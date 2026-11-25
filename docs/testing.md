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

For the frontend, run `npm test` and `npm run build` in `frontend/`. The tests cover response validation, error messages, math conversion, and citation helpers.

## Verified checks

On November 18, 2026, all 89 tests passed on Python 3.14.8, along with Ruff lint and formatting checks. Coverage includes safe file selection, heading preservation, note updates, cache reuse and invalidation, concurrent writes, citation validation, provider failures, and AWS note recovery and cleanup.

Live AWS smoke tests verified note updates, delete and restore, scheduled cleanup, and IAM-protected API access. One live answer returned the expected source citation. Temporary test notes were removed afterward.

## Reviewed retrieval evaluation

The evaluation uses 44 hand-written questions and real `text-embedding-3-small` embeddings. Logistic regression uses 5 selected notes (22 sections), and network flow uses 3 selected notes (9 sections). Each dataset is searched independently, with 5 results and 20 candidates per method.

| Ranking | Evidence Recall@5 | Hit@5 | Full required evidence@5 | MRR@5 |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.931 | 35/36 | 32/36 | 0.633 |
| FAISS | 0.958 | 35/36 | 34/36 | 0.817 |
| Hybrid | 0.972 | 35/36 | 35/36 | 0.789 |

Scores cover the 36 answerable questions. Recall measures the fraction of required evidence groups retrieved, averaged across questions. A group can accept alternative supporting sections. MRR@5 measures the reciprocal rank of the first relevant section, averaged across questions.

These are development scores on reviewed labels. There is no held-out set. See the [question sets](../evaluations/) and [per-question rankings](../evaluations/results/).

## SQLite cache benchmark

Each of the 44 questions ran twice locally, once per cache setting. Each request reopened SQLite and rebuilt both indexes. The paired runs alternated order and shared an HTTP connection pool. The populated-cache figures exclude one warm-up per dataset (5,955 input tokens combined).

| Metric across 44 requests | Cache disabled | Cache populated |
| --- | ---: | ---: |
| Median retrieval latency | 541.5 ms | 243.5 ms |
| p95 retrieval latency | 1003.9 ms | 470.5 ms |
| Embedding HTTP calls | 88 | 44 |
| Document chunks embedded | 656 | 0 |
| Queries embedded | 44 | 44 |
| Reported embedding input tokens | 129,015 | 595 |
| Estimated standard embedding cost | $0.0025803 | $0.0000119 |

Median retrieval latency fell 55% in this single local pass. All rankings matched across cache settings. Timings exclude answer generation and AWS. Estimated costs use $0.02 per million embedding input tokens.

## AWS cache benchmark

The same deployed Lambda image answered three network-flow questions three times per cache setting. Both runs used the same nine sections. The first invocation in each setting reported an initialization time. The remaining eight per setting were warm.

| Metric | Uncached | Cached |
| --- | ---: | ---: |
| Embedding requests across nine answers | 18 | 9 |
| Embedding input tokens across nine answers | 22,233 | 93 |
| Median warm request, including generation | 7.68 s | 6.94 s |
| First request, including initialization and generation | 16.01 s | 8.28 s |

All nine pairs had identical BM25, FAISS, and hybrid rankings and the same answer or abstention status. Six pairs had identical citation lists. The other three were repeats of `nf-012`, where the model kept the proof citation and varied the supporting citations. The small sample and generation latency limit the timing comparison. [Per-request results](../evaluations/results/aws_cache_benchmark.json)

## Answers and AWS smoke test

Using `gpt-6-luna` and the same embedding model, all 36 answerable questions returned valid citation IDs. Human review judged 34 answers acceptable and two partial. All eight unanswerable questions returned `insufficient_evidence`. The model received only the question and retrieved evidence.

- `nf-004` omitted the requirement that residual capacity be positive.
- `nf-012` omitted the zero reverse-flow condition. The supplied proof excerpt ended before that step.

Six IAM-signed AWS requests matched the local outcomes (four answers, two abstentions). All returned HTTP 200 and cited only supplied evidence where applicable. Test notes were purged afterward. [Cloud smoke report](../evaluations/results/cloud_answers_smoke.json)

## Long-section regression

Splitting the Ford–Fulkerson proof put both the saturation and zero reverse-flow conditions in one retrievable passage. That passage ranked first for `nf-012`. The focused local answer and the signed AWS answer both included and cited the missing condition.

The 44-question retrieval rerun found the same hybrid Hit@5 (35/36). Full required evidence fell from 35/36 to 34/36. For `nf-011`, two chunks of the same proof entered the top five and displaced a required section. Logistic-regression retrieval scores were unchanged.

The answer rerun returned answers for 35 of 36 answerable questions and abstained on all eight unanswerable questions. The one unexpected abstention, `lr-012`, used the same five passages as the original successful answer. [Post-split evaluation](../evaluations/results/long_section_evaluation.json)

## Reproduce the evaluation

Set `OPENAI_API_KEY`. Choose the directory containing the selected source notes and the matching label file. The evaluator sends note sections and questions to OpenAI. The repository includes labels and reports. Supply the original notes separately.

```sh
notes_root=/path/to/logistic-regression-notes
labels=evaluations/logistic_regression.json
python -m scripts.evaluate_retrieval "$notes_root" \
  --dataset "$labels" --embedding-model text-embedding-3-small
```

For network flow, use its notes directory and `evaluations/network_flow.json`. Append `--benchmark --repeats 1` for the paired cache run or `--answer-model gpt-6-luna` for generated answers. The answer evaluator includes excerpts in its output. The committed reports retain excerpt hashes and lengths.
