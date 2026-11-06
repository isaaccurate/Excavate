# Testing

After installing the development and retrieval extras, run these from the project root.

```sh
python -m pytest -q
ruff check .
ruff format --check .
python -m pip check
```

## Results on November 4, 2026

- macOS with Python 3.14.8 and pytest 9.2.0. All 17 tests passed in 1.15 seconds.
- Ruff 0.17.3 passed lint and format checks. Pip found no broken requirements.
- Python 3.12.11 passed a separate smoke check for CLI ingest, unchanged ingest, delete, and the health handler. The full suite ran on Python 3.14.8.
- Coverage includes the HTTP health response, path traversal and symlink rejection, explicit selection, persistence across store instances, stable chunk IDs, invalid UTF-8 handling, and CLI behavior.

## Retrieval increment

The full suite passed on Python 3.14.8 with 19 tests in 1.15 seconds. Ruff lint and format checks passed. New coverage exercises lexical matching after edits and deletes, literal query handling, and deterministic rank fusion. Retrieval quality has yet to be measured.

## Two-note BM25 baseline

Ingested only the two user-selected Markdown files into a temporary database. The corpus contained 10 chunks. The labels below were assigned before running search.

| Query | Expected section | Rank |
| --- | --- | --- |
| What makes a resident and hospital an unstable pair? | Stable Matching → Formal Definition | 1 |
| Why can’t a hospital and a resident who prefer each other end up apart? | Stable Matching → Gale Shapley Algorithm → Proof | 1 |
| Why does equal work at every recursion level introduce a logarithmic factor? | Master Theorem → Intuition | 1 |
| When do the leaves dominate the total work of a divide-and-conquer recurrence? | Master Theorem → Intuition | 1 |

Hit@1 was 4/4. The two notes cover different topics, and two questions share a target passage. This is a small baseline for comparison with dense and hybrid search. The temporary database was removed after the run.

## Local hybrid comparison

Run `python scripts/evaluate_retrieval.py /path/to/CSE_421` from the project root after installing the retrieval extra. It reads the same two explicitly selected notes into a temporary database.

| Query target | BM25 rank | FAISS rank with token hashes | Hybrid rank |
| --- | ---: | ---: | ---: |
| Unstable pair definition | 1 | 2 | 1 |
| Stability proof | 1 | 2 | 1 |
| Equal work across recursion levels | 1 | 1 | 1 |
| Leaves dominate total work | 1 | 2 | 1 |

Hit@1 was 4/4 for BM25, 1/4 for FAISS with token hashes, and 4/4 for hybrid. Token hashing measures the offline pipeline's behavior. Semantic retrieval quality requires a managed model run and a larger labeled corpus with competing passages.

Python 3.14.8 with FAISS 1.15.1 and NumPy 2.5.4 passed all 28 tests in 1.87 seconds. Ruff lint and format checks passed, and pip found no broken requirements. Managed adapter tests used mocked HTTP responses.

## Review fixes

All 34 tests passed in 1.34 seconds on Python 3.14.8. Ruff lint and format checks passed. Regression coverage includes title-only queries across lexical, dense, and hybrid rankings, heading-only sections and their ancestry, re-ingestion of legacy records with unchanged source digests, blank notes, and CLI searches that must skip embedding requests. Earlier evaluation tables record the behavior before these retrieval changes.

## Grounded answering

All 57 tests passed in 1.65 seconds on Python 3.14.8. Ruff 0.17.3 passed lint and format checks. Pip found no broken requirements. The suite exercises the CLI and API through mocked HTTP, resolves citations after a concurrent corpus change, checks serialized evidence limits and prompt separation, and rejects malformed results, unknown citations, incomplete responses, and refusals. An empty corpus skips all managed requests. A managed embedding failure is reported without fallback. The suite uses synthetic notes and does not need credentials or contact OpenAI.

## Expanded local course corpus

Supplied the CSE_421 directory for local testing. 12 Markdown notes were ingested into data/cse421.sqlite3, yielding 52 chunks. Selection was limited to that course directory; symbolic-link directories were not followed. The database is covered by the existing *.sqlite3 ignore rule.

The four existing labeled questions were rerun with limit 5 and 20 candidates per retrieval method. Expected passage ranks were:

| Query target | BM25 | FAISS with token hashes | Hybrid |
| --- | ---: | ---: | ---: |
| Unstable pair definition | 1 | 2 | 1 |
| Stability proof | 1 | Outside top 5 | 1 |
| Equal work across recursion levels | 1 | 1 | 1 |
| Leaves dominate total work | 1 | Outside top 5 | Outside top 5 |

Hit@5 was 4/4 for BM25, 2/4 for token-hash FAISS, and 3/4 for hybrid. These measurements use local test embeddings. No paid providers were called. The earlier two-note comparisons used different corpus and candidate sizes.

## Note link pilot

Run `python -m scripts.evaluate_note_links data/cse421.sqlite3` from the project root. The pilot used 12 notes and 52 chunks with six questions labeled before scoring, two per linked note pair. The four existing single-passage questions served as controls.

