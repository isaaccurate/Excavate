"""Score reviewed section labels using the application's retrieval pipeline."""

import hashlib
import json
import os
import platform
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx

from knowledge_assistant.embeddings import HashEmbeddings, OpenAIEmbeddings
from knowledge_assistant.hybrid import HybridSearch
from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.storage import SQLiteDocumentStore

MODES = ("lexical", "dense", "hybrid")


def score_ranking(ranking, relevant):
    """Score listed relevant sections, without inferring fact coverage."""
    hits = relevant.intersection(ranking[:5])
    first = next((i for i, key in enumerate(ranking[:5], 1) if key in relevant), None)
    return {
        "recall_at_5": len(hits) / len(relevant),
        "hit_at_5": bool(hits),
        "all_sources_at_5": hits == relevant,
        "reciprocal_rank_at_5": 1 / first if first else 0,
    }


def evidence_groups(question):
    """Return required evidence groups, allowing explicitly reviewed alternatives."""
    if "evidence_groups" in question:
        groups = question["evidence_groups"]
        if not groups or any(not group["alternatives"] for group in groups):
            raise ValueError("evidence groups must contain supporting sections")
        return [group["alternatives"] for group in groups]
    return [[source] for source in question["sources"]]


def source_key(source):
    return source["path"], tuple(source["heading"])


def score_evidence(ranking, groups):
    """Credit each required group once when any accepted section is retrieved."""
    positions = [
        next((i for i, key in enumerate(ranking[:5], 1) if key in group), None)
        for group in groups
    ]
    ranks = [rank for rank in positions if rank is not None]
    return {
        "evidence_recall_at_5": len(ranks) / len(groups),
        "hit_at_5": bool(ranks),
        "full_evidence_at_5": len(ranks) == len(groups),
        "reciprocal_rank_at_5": 1 / min(ranks) if ranks else 0,
    }


def aggregate_metrics(results):
    scored = [result for result in results if result["metrics"] is not None]
    if not scored:
        raise ValueError("evaluation needs at least one scored question")
    return {
        mode: {
            metric: sum(row["metrics"][mode][metric] for row in scored) / len(scored)
            for metric in scored[0]["metrics"][mode]
        }
        for mode in MODES
    }


def rescore_report(dataset_path: Path, original: dict) -> dict:
    """Rescore saved rankings without changing queries or calling providers."""
    dataset = json.loads(dataset_path.read_text())
    questions = {q["id"]: q for q in dataset["questions"]}
    if len(questions) != len(dataset["questions"]):
        raise ValueError("duplicate question IDs")
    if set(questions) != {r["id"] for r in original["results"]}:
        raise ValueError("saved report and labels have different questions")
    results = []
    for saved in original["results"]:
        question = questions[saved["id"]]
        if question["answerable"] != saved["answerable"]:
            raise ValueError("rescoring cannot change answerability")
        groups = [
            {source_key(source) for source in alternatives}
            for alternatives in evidence_groups(question)
        ]
        scored = question["answerable"] and not question.get(
            "exclude_from_scoring", False
        )
        results.append(
            saved
            | {
                "excluded_from_scoring": question.get("exclude_from_scoring", False),
                "metrics": {
                    mode: score_evidence(
                        [source_key(row) for row in saved["rankings"][mode]], groups
                    )
                    for mode in MODES
                }
                if scored
                else None,
            }
        )
    return original | {
        "original_dataset_sha256": original["dataset_sha256"],
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "label_revision": dataset.get("label_revision", 1),
        "rescore_embedding_http_calls": 0,
        "scored_questions": sum(row["metrics"] is not None for row in results),
        "scoring": "Macro evidence-group Recall@5, Hit@5, full-evidence@5, MRR@5. Explicit alternatives satisfy the same group. Unanswerable and excluded questions have rankings only.",
        "metrics": aggregate_metrics(results),
        "results": results,
    }


