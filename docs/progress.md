# Progress

## Working today

- Index selected Markdown files, preserve their headings, and update or remove indexed notes through the CLI.
- Search with BM25, FAISS, and combined rankings. Local test embeddings work without credentials.
- Answer through the CLI or FastAPI with citations to retrieved notes and sections.
- Store notes locally in SQLite or in AWS using S3 and DynamoDB.
- Run the API on Lambda with IAM authentication, keep deleted notes recoverable for seven days, and clean up expired content hourly.

Local tests cover ingestion, retrieval, answering, and storage failures. AWS smoke tests verified note recovery, scheduled cleanup, and one live model answer with the expected citation. See [testing](testing.md) for the recorded results.

## Next work

- Save embeddings and search indexes so requests can reuse them. Currently, each request rebuilds the indexes, and managed embeddings repeat work across the corpus.
- Evaluate real semantic embeddings with a larger set of manually labeled questions.
- Find and remove S3 uploads left behind when publishing their DynamoDB records fails.
- Evaluate managed vector search and check that it preserves retrieval results and citations.

## Deferred

The note-link experiments found no improvement from the tested expansion rule, so link expansion remains outside production retrieval. The results are in [testing](testing.md#note-link-pilot).

Full Markdown parsing, splitting long sections, and automatic note synchronization remain future work. The current parser supports ATX headings and fenced code blocks.
