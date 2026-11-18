from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, update

from knowledge_assistant.embeddings import EmbeddingError, HashEmbeddings
from knowledge_assistant.hybrid import HybridSearch, Snapshot
from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.storage import EmbeddingRow, SQLiteDocumentStore


class CountingEmbeddings(HashEmbeddings):
    def __init__(self, namespace="test-hash-v1", before_embed=None):
        self.cache_namespace = namespace
        self.calls = []
        self.before_embed = before_embed

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.before_embed:
            self.before_embed()
        return super().embed(texts)


@pytest.fixture
def corpus(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("""# Storage
SQLite stores documents.
# Search
FAISS searches vectors.""")
    store = SQLiteDocumentStore(tmp_path / "notes.sqlite3")
    ingest_note(tmp_path, note.name, store)
    yield store, note
    store.engine.dispose()


def cache_count(store):
    with store.engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(EmbeddingRow))


def test_cache_survives_reopening_and_preserves_rankings(corpus):
    store, note = corpus
    documents = store.list_documents()
    expected = HybridSearch(Snapshot(documents), HashEmbeddings()).search("vectors")
    first = CountingEmbeddings()
    assert HybridSearch(store, first).search("vectors") == expected
    assert [len(batch) for batch in first.calls] == [2, 1]
    reopened = SQLiteDocumentStore(note.parent / "notes.sqlite3")
    try:
        repeated = CountingEmbeddings()
        assert HybridSearch(reopened, repeated).search("vectors") == expected
        assert repeated.calls == [["vectors"]]
    finally:
        reopened.engine.dispose()
    assert not ingest_note(note.parent, note.name, store)
    unchanged = CountingEmbeddings()
    HybridSearch(store, unchanged)
    assert unchanged.calls == []


def test_partial_edit_and_delete_remove_superseded_vectors(corpus):
    store, note = corpus
    HybridSearch(store, CountingEmbeddings())
    old = store.get(note.name)
    note.write_text("""# Storage
SQLite stores documents.
# Search
BM25 searches words.""")
    assert ingest_note(note.parent, note.name, store)
    assert cache_count(store) == 1
    provider = CountingEmbeddings()
    updated = HybridSearch(store, provider)
    assert len(provider.calls) == 1 and len(provider.calls[0]) == 1
    assert "BM25" in provider.calls[0][0]
    assert old.chunks[1].id not in updated.search("FAISS").hybrid
    store.delete(note.name)
    assert cache_count(store) == 0
    empty = CountingEmbeddings()
    assert not HybridSearch(store, empty).search("words").hybrid
    assert empty.calls == []


def test_namespace_change_computes_new_vectors(corpus):
    store, _ = corpus
    for namespace in (
        "model-a:dimensions-512",
        "model-b:dimensions-512",
        "model-b:dimensions-256",
    ):
        provider = CountingEmbeddings(namespace)
        HybridSearch(store, provider)
        assert len(provider.calls[0]) == 2
    assert cache_count(store) == 6


@pytest.mark.parametrize("mutation", ["edit", "delete"])
def test_concurrent_mutation_cannot_publish_stale_vectors(corpus, mutation):
    store, note = corpus

    def change():
        if mutation == "delete":
            store.delete(note.name)
        else:
            note.write_text("""# Changed
A new document.""")
            ingest_note(note.parent, note.name, store)

    in_flight = HybridSearch(store, CountingEmbeddings(before_embed=change))
    assert len(in_flight.snapshot.documents[0].chunks) == 2
    assert cache_count(store) == 0
    current = HybridSearch(store, CountingEmbeddings())
    assert all(
        "FAISS" not in c.text for d in current.snapshot.documents for c in d.chunks
    )


def test_parallel_requests_publish_consistently(corpus):
    store, _ = corpus
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: HybridSearch(store, CountingEmbeddings()).search("vectors"),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert cache_count(store) == 2


@pytest.mark.parametrize("bad", ["bytes", "nan", "dimensions"])
def test_invalid_cached_vector_is_rejected(corpus, bad):
    import struct

    store, _ = corpus
    HybridSearch(store, CountingEmbeddings())
    vector = {
        "bytes": b"x",
        "nan": struct.pack("<f", float("nan")),
        "dimensions": struct.pack("<f", 1.0),
    }[bad]
    chunk = store.list_documents()[0].chunks[0]
    with store.engine.begin() as connection:
        connection.execute(
            update(EmbeddingRow)
            .where(EmbeddingRow.chunk_id == chunk.id)
            .values(vector=vector)
        )
    with pytest.raises((ValueError, EmbeddingError)):
        HybridSearch(store, CountingEmbeddings())


def test_failed_provider_does_not_publish_partial_cache(corpus):
    store, _ = corpus

    class InvalidProvider(CountingEmbeddings):
        def embed(self, texts):
            return [[1.0]]  # Incorrect batch size.

    with pytest.raises(EmbeddingError):
        HybridSearch(store, InvalidProvider())
    assert cache_count(store) == 0


def test_changed_input_digest_recomputes_only_that_chunk(corpus):
    store, _ = corpus
    HybridSearch(store, CountingEmbeddings())
    chunk = store.list_documents()[0].chunks[0]
    with store.engine.begin() as connection:
        connection.execute(
            update(EmbeddingRow)
            .where(EmbeddingRow.chunk_id == chunk.id)
            .values(input_digest="older-input-format")
        )
    provider = CountingEmbeddings()
    HybridSearch(store, provider)
    assert [len(batch) for batch in provider.calls] == [1]
    assert cache_count(store) == 2


def test_legacy_database_gains_cache_without_reingestion(corpus):
    store, note = corpus
    with store.engine.begin() as connection:
        EmbeddingRow.__table__.drop(connection)
    reopened = SQLiteDocumentStore(note.parent / "notes.sqlite3")
    try:
        provider = CountingEmbeddings()
        HybridSearch(reopened, provider)
        assert len(provider.calls[0]) == 2
        assert cache_count(reopened) == 2
    finally:
        reopened.engine.dispose()


def test_cached_rankings_match_uncached_for_synthetic_queries(tmp_path):
    from scripts.evaluate_retrieval import SYNTHETIC_CASES, seed_corpus

    store = SQLiteDocumentStore(seed_corpus(tmp_path))
    try:
        uncached = HybridSearch(Snapshot(store.list_documents()), HashEmbeddings())
        HybridSearch(store, HashEmbeddings())  # Fill the persistent cache.
        cached = HybridSearch(store, HashEmbeddings())
        for _, _, question in SYNTHETIC_CASES:
            assert cached.search(question) == uncached.search(question)
    finally:
        store.engine.dispose()