def evaluate_labeled(dataset_path: Path, root: Path, model: str | None) -> dict:
    dataset = json.loads(dataset_path.read_text())
    questions = dataset["questions"]
    if dataset["status"] != "human_reviewed":
        raise ValueError("dataset must be human reviewed")
    ids = [q["id"] for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate question IDs")
    calls = []
    tokens = []

    def record_response(response):
        calls.append(response.status_code)
        response.read()
        if response.is_success:
            usage = response.json().get("usage", {})
            tokens.append(usage.get("total_tokens", 0))

    with (
        TemporaryDirectory() as directory,
        httpx.Client(event_hooks={"response": [record_response]}) as client,
    ):
        store = SQLiteDocumentStore(Path(directory) / "evaluation.sqlite3")
        try:
            for path in dataset["corpus"]["paths"]:
                ingest_note(root, path, store)
            documents = store.list_documents()
            labels = defaultdict(set)
            metadata = {}
            for document in documents:
                for chunk in document.chunks:
                    labels[document.path, chunk.heading].add(chunk.id)
                    metadata[chunk.id] = {
                        "path": document.path,
                        "heading": chunk.heading,
                        "id": chunk.id,
                    }
            targets = {}
            # Validate every label before making any paid provider requests.
            for question in questions:
                relevant = set()
                for source in [s for group in evidence_groups(question) for s in group]:
                    key = (source["path"], tuple(source["heading"]))
                    if key not in labels:
                        raise ValueError(
                            f"unresolved source for {question['id']}: {key}"
                        )
                    relevant.update(labels[key])
                if bool(relevant) != question["answerable"]:
                    raise ValueError(f"inconsistent answerability for {question['id']}")
                targets[question["id"]] = relevant
            provider = (
                OpenAIEmbeddings(
                    client, api_key=os.environ["OPENAI_API_KEY"], model=model
                )
                if model
                else HashEmbeddings()
            )
            started = perf_counter()
            search = HybridSearch(store, provider)
            setup_seconds = perf_counter() - started
            results = []
            for question in questions:
                started = perf_counter()
                ranks = search.search(question["question"], limit=5, candidates=20)
                elapsed = perf_counter() - started
                relevant = targets[question["id"]]
                result = {
                    "id": question["id"],
                    "answerable": question["answerable"],
                    "retrieval_seconds": elapsed,
                    "rankings": {
                        mode: [metadata[key] for key in getattr(ranks, mode)]
                        for mode in MODES
                    },
                    "metrics": {
                        mode: score_ranking(getattr(ranks, mode), relevant)
                        for mode in MODES
                    }
                    if relevant
                    else None,
                }
                results.append(result)
            report = {
                "dataset": dataset["name"],
                "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                "model": model or "local-token-hash",
                "python": platform.python_version(),
                "corpus": [
                    {"path": d.path, "digest": d.digest, "chunks": len(d.chunks)}
                    for d in documents
                ],
                "questions": len(questions),
                "answerable": sum(q["answerable"] for q in questions),
                "unanswerable": sum(not q["answerable"] for q in questions),
                "scope": "Each dataset uses only its own declared note selection.",
                "scoring": "Macro section Recall@5, Hit@5, all-listed-sources@5, MRR@5. Unanswerable cases have rankings only.",
                "setup_seconds": setup_seconds,
                "embedding_http_calls": len(calls),
                "embedding_tokens": sum(tokens),
                "metrics": {},
                "results": results,
            }
            return rescore_report(dataset_path, report)
        finally:
            store.engine.dispose()


def benchmark_labeled(dataset_path: Path, root: Path, model: str, repeats: int) -> dict:
    """Compare real provider work with and without persistent document vectors."""
    from math import ceil
    from statistics import median

    dataset = json.loads(dataset_path.read_text())
    if repeats < 1 or dataset["status"] != "human_reviewed":
        raise ValueError("positive repeats and reviewed labels are required")
    samples = {"disabled": [], "enabled": []}
    cold = []
    active = {}

    def observe(response):
        response.read()
        active["http_calls"] += 1
        if response.is_success:
            active["tokens"] += response.json().get("usage", {}).get("total_tokens", 0)

    class MeasuredProvider(OpenAIEmbeddings):
        @property
        def cache_namespace(self):
            return super().cache_namespace if self.enabled else ""

        def embed(self, texts):
            active[f"{self.phase}_inputs"] += len(texts)
            started = perf_counter()
            result = super().embed(texts)
            active[f"{self.phase}_seconds"] += perf_counter() - started
            return result

    with (
        TemporaryDirectory() as directory,
        httpx.Client(event_hooks={"response": [observe]}) as client,
    ):
        database = Path(directory) / "benchmark.sqlite3"
        store = SQLiteDocumentStore(database)
        try:
            for path in dataset["corpus"]["paths"]:
                ingest_note(root, path, store)
            documents = store.list_documents()
        finally:
            store.engine.dispose()

        def request(question, enabled):
            active.clear()
            active.update(
                {
                    "question_id": question["id"],
                    "http_calls": 0,
                    "tokens": 0,
                    "document_inputs": 0,
                    "query_inputs": 0,
                    "document_seconds": 0,
                    "query_seconds": 0,
                }
            )
            provider = MeasuredProvider(
                client, api_key=os.environ["OPENAI_API_KEY"], model=model
            )
            provider.enabled = enabled
            provider.phase = "document"
            started = perf_counter()
            store = SQLiteDocumentStore(database)
            try:
                search = HybridSearch(store, provider)
                provider.phase = "query"
                rankings = search.search(question["question"])
                active["rankings"] = {
                    mode: list(getattr(rankings, mode)) for mode in MODES
                }
            finally:
                store.engine.dispose()
            active["total_seconds"] = perf_counter() - started
            return dict(active)

        # Record the cost to populate the cache separately from repeated requests.
        cold.append(request(dataset["questions"][0], True))
        for repeat in range(repeats):
            for index, question in enumerate(dataset["questions"]):
                # Alternate order to reduce systematic network/order effects.
                order = (False, True) if (repeat + index) % 2 == 0 else (True, False)
                for enabled in order:
                    samples["enabled" if enabled else "disabled"].append(
                        request(question, enabled)
                    )

        summary = {}
        for mode, rows in samples.items():
            times = sorted(row["total_seconds"] * 1000 for row in rows)
            summary[mode] = {
                "requests": len(rows),
                "median_ms": median(times),
                "p95_ms": times[ceil(len(times) * 0.95) - 1],
                "http_calls": sum(row["http_calls"] for row in rows),
                "tokens": sum(row["tokens"] for row in rows),
                "document_inputs": sum(row["document_inputs"] for row in rows),
                "query_inputs": sum(row["query_inputs"] for row in rows),
            }
        parity = all(
            before["question_id"] == after["question_id"]
            and before["rankings"] == after["rankings"]
            for before, after in zip(
                samples["disabled"], samples["enabled"], strict=True
            )
        )
        return {
            "dataset": dataset["name"],
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "model": model,
            "python": platform.python_version(),
            "corpus": [
                {"path": d.path, "digest": d.digest, "chunks": len(d.chunks)}
                for d in documents
            ],
            "repeats": repeats,
            "summary": summary,
            "all_rankings_identical": parity,
            "cold_cache_population": cold,
            "samples": samples,
            "methodology": "Paired requests in alternating order, reopened SQLite stores, shared HTTP connection pool, populated persistent cache. Excludes imports, ingestion and generation. Cold sample is cache population, not process startup.",
        }


def evaluate_answers(
    dataset_path: Path, root: Path, embedding_model: str, model: str
) -> dict:
    """Run the production answering flow and retain evidence for source review."""
    from knowledge_assistant.answering import GenerationError, answer_question
    from knowledge_assistant.generation import OpenAIGeneration

    dataset = json.loads(dataset_path.read_text())
    if dataset["status"] != "human_reviewed":
        raise ValueError("dataset must be human reviewed")

    class CapturedGeneration(OpenAIGeneration):
        def generate(self, *, instructions, input_text):
            self.evidence = json.loads(input_text)["passages"]
            return super().generate(instructions=instructions, input_text=input_text)

    usage = []

    def observe(response):
        response.read()
        if response.is_success:
            usage.append(
                {
                    "endpoint": response.request.url.path,
                    "usage": response.json().get("usage", {}),
                }
            )

    with (
        TemporaryDirectory() as directory,
        httpx.Client(event_hooks={"response": [observe]}) as client,
    ):
        store = SQLiteDocumentStore(Path(directory) / "answers.sqlite3")
        try:
            for path in dataset["corpus"]["paths"]:
                ingest_note(root, path, store)
            documents = store.list_documents()
            embeddings = OpenAIEmbeddings(
                client, api_key=os.environ["OPENAI_API_KEY"], model=embedding_model
            )
            generation = CapturedGeneration(
                client, api_key=os.environ["OPENAI_API_KEY"], model=model
            )
            results = []
            for question in dataset["questions"]:
                generation.evidence = []
                started = perf_counter()
                try:
                    search = HybridSearch(store, embeddings)
                    answer = answer_question(question["question"], search, generation)
                    result = {"result": answer.model_dump(mode="json"), "error": None}
                except GenerationError as error:
                    result = {"result": None, "error": str(error)}
                results.append(
                    {
                        "id": question["id"],
                        "question": question["question"],
                        "expected_answerable": question["answerable"],
                        "elapsed_seconds": perf_counter() - started,
                        "evidence": generation.evidence,
                        **result,
                    }
                )
            return {
                "dataset": dataset["name"],
                "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                "embedding_model": embedding_model,
                "generation_model": model,
                "corpus": [
                    {"path": d.path, "digest": d.digest, "chunks": len(d.chunks)}
                    for d in documents
                ],
                "usage": usage,
                "results": results,
            }
        finally:
            store.engine.dispose()
