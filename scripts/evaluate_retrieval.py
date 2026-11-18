"""Evaluate retrieval on selected course notes or a synthetic corpus."""

import argparse
import json
import math
import platform
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from types import SimpleNamespace
from unittest.mock import patch

import faiss
import numpy as np
import sqlalchemy
from sqlalchemy import delete

from knowledge_assistant import hybrid, retrieval
from knowledge_assistant.embeddings import HashEmbeddings
from knowledge_assistant.hybrid import HybridSearch
from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.storage import EmbeddingRow, SQLiteDocumentStore

STABLE_MATCHING = "Stable Matching.md"
MASTER_THEOREM = "Divide and Conquer Algorithm/Master Theorem.md"
CASES = (
    (
        "What makes a resident and hospital an unstable pair?",
        STABLE_MATCHING,
        ("Formal Definition",),
    ),
    (
        "Why can’t a hospital and a resident who prefer each other end up apart?",
        STABLE_MATCHING,
        ("Gale Shapley Algorithm", "Proof"),
    ),
    (
        "Why does equal work at every recursion level introduce a logarithmic factor?",
        MASTER_THEOREM,
        ("Intuition",),
    ),
    (
        "When do the leaves dominate the total work of a divide-and-conquer recurrence?",
        MASTER_THEOREM,
        ("Intuition",),
    ),
)


# These cases are synthetic and can be reproduced without a private vault.
SYNTHETIC_CASES = (
    (
        "Fern",
        "Keep fern specimens at 55 percent humidity.",
        "What humidity is needed for fern specimens?",
    ),
    (
        "Atlas",
        "Atlas export archives expire after 14 days.",
        "How long can I download an Atlas export?",
    ),
    (
        "Harbor",
        "The Harbor evacuation assembly point is the east pier.",
        "Where should people meet after evacuating Harbor?",
    ),
    (
        "Lumen",
        "Use a 5 amp fuse in the Lumen power supply.",
        "Which fuse rating fits Lumen?",
    ),
    (
        "Juniper",
        "Juniper greenhouse vents open when temperature reaches 28 Celsius.",
        "At what temperature do Juniper vents open?",
    ),
    (
        "Cedar",
        "Cedar collects water samples every Tuesday at noon.",
        "When does Cedar collect water samples?",
    ),
    (
        "Echo",
        "The Echo receiver uses channel 19 for emergency calls.",
        "Which channel carries Echo emergency calls?",
    ),
    (
        "Orchard",
        "Orchard stores seed envelopes in cabinet seven.",
        "Where are the seed envelopes kept in Orchard?",
    ),
)


def seed_corpus(directory: Path) -> Path:
    database = directory / "benchmark.sqlite3"
    store = SQLiteDocumentStore(database)
    try:
        for topic, answer, _ in SYNTHETIC_CASES:
            path = directory / f"{topic}.md"
            path.write_text(f"# Reference\n{answer}\n", encoding="utf-8")
            ingest_note(directory, path.name, store)
            for number in range(24):
                path = directory / f"{topic} Log {number:02}.md"
                path.write_text(
                    f"# Activity log\n"
                    f"Technicians reviewed {topic} on shift {number}. "
                    "They recorded equipment status, checked labels and updated the "
                    "maintenance log before handing over to the next shift. "
                    "The reference note contains operating values and procedures.\n",
                    encoding="utf-8",
                )
                ingest_note(directory, path.name, store)
    finally:
        store.engine.dispose()
    return database


class TimedEmbeddings(HashEmbeddings):
    def __init__(self, metrics: Counter) -> None:
        self.metrics = metrics
        self.phase = "document"

    def embed(self, texts):
        started = perf_counter_ns()
        result = super().embed(texts)
        self.metrics[f"{self.phase}_embedding_ns"] += perf_counter_ns() - started
        self.metrics[f"{self.phase}_inputs"] += len(texts)
        self.metrics[f"{self.phase}_provider_calls"] += 1
        return result


