# Progress

## Working today

- Index selected Markdown files, preserve their headings, and update or remove indexed notes through the CLI.
- Search with BM25, FAISS, and combined rankings. Local test embeddings work without credentials.
- Answer through the CLI or FastAPI with citations to retrieved notes and sections.
- Store notes locally in SQLite or in AWS using S3 and DynamoDB.
- Run the API on Lambda with IAM authentication, keep deleted notes recoverable for seven days, and clean up expired content hourly.

Local tests cover ingestion, retrieval, answering, and storage failures. AWS smoke tests verified note recovery, scheduled cleanup, and a six-question cloud answer check. The 44-question local generation run passed all eight abstention cases, with two answers still marked partial after user review of the initially flagged responses. See [testing](testing.md) for the recorded results.

## Next work

- Extend embedding caching to AWS with version tracking and retention. SQLite now persists document embeddings across requests and processes. Indexes still rebuild for each request.
- Expand the reviewed evaluation with a holdout set. The 44-question real-embedding baseline and reviewed label corrections are recorded in testing.
- Find and remove S3 uploads left behind when publishing their DynamoDB records fails.
- Evaluate managed vector search and check that it preserves retrieval results and citations.

## Deferred

The note-link experiments found no improvement from the tested expansion rule, so link expansion remains outside production retrieval. The results are in [testing](testing.md#note-link-pilot).

Full Markdown parsing, splitting long sections, and automatic note synchronization remain future work. The current parser supports ATX headings and fenced code blocks.
