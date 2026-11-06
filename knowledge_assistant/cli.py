import argparse
import os
import sqlite3
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from knowledge_assistant.answer_service import (
    AnswerConfigurationError,
    configured_answer,
)
from knowledge_assistant.answering import AnswerRequest, GenerationError
from knowledge_assistant.ingestion import ingest_note, note_key
from knowledge_assistant.store_config import (
    open_aws_document_store,
    open_document_store,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage explicitly selected Markdown notes."
    )
    parser.add_argument("--db", type=Path, default=Path("knowledge.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--root", type=Path, required=True)
    ingest.add_argument("path")
    remove = commands.add_parser("delete")
    remove.add_argument("path")
    commands.add_parser(
        "restore", help="Restore an AWS note within its recovery window."
    ).add_argument("path")
    commands.add_parser("purge", help="Permanently delete an AWS note.").add_argument(
        "path"
    )
    commands.add_parser("cleanup", help="Purge expired AWS note versions.")

    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument(
        "--openai-model", help="Opt in to sending passages and queries to OpenAI."
    )
    ask = commands.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument(
        "--openai-model",
        required=True,
        help="Generation model. Sends the question and selected evidence to OpenAI.",
    )
    ask.add_argument(
        "--embedding-model",
        help="Opt in to sending all stored passages and the question for embeddings.",
    )

    args = parser.parse_args()
    if args.command == "ask":
        try:
            question = AnswerRequest(question=args.question).question
        except ValueError:
            parser.error("question must be nonblank and at most 1,000 characters")
        try:
            result = configured_answer(
                question,
                database=args.db,
                model=args.openai_model,
                embedding_model=args.embedding_model,
            )
        except AnswerConfigurationError as error:
            parser.exit(1, f"knowledge-assistant: {error}\n")
        except (OSError, sqlite3.Error, SQLAlchemyError, ValueError):
            parser.exit(1, "knowledge-assistant: answer retrieval failed\n")
        except GenerationError:
            parser.exit(1, "knowledge-assistant: answer provider failed\n")
        print(result.model_dump_json())
        return
    if args.command == "search":
        try:
            run_search(args.db, args.query, args.limit, args.openai_model)
        except (
            ImportError,
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
        ) as error:
            parser.exit(1, f"knowledge-assistant: {error}\n")
        return
    if args.command in {"restore", "purge", "cleanup"}:
        try:
            path = None if args.command == "cleanup" else note_key(args.path)
            with open_aws_document_store() as store:
                if path is None:
                    print(f"purged notes: {store.cleanup()}")
                elif args.command == "restore":
                    print(
                        f"{'restored' if store.restore(path) else 'not recoverable'}: {path}"
                    )
                else:
                    print(
                        f"{'purged' if store.purge(path) else 'no note purged'}: {path}"
                    )
        except (OSError, ValueError) as error:
            parser.exit(1, f"knowledge-assistant: {error}\n")
        return
    try:
        key = note_key(args.path)
        with open_document_store(args.db, create=True) as store:
            if args.command == "ingest":
                outcome = (
                    "indexed" if ingest_note(args.root, key, store) else "unchanged"
                )
            else:
                outcome = "deleted" if store.delete(key) else "absent"
    except (OSError, ValueError, SQLAlchemyError) as error:
        parser.exit(1, f"knowledge-assistant: {error}\n")
    print(f"{outcome}: {key}")


def run_search(database: Path, query: str, limit: int, model: str | None) -> None:
    import httpx

    from knowledge_assistant.contracts import EmbeddingProvider
    from knowledge_assistant.embeddings import HashEmbeddings, OpenAIEmbeddings
    from knowledge_assistant.hybrid import HybridSearch

    if limit < 0:
        raise ValueError("limit must be nonnegative")
    # Constructing HybridSearch embeds the corpus, so handle no-op requests first.
    if not query.strip() or limit == 0:
        print("lexical\ndense\nhybrid")
        return
    with open_document_store(database) as store, httpx.Client() as client:
        provider: EmbeddingProvider = HashEmbeddings()
        if model is not None:
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("set OPENAI_API_KEY to use the managed provider")
            provider = OpenAIEmbeddings(client, api_key=key, model=model)
        search = HybridSearch(store, provider)
        ranks = search.search(query, limit=limit, candidates=max(20, limit))

    sources = {
        chunk.id: " → ".join((document.path, *chunk.heading))
        for document in search.snapshot.documents
        for chunk in document.chunks
    }
    for name in ("lexical", "dense", "hybrid"):
        print(name)
        for rank, chunk_id in enumerate(getattr(ranks, name), start=1):
            print(f"  {rank}. {sources[chunk_id]} [{chunk_id}]")


if __name__ == "__main__":
    main()
