from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.retrieval import reciprocal_rank_fusion, search_lexical
from knowledge_assistant.storage import SQLiteDocumentStore


def test_lexical_search_reads_latest_selected_content(tmp_path):
    store = SQLiteDocumentStore(tmp_path / "notes.sqlite3")
    path = tmp_path / "example.md"
    path.write_text("# Deployment\nSQLite WAL")
    ingest_note(tmp_path, path.name, store)
    (document,) = store.list_documents()
    (chunk,) = document.chunks

    assert search_lexical(store, '"Deployment" OR', limit=2) == (chunk.id,)
    assert search_lexical(store, "???", limit=2) == ()

    path.write_text("# Local\nFAISS indexing")
    ingest_note(tmp_path, path.name, store)
    assert search_lexical(store, "deployment", limit=2) == ()
    assert len(search_lexical(store, "faiss", limit=2)) == 1

    store.delete(path.name)
    assert search_lexical(store, "faiss", limit=2) == ()


def test_fusion_rewards_agreement_and_uses_stable_ties():
    assert reciprocal_rank_fusion(
        ("b", "shared", "shared"), ("a", "shared"), limit=3
    ) == ("shared", "a", "b")
    assert reciprocal_rank_fusion(("b", "a"), ("a", "b"), limit=1) == ("a",)
    assert reciprocal_rank_fusion(limit=1) == ()
