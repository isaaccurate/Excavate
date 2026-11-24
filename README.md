# Excavate

Excavate answers questions about selected Obsidian notes and cites the note and section behind each answer. It combines keyword search (BM25) and vector search (FAISS), then uses a language model to draft an answer from the retrieved passages.

## Run locally

Requires Python 3.12+ on macOS or Linux.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[retrieval]'
```

Index a Markdown file by giving its path relative to your vault, then search it. Local search uses SQLite and runs without an API key.

```sh
knowledge-assistant ingest --root /path/to/vault "Projects/Example.md"
knowledge-assistant search "What does the project cover?"
```

Excavate indexes only the files you select. Re-run `ingest` after editing a note, or run `knowledge-assistant delete "Projects/Example.md"` to remove it from the index.

## Ask a question

Set `OPENAI_API_KEY` in your environment, then run:

```sh
knowledge-assistant ask --openai-model gpt-6-luna "What does the project cover?"
```

Excavate sends the question and selected note excerpts to OpenAI. If the excerpts don't contain enough evidence, it can return `insufficient_evidence`.

## Repository structure

```text
Excavate/
├── knowledge_assistant/
│   ├── cli.py               # Command-line entry point
│   ├── api.py               # FastAPI routes
│   ├── ingestion.py         # Markdown parsing and section IDs
│   ├── hybrid.py            # Combined keyword and vector search
│   └── answer_service.py    # Retrieval and answer generation
├── scripts/
│   └── evaluate_retrieval.py
├── evaluations/             # Labeled question sets
│   └── results/             # Retrieval, cache, and answer reports
├── frontend/                # React page for asking questions
├── tests/                   # Automated tests
├── docs/                    # Usage, design, and testing guides
├── deploy/                  # Docker and AWS templates
└── pyproject.toml           # Dependencies and project settings
```

[Usage](docs/usage.md) · [Frontend](frontend/README.md) · [Architecture](docs/architecture.md) · [Design decisions](docs/decisions.md) · [Testing and benchmarks](docs/testing.md) · [Next steps](docs/progress.md) · [Deployment](deploy/README.md)
