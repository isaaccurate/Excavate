# Architecture

- `api` serves FastAPI health and answer endpoints. The app factory accepts an answer service for local integration and tests.
- `cli` invokes ingestion or deletion for a single path, compares search rankings, and answers questions.
- `ingestion` validates the path, opens the selected file, decodes UTF-8, and builds a document with section chunks.
- `contracts` defines immutable Pydantic records and structural interfaces for document persistence, retrieval, embeddings, and generation.
- `storage` uses SQLAlchemy to persist documents. A conditional SQLite upsert replaces a document and its chunks in one transaction when the content digest or derived chunks differ.

`retrieval` builds an in-memory SQLite FTS5 index per lexical query. It ranks note title, heading, and body matches with BM25. FAISS ranks normalized vectors by inner product. Reciprocal rank fusion combines ranked chunk IDs with deterministic tie-breaking. `HybridSearch` binds lexical and dense search to a single document snapshot and resolves ranked passages from that snapshot. The next request rebuilds from current data.

`answer_service` connects SQLite, hybrid search, and configured providers for both `ask` and `POST /answer`. It loads retrieval dependencies when needed, so the health endpoint remains available with the base install. `answering` validates the question, builds bounded evidence from the ranked passages, and resolves validated citation IDs to source metadata. `generation` uses the OpenAI Responses API with Structured Outputs and separates trusted instructions from the question and evidence. The request uses no tools. The API returns HTTP 422 for invalid input, 503 for missing configuration, and 502 for managed provider failures or unusable outputs.
