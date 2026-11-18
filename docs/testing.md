# Testing

Install the test dependencies and run the checks from the project root. The automated suite uses synthetic notes and mocked providers.

```sh
python -m pip install -e '.[dev,retrieval,aws]'
python -m pytest -q
ruff check .
ruff format --check .
python -m pip check
```

`pytest` runs the automated tests. `ruff check` checks code style and common mistakes, while `ruff format --check` checks formatting. `pip check` checks that installed dependencies are compatible.

## Verified checks

On November 18, 2026, all 88 tests passed on Python 3.14.8, along with Ruff lint and formatting checks. Coverage includes safe file selection, heading preservation, note updates, cache reuse and invalidation, concurrent writes, citation validation, provider failures, and AWS note recovery and cleanup.

Live AWS smoke tests verified note updates, delete and restore, scheduled cleanup, and IAM-protected API access. One live answer returned the expected source citation. Temporary test notes were removed afterward.

## Reviewed retrieval evaluation

The evaluation uses 44 hand-written questions and real `text-embedding-3-small` embeddings. Logistic regression uses 5 selected notes (22 sections), and network flow uses 3 selected notes (9 sections). Each dataset is searched independently, with 5 results and 20 candidates per method.

| Ranking | Evidence Recall@5 | Hit@5 | Full required evidence@5 | MRR@5 |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.931 | 35/36 | 32/36 | 0.633 |
| FAISS | 0.958 | 35/36 | 34/36 | 0.817 |
| Hybrid | 0.972 | 35/36 | 35/36 | 0.789 |

Scores cover the 36 answerable questions. Recall measures the fraction of required evidence groups retrieved, averaged across questions. A group can accept alternative supporting sections. MRR@5 measures the reciprocal rank of the first relevant section, averaged across questions.

The eight unanswerable questions have saved rankings. Answer quality and abstention evaluation are pending. Original labels, original reports, and revised scores remain available in `evaluations/revisions/` and `evaluations/results/` for audit.

With `OPENAI_API_KEY` set, run each dataset against its selected note directory. The commands send note sections and questions to OpenAI.

```sh
python -m scripts.evaluate_retrieval "$LOGISTIC_NOTES_ROOT" \
  --dataset evaluations/logistic_regression.json --embedding-model text-embedding-3-small
python -m scripts.evaluate_retrieval "$FLOW_NOTES_ROOT" \
  --dataset evaluations/network_flow.json --embedding-model text-embedding-3-small
```

## Note link pilot

The earlier link-expansion pilot found no improvement from the tested rule. Link expansion remains deferred. The experiment is implemented in `scripts/evaluate_note_links.py`.

## Real embedding cache benchmark

The same 44 course-note questions were run locally with `text-embedding-3-small`, once with document caching disabled and once with it enabled. Each request reopened SQLite and rebuilt its search indexes. Paired requests alternated execution order and shared an HTTP connection pool. One initial request per corpus populated the cache before the paired measurements.

| Metric across 44 requests | Cache disabled | Cache populated |
| --- | ---: | ---: |
| Median retrieval latency | 541.5 ms | 243.5 ms |
| p95 retrieval latency | 1003.9 ms | 470.5 ms |
| Embedding HTTP calls | 88 | 44 |
| Document chunks embedded | 656 | 0 |
| Queries embedded | 44 | 44 |
| Reported embedding input tokens | 129,015 | 595 |
| Estimated standard embedding cost | $0.0025803 | $0.0000119 |

In this run, median retrieval latency decreased 55.0%, API calls decreased 50%, and repeated-request token usage decreased 99.5%. All BM25, FAISS, and hybrid rankings matched between modes and matched the original real-embedding evaluation.

The two initial cache-population requests took 1786.4 ms for logistic regression and 538.0 ms for network flow, using 5,955 tokens combined. These individual cache-population observations are excluded from the repeated-request table.

Cost estimates use $0.02 per million embedding input tokens and exclude generation, AWS services, and billing credits. The repeated-request table excludes the one-time cache-population cost. [OpenAI embedding model pricing](https://developers.openai.com/api/docs/models/text-embedding-3-small)

This is a single local pass with 44 paired requests over two small, fixed corpora. Network variation and HTTP connection reuse affect timings. These measurements exclude ingestion, imports, answer generation, and the deployed AWS request path.

Run either selected corpus with the corresponding labels, after setting `OPENAI_API_KEY`:

```sh
python -m scripts.evaluate_retrieval "$LOGISTIC_NOTES_ROOT" \
  --dataset evaluations/logistic_regression.json \
  --embedding-model text-embedding-3-small --benchmark --repeats 1
python -m scripts.evaluate_retrieval "$FLOW_NOTES_ROOT" \
  --dataset evaluations/network_flow.json \
  --embedding-model text-embedding-3-small --benchmark --repeats 1
```

Per-request timings, calls, tokens, and ranking IDs are saved in `evaluations/results/*_cache_benchmark.json`.
