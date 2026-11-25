# Project status

Excavate supports local and AWS storage, hybrid search, and answers with section citations. SQLite caches document embeddings during retrieval. AWS can cache them during ingestion. A React page in `frontend/` asks the local API and shows each answer's cited excerpts. The [evaluation results](testing.md) cover retrieval, cache performance, answer quality, and AWS checks.

## Next work

- Host the frontend publicly. The deployed API accepts only IAM-signed requests, so a public page needs something that signs them.
- Add held-out questions to test how well retrieval and answering generalize.
- Reconcile unpublished S3 note versions, including any embeddings bundled in them. Preserve current and recoverable versions and uploads still being published.

Managed vector search and automatic note synchronization remain deferred. The tested note-link expansion rule did not improve retrieval.
