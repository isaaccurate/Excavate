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
from knowledge_assistant.storage import SQLiteDocumentStore


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
    try:
        key = note_key(args.path)
        store = SQLiteDocumentStore(args.db)
        if args.command == "ingest":
            outcome = "indexed" if ingest_note(args.root, key, store) else "unchanged"
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
    if not database.is_file():
        raise ValueError("database does not exist")
    # Constructing HybridSearch embeds the corpus, so handle no-op requests first.
    if not query.strip() or limit == 0:
        print("lexical\ndense\nhybrid")
        return
    with httpx.Client() as client:
        provider: EmbeddingProvider = HashEmbeddings()
        if model is not None:
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("set OPENAI_API_KEY to use the managed provider")
            provider = OpenAIEmbeddings(client, api_key=key, model=model)
        search = HybridSearch(SQLiteDocumentStore(database), provider)
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
