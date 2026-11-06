import httpx
import pytest

from knowledge_assistant.embeddings import (
    EmbeddingError,
    HashEmbeddings,
    OpenAIEmbeddings,
)
from knowledge_assistant.hybrid import FaissVectorSearch, HybridSearch
from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.storage import SQLiteDocumentStore


def test_faiss_cosine_search():
    index = FaissVectorSearch(["long", "aligned", "tie"], [[100, 100], [1, 0], [2, 0]])
    assert index.search([3, 0], limit=2) == ("aligned", "tie")
    with pytest.raises(EmbeddingError):
        index.search([1], limit=1)


def test_hybrid_snapshot(tmp_path):
    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    note = tmp_path / "test.md"
    note.write_text("# Storage\nSQLite\n# Search\nFAISS")
    ingest_note(tmp_path, note.name, store)
    document = store.get(note.name)
    assert document is not None
    expected = (document.chunks[1].id,)
    search = HybridSearch(store, HashEmbeddings())
    store.delete(note.name)
    result = search.search("FAISS", limit=1)
    assert result.lexical == result.dense == result.hybrid == expected
    assert not HybridSearch(store, HashEmbeddings()).search("FAISS").hybrid


@pytest.mark.parametrize("status, indices", [(200, [1, 0]), (200, [0, 0]), (429, [])])
def test_managed_provider_response(status, indices):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status,
            json={"data": [{"index": i, "embedding": [float(i)]} for i in indices]},
        )
    )
    with httpx.Client(transport=transport) as client:
        provider = OpenAIEmbeddings(client, api_key="test", model="test")
        if indices == [1, 0]:
            assert provider.embed(["one", "two"]) == [[0.0], [1.0]]
        else:
            with pytest.raises(EmbeddingError):
                provider.embed(["one", "two"])


def test_search_cli_defaults_to_local_provider(tmp_path, monkeypatch, capsys):
    from knowledge_assistant.cli import main

    database = tmp_path / "db.sqlite3"
    note = tmp_path / "test.md"
    note.write_text("# Storage\nSQLite")
    ingest_note(tmp_path, note.name, SQLiteDocumentStore(database))
    monkeypatch.setenv("OPENAI_API_KEY", "unused")
    monkeypatch.setattr(
        "sys.argv",
        [
            "knowledge-assistant",
            "--db",
            str(database),
            "search",
            "SQLite",
            "--limit",
            "1",
        ],
    )
    main()
    output = capsys.readouterr().out
    assert output.count("1. test.md → Storage") == 3


@pytest.mark.parametrize("vectors", [[[1, 2]], [[1], [1, 2]], [[1], [float("nan")]]])
def test_faiss_rejects_invalid_embedding_batches(vectors):
    with pytest.raises(EmbeddingError):
        FaissVectorSearch(["first", "second"], vectors)


def test_title_only_query_matches_both_indexes(tmp_path):
    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    for name in ("Master Theorem.md", "Other.md"):
        (tmp_path / name).write_text("recurrence")
        ingest_note(tmp_path, name, store)
    document = store.get("Master Theorem.md")
    assert document is not None
    expected = (document.chunks[0].id,)
    result = HybridSearch(store, HashEmbeddings()).search("Master Theorem", limit=1)
    assert result.lexical == result.dense == result.hybrid == expected


@pytest.mark.parametrize("query, limit", [("", 5), ("  ", 5), ("SQLite", 0)])
def test_empty_cli_search_skips_provider(tmp_path, monkeypatch, capsys, query, limit):
    from knowledge_assistant.cli import main

    database = tmp_path / "db.sqlite3"
    (tmp_path / "note.md").write_text("SQLite")
    ingest_note(tmp_path, "note.md", SQLiteDocumentStore(database))

    def unexpected_client(*args, **kwargs):
        pytest.fail("empty search created an HTTP client")

    monkeypatch.setattr(httpx, "Client", unexpected_client)
    monkeypatch.setattr(
        "sys.argv",
        [
            "knowledge-assistant",
            "--db",
            str(database),
            "search",
            query,
            "--limit",
            str(limit),
            "--openai-model",
            "test",
        ],
    )
    main()
    assert capsys.readouterr().out == "lexical\ndense\nhybrid\n"