def measure_request(
    database: Path, case_index: int, *, cache_enabled: bool = True
) -> dict:
    metrics: Counter = Counter(
        dict.fromkeys(
            (
                "storage_read_ns",
                "cache_read_ns",
                "cache_write_ns",
                "document_embedding_ns",
                "document_inputs",
                "document_provider_calls",
                "faiss_build_ns",
                "bm25_build_ns",
                "query_embedding_ns",
                "query_inputs",
                "query_provider_calls",
            ),
            0,
        )
    )
    provider = TimedEmbeddings(metrics)
    if not cache_enabled:
        provider.cache_namespace = None
    _, _, query = SYNTHETIC_CASES[case_index]

    class TimedStore(SQLiteDocumentStore):
        def list_documents(self):
            started = perf_counter_ns()
            documents = super().list_documents()
            metrics["storage_read_ns"] += perf_counter_ns() - started
            return documents

        def read_embeddings(self, namespace, input_digests):
            started = perf_counter_ns()
            result = super().read_embeddings(namespace, input_digests)
            metrics["cache_read_ns"] += perf_counter_ns() - started
            return result

        def write_embeddings(self, namespace, documents, entries):
            started = perf_counter_ns()
            super().write_embeddings(namespace, documents, entries)
            metrics["cache_write_ns"] += perf_counter_ns() - started

    class TimedFaiss(hybrid.FaissVectorSearch):
        def __init__(self, *args):
            started = perf_counter_ns()
            super().__init__(*args)
            metrics["faiss_build_ns"] += perf_counter_ns() - started

    class TimedFtsConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if not sql.startswith("CREATE VIRTUAL TABLE"):
                return super().execute(sql, parameters)
            started = perf_counter_ns()
            result = super().execute(sql, parameters)
            metrics["bm25_build_ns"] += perf_counter_ns() - started
            return result

        def executemany(self, sql, parameters):
            started = perf_counter_ns()
            result = super().executemany(sql, parameters)
            metrics["bm25_build_ns"] += perf_counter_ns() - started
            return result

    def connect_fts(name):
        started = perf_counter_ns()
        connection = sqlite3.connect(name, factory=TimedFtsConnection)
        metrics["bm25_build_ns"] += perf_counter_ns() - started
        return connection

    with (
        patch.object(hybrid, "FaissVectorSearch", TimedFaiss),
        patch.object(retrieval, "sqlite3", SimpleNamespace(connect=connect_fts)),
    ):
        started = perf_counter_ns()
        store = TimedStore(database)
        try:
            search = HybridSearch(store, provider)
            provider.phase = "query"
            search.search(query)
        finally:
            store.engine.dispose()
        metrics["total_ns"] = perf_counter_ns() - started
    return dict(metrics)


def summarize(samples: list[dict]) -> dict:
    summary = {}
    for metric in samples[0]:
        values = sorted(sample.get(metric, 0) for sample in samples)
        if metric.endswith("_ns"):
            summary[metric.removesuffix("_ns") + "_ms"] = {
                "median": round(median(values) / 1e6, 3),
                "p95": round(values[math.ceil(len(values) * 0.95) - 1] / 1e6, 3),
            }
        else:
            summary[metric] = {"min": values[0], "max": values[-1]}
    return summary


def evaluate_quality(database: Path) -> dict:
    store = SQLiteDocumentStore(database)
    try:
        search = HybridSearch(store, HashEmbeddings())
        targets = {doc.path: doc.chunks[0].id for doc in search.snapshot.documents}
        positions = {mode: [] for mode in ("lexical", "dense", "hybrid")}
        for topic, _, query in SYNTHETIC_CASES:
            target = targets[f"{topic}.md"]
            top = search.search(query)
            full = search.search(query, limit=len(targets), candidates=len(targets))
            for mode in positions:
                ranking = getattr(full, mode)
                rank = ranking.index(target) + 1 if target in ranking else 0
                positions[mode].append((target in getattr(top, mode), rank))
        return {
            mode: {
                "recall_at_5": sum(hit for hit, _ in results) / len(results),
                "mrr_full_candidates": sum(
                    1 / rank if rank else 0 for _, rank in results
                )
                / len(results),
            }
            for mode, results in positions.items()
        }
    finally:
        store.engine.dispose()


