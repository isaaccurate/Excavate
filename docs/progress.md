# Progress

1. **Local backend foundation.** FastAPI health endpoint, typed contracts, explicit Markdown ingestion, SQLite persistence, and CLI updates and deletes.
2. **Hybrid retrieval and evaluation.** Corpus snapshots, BM25, FAISS, reciprocal rank fusion, a managed embedding adapter, and a local evaluation harness are implemented. Managed semantic quality evaluation is pending.
3. **Grounded answering.** The CLI and local API can retrieve passages and request a structured answer with validated source IDs or an explicit insufficient-evidence result. OpenAI generation and optional semantic embeddings require explicit configuration. The answering flow has been verified offline with synthetic notes and mocked providers. Live generation and semantic answer quality evaluation are pending.

The section splitter handles ATX headings and fenced code. Full Markdown parsing, long-section splitting, automatic synchronization, and index integration are deferred.

Review fixes completed for title search, heading-only content, and empty-search embedding avoidance. Verification includes migration by re-ingestion of existing records.

## Planned experiment for note links

The CSE_421 corpus has three visible links between selected notes. Divide and Conquer links to Euclidean Closest Pair, and both Graph Traversal and Greedy Graph Approximation Algorithms link to Bipartite Testing. These are starting points for test questions. Other observed targets include attachments and notes outside the selected corpus.

1. Label questions that need evidence from both sides of a link. Keep the existing single-passage questions as a control. Record the expected sections before tuning retrieval.
2. Run a local BM25 baseline. Record whether both expected passages appear in the top five for each two-note question, and whether the expected passage appears for each control.
3. Prototype one-hop expansion from the highest-ranked passages. Resolve links only within the indexed corpus, skip ambiguous targets, and give linked passages a small candidate budget.
4. Compare with the baseline at the same result limit. Report per-question changes and inspect which relevant passages get displaced. Enable expansion by default only if the improvement holds beyond the initial examples.

The next task is to label the evaluation questions. The experiment uses the local course database and needs no paid model calls.

The pilot is complete. Both methods retrieved both expected passages for four of six linked questions and the expected passage for all four controls. Keep link expansion out of production retrieval. Revisit it if a larger set of linked notes and questions reveals recurring misses that expansion could address.

The expanded CSE_421 and CSE_332 Graphs pilot also found no gain from the tested expansion rule. The linked BFS note was retrieved on both cross-course misses, but the labeled layer-distance section stayed outside the top five. Keep production retrieval as is pending evidence for a rule that improves passage selection.

## D3 AWS migration

1. **Storage adapter implemented.** CLI and API can select S3 and DynamoDB storage through configuration. AWS SDK stubs verify lifecycle operations and a failed upload. Local mode remains the default.
2. **Next.** Recoverable delete, restore, and retryable cleanup are implemented and verified with stubs. Define infrastructure, schedule cleanup with its own AWS role, and set a cost budget. Run a live smoke test with synthetic data and reconcile untracked uploads before migrating selected notes.
3. **Managed retrieval.** Evaluate a managed vector backend, persist embeddings with their model and document versions, and check retrieval and citation parity before deployment.
