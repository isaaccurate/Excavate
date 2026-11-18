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

On November 18, 2026, all 74 tests passed on Python 3.14.8, along with Ruff lint and formatting checks. Coverage includes safe file selection, heading preservation, note updates, citation validation, provider failures, and AWS note recovery and cleanup.

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