def benchmark(repeats: int, *, cache_enabled: bool = True) -> dict:
    with TemporaryDirectory() as directory:
        database = seed_corpus(Path(directory))
        case_indices = range(len(SYNTHETIC_CASES))
        worker_flags = [] if cache_enabled else ["--disable-cache"]

        def fresh_request(index, *, clear=False):
            return json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "scripts.evaluate_retrieval",
                        "--worker",
                        str(database),
                        str(index),
                        *worker_flags,
                        *(["--clear-cache"] if clear else []),
                    ],
                    text=True,
                )
            )

        cold = [
            fresh_request(index, clear=True) for _ in range(3) for index in case_indices
        ]
        fresh_cached = [
            fresh_request(index) for _ in range(3) for index in case_indices
        ]
        # Warm the process, then keep the request lifecycle the same for every sample.
        measure_request(database, 0, cache_enabled=cache_enabled)
        warm = [
            measure_request(database, index, cache_enabled=cache_enabled)
            for _ in range(repeats)
            for index in case_indices
        ]
        return {
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "sqlalchemy": sqlalchemy.__version__,
                "faiss": faiss.__version__,
                "numpy": np.__version__,
                "faiss_threads": faiss.omp_get_max_threads(),
            },
            "embedding_provider": "local token hash",
            "cache_enabled": cache_enabled,
            "external_embedding_api_calls": 0,
            "external_embedding_cost_usd": 0,
            "documents_and_chunks": len(SYNTHETIC_CASES) * 25,
            "questions": len(SYNTHETIC_CASES),
            "cold_samples": len(cold),
            "warm_samples": len(warm),
            "cold": summarize(cold),
            "warm": summarize(warm),
            "fresh_process_populated_cache": summarize(fresh_cached),
            "quality": evaluate_quality(database),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, nargs="?", help="Directory containing the selected notes."
    )
    parser.add_argument(
        "--dataset", type=Path, help="Reviewed JSON labels for the supplied root."
    )
    parser.add_argument(
        "--embedding-model",
        help="Opt in to sending the selected notes and questions to OpenAI.",
    )
    parser.add_argument(
        "--rescore",
        type=Path,
        help="Rescore saved rankings with revised labels, without API calls.",
    )
    parser.add_argument(
        "--disable-cache", action="store_true", help="Benchmark with caching disabled."
    )
    parser.add_argument("--clear-cache", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Benchmark the labeled corpus with real embeddings.",
    )
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--worker", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.benchmark:
        if (
            not args.dataset
            or not args.root
            or not args.embedding_model
            or args.repeats < 1
            or args.synthetic
            or args.rescore
            or args.worker
        ):
            parser.error(
                "--benchmark requires a root, --dataset, --embedding-model and positive --repeats"
            )
        from scripts.evaluate_labeled import benchmark_labeled

        print(
            json.dumps(
                benchmark_labeled(
                    args.dataset, args.root, args.embedding_model, args.repeats
                ),
                indent=2,
            )
        )
        return
    if args.rescore:
        if (
            not args.dataset
            or args.root
            or args.embedding_model
            or args.synthetic
            or args.worker
        ):
            parser.error("--rescore requires --dataset and no retrieval options")
        from scripts.evaluate_labeled import rescore_report

        print(
            json.dumps(
                rescore_report(args.dataset, json.loads(args.rescore.read_text())),
                indent=2,
            )
        )
        return
    if args.dataset:
        if args.root is None or args.synthetic or args.worker:
            parser.error(
                "--dataset requires a root and cannot use synthetic/worker mode"
            )
        from scripts.evaluate_labeled import evaluate_labeled

        print(
            json.dumps(
                evaluate_labeled(args.dataset, args.root, args.embedding_model),
                indent=2,
            )
        )
        return
    if args.embedding_model:
        parser.error("--embedding-model requires --dataset")
    if args.worker:
        database, index = args.worker
        if args.clear_cache:
            store = SQLiteDocumentStore(Path(database))
            try:
                with store.engine.begin() as connection:
                    connection.execute(delete(EmbeddingRow))
            finally:
                store.engine.dispose()
        print(
            json.dumps(
                measure_request(
                    Path(database), int(index), cache_enabled=not args.disable_cache
                )
            )
        )
        return
    if args.synthetic:
        if args.root or args.repeats < 1:
            parser.error("synthetic evaluation requires positive repeats and no root")
        print(
            json.dumps(
                benchmark(args.repeats, cache_enabled=not args.disable_cache), indent=2
            )
        )
        return
    if args.root is None:
        parser.error("provide a course-note root or select --synthetic")

    with TemporaryDirectory() as directory:
        store = SQLiteDocumentStore(Path(directory) / "eval.sqlite3")
        for note in (STABLE_MATCHING, MASTER_THEOREM):
            ingest_note(args.root, note, store)
        search = HybridSearch(store, HashEmbeddings())
        labels = {
            (doc.path, chunk.heading): chunk.id
            for doc in search.snapshot.documents
            for chunk in doc.chunks
        }
        print(f"{len(labels)} passages. Columns: lexical, dense, hybrid.")
        for query, path, heading in CASES:
            target = labels[path, heading]
            ranks = search.search(query, limit=len(labels), candidates=len(labels))
            print(
                [
                    ranking.index(target) + 1 if target in ranking else None
                    for ranking in (ranks.lexical, ranks.dense, ranks.hybrid)
                ],
                query,
            )


if __name__ == "__main__":
    main()
