# Project status

Excavate supports local and AWS storage, hybrid search, and answers with section citations. SQLite caches document embeddings across requests. The [evaluation results](testing.md) cover local retrieval, cache performance, answer quality, and a six-request AWS smoke test.

## Next work

- Cache document embeddings in AWS and measure repeated requests against the deployed baseline.
- Split long sections so answer generation can use evidence beyond the current excerpt limit. The network-flow proof in `nf-012` is a regression case.
- Add held-out questions to test how well retrieval and answering generalize.
- Reconcile S3 uploads left behind when DynamoDB publication fails.

Managed vector search and automatic note synchronization remain deferred. The tested note-link expansion rule did not improve retrieval.