Both variants return up to five passages. The prototype checks outgoing wiki links in the first three BM25 passages, resolves unique note titles within the indexed corpus, and gives the best BM25 match from a linked note the fifth slot if it is absent from the baseline. The pilot uses no model calls.

| Measure | BM25 | BM25 with one-hop expansion |
| --- | ---: | ---: |
| Both expected passages in top five | 4/6 | 4/6 |
| Expected passage in top five on controls | 4/4 | 4/4 |

Expansion changed one result list. For the maximum cut question about the two vertex sets, it replaced an unrelated matrix multiplication passage with the bipartiteness proof. The labeled definition passage still missed the top five. The small set has three distinct links and tests one expansion rule.

## Cross-course note link pilot

Run `python -m scripts.evaluate_note_links data/cse421-cse332-links.sqlite3 --cross-course`. The separate local database combines 12 selected CSE_421 notes with 9 supplied CSE_332 Graphs notes, for 21 notes and 89 passages. Cross-course links from Graph Traversal and Greedy MST Algorithms now resolve to Breadth-First Search, Depth First Search, and Spanning Tree. The same one-hop rule and five-passage budget were used.

| Measure | BM25 | BM25 with one-hop expansion |
| --- | ---: | ---: |
| Both labeled passages on five cross-course questions | 3/5 | 3/5 |
| Both labeled passages on six original linked questions | 3/6 | 3/6 |
| Labeled passage on four controls | 4/4 | 4/4 |

Expansion changed none of the five cross-course rankings. In both misses, BM25 ranked the linked BFS note's introduction second, so the expansion rule kept it. The labeled BFS layer-distance section remained outside the top five. This pilot supports deferring the tested rule. A section-aware candidate rule would be a separate experiment. No model calls were made.
## D3 storage verification

With boto3 1.43.125 installed, all 59 tests passed in 1.47 seconds. The AWS SDK stub tests cover document writes, unchanged retries, reads, pagination, deletes, and CLI handling of an S3 upload failure before DynamoDB publication. Tests used dummy credentials and synthetic text. No live AWS resources were used.

## D3 recovery and cleanup verification

All 65 tests passed in 2.00 seconds. Ruff lint and format checks passed. The AWS stubs cover hiding and restoring notes, a seven-day deadline, preservation of current and recent payloads, reading legacy pointer records during replacement, stale cleanup after restore, partial purge and retry, CLI cleanup, and rejection of a versioned bucket. No live AWS calls or scheduled jobs ran.

## Migration commit review

On November 6, 2026, all 68 tests passed in 2.18 seconds. Ruff lint and format checks passed, and pip found no broken requirements. Added coverage verifies failed conditional publication after an S3 upload, checksum rejection for corrupted payloads, and the answer API retrieving evidence from stubbed AWS storage without a SQLite database. Orphan-upload reconciliation, deployed scheduling, and live AWS verification remain pending.

## Live AWS storage smoke test

In `us-east-2`, the `excavate` browser-sign-in profile ran the CLI against a private, unversioned S3 bucket and an on-demand DynamoDB test table. Two synthetic notes verified ingestion, unchanged re-ingestion, search with local embeddings, replacement, recoverable delete, restore, and purge. A test-only change to one deleted record's recovery deadline verified that cleanup removed the expired note while preserving the active note. Final checks found zero records in the test table and zero objects under both test note prefixes. The bucket and table remain available for testing.

The run used the project sign-in role. Scoped IAM roles, a deployed cleanup schedule, and live answer generation were outside this test. The AWS package extra now includes the Boto3 runtime for browser-sign-in profiles.

## Deployed Lambda smoke test

The Ohio CodeBuild image passed FAISS imports, Lambda handler imports, and FTS5 table creation. CloudFormation Linter passed for both templates. The deployed Function URL returned 403 without a signature and 200 for signed health checks. A signed answer request returned 503 with model setup missing. No model calls were made.

The deployed cleanup function erased a synthetic expired note and its S3 object while preserving an active test note. The test then purged that active note and verified empty note storage. IAM simulation with the Ohio Region context allowed API reads and denied the tested S3 deletes and writes and DynamoDB writes. After enabling the hourly schedule, CloudWatch recorded a successful scheduled invocation. All 68 local tests passed.

## Live OpenAI answer smoke test

On November 6, 2026, the Ohio stack was configured with `gpt-6-luna` and a Secrets Manager reference. The first signed answer request returned 502. After deploying sanitized provider logging, a second test confirmed the OpenAI Responses API returned HTTP 401.

After updating the AWS secret to contain the raw API key as plaintext, a signed request returned 200 with the expected synthetic access code and a citation to the source file and its `Observatory Access` heading. Signed and unsigned health checks returned 200 and 403, respectively. This test used local embeddings and one synthetic note.

Each fixture was purged, and each cleanup verified zero DynamoDB records and zero S3 note objects. The hourly schedule was enabled after the image update. The local suite passed all 68 tests, including checks that provider error logs exclude private input and response text. Ruff lint and format checks passed.
