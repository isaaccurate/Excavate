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

## Verified results

On November 6, 2026, all 68 tests passed on Python 3.14.8, along with Ruff lint and formatting checks. Earlier checks also verified basic ingestion, deletion, and health behavior on Python 3.12.

The suite covers safe file selection, heading preservation, incremental updates, retrieval, citation validation, provider failures, and AWS note recovery and cleanup.

Live AWS tests verified note updates, delete and restore, scheduled cleanup, and IAM-protected API access. A live answer test with `gpt-6-luna` returned the expected answer and source citation for one synthetic note. Temporary test notes were removed and storage was verified empty afterward.

## Retrieval experiments

These recorded experiments used local token-hash embeddings. They measure the test pipeline's behavior. Quality with real semantic embeddings still needs evaluation.

| Corpus | Questions | BM25 | FAISS | Hybrid |
| --- | ---: | ---: | ---: | ---: |
| 2 notes, 10 sections | 4 | 4/4 at rank 1 | 1/4 at rank 1 | 4/4 at rank 1 |
| 12 notes, 52 sections | 4 | 4/4 in top 5 | 2/4 in top 5 | 3/4 in top 5 |

The two-note run can be repeated with `python scripts/evaluate_retrieval.py /path/to/CSE_421`. It reads the two selected course notes into a temporary database. These are small historical comparisons, and later retrieval changes require fresh measurements.

## Note link pilot

We tested whether following links between notes improved retrieval. On 12 notes, both BM25 and link expansion found both expected passages for 4 of 6 questions. An expanded test on 21 notes found no improvement on five cross-course questions. The tested rule remains outside production retrieval.

Run `python -m scripts.evaluate_note_links /path/to/notes.sqlite3` against the selected course corpus. Add `--cross-course` for the expanded experiment. The labels and expected note paths are defined in the script.

## Still to verify

A larger set of manually labeled questions and real semantic embeddings is needed to assess retrieval and answer quality. The successful live answer test confirms that the deployed components work together on one example.
