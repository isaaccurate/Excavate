# Architecture

- `api` serves FastAPI health and answer endpoints. The app factory accepts an answer service for local integration and tests.
- `cli` invokes ingestion or deletion for a single path, compares search rankings, and answers questions.
- `ingestion` validates the path, opens the selected file, decodes UTF-8, and builds a document with section chunks.
- `contracts` defines immutable Pydantic records and structural interfaces for document persistence, retrieval, embeddings, and generation.
- `storage` uses SQLAlchemy to persist documents. A conditional SQLite upsert replaces a document and its chunks in one transaction when the content digest or derived chunks differ.

`retrieval` builds an in-memory SQLite FTS5 index per lexical query. It ranks note title, heading, and body matches with BM25. FAISS ranks normalized vectors by inner product. Reciprocal rank fusion combines ranked chunk IDs with deterministic tie-breaking. `HybridSearch` binds lexical and dense search to a single document snapshot and resolves ranked passages from that snapshot. The next request rebuilds from current data.

`answer_service` connects the configured document store, hybrid search, and model providers for both `ask` and `POST /answer`. It loads retrieval dependencies when needed, so the health endpoint remains available with the base install. `answering` validates the question, builds bounded evidence from the ranked passages, and resolves validated citation IDs to source metadata. `generation` uses the OpenAI Responses API with Structured Outputs and separates trusted instructions from the question and evidence. The request uses no tools. The API returns HTTP 422 for invalid input, 503 for missing configuration, and 502 for managed provider failures or unusable outputs.

## D3 storage

The configured store implements both `DocumentStore` and `CorpusReader`. In AWS mode the selected note becomes a serialized document in S3 and a current-version pointer in DynamoDB. The pointer is written after the payload. Retrieval materializes the documents once and passes the same collection to lexical search, dense search, and citation lookup. A DynamoDB scan is consistent per item and can observe different document versions during concurrent writes. [DynamoDB Scan](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html)

AWS deletion marks the record as recoverable until a deadline and excludes it from reads. Restore clears that deadline. Cleanup claims expired records with a conditional revision, removes their tracked objects, and deletes the claimed record after S3 succeeds.
