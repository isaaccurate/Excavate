# Project status

Excavate supports local and AWS storage, hybrid search, and answers with section citations. SQLite caches document embeddings during retrieval. AWS can cache them during ingestion. A React page in `frontend/` asks the API and shows each answer's cited excerpts. It is [hosted on CloudFront](https://d3ljbmvvwxow49.cloudfront.net), which signs requests to the deployed API. The [evaluation results](testing.md) cover retrieval, cache performance, answer quality, and AWS checks.

## Next work

- Add held-out questions to test how well retrieval and answering generalize.
- Reconcile unpublished S3 note versions, including any embeddings bundled in them. Preserve current and recoverable versions and uploads still being published.

Managed vector search and automatic note synchronization remain deferred. The tested note-link expansion rule did not improve retrieval.
