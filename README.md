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

Excavate sends the question and selected note excerpts to OpenAI. If the excerpts don't contain enough evidence, it can return `insufficient_evidence`. See the [usage guide](docs/usage.md) for the FastAPI server, optional semantic embeddings, and note storage details.

## Deployment

Excavate runs on AWS Lambda with IAM authentication and stores indexed notes in S3 and DynamoDB. [Deployment guide](deploy/README.md)

See [architecture](docs/architecture.md) for the retrieval and storage design, and [testing](docs/testing.md) for local checks and AWS smoke test results.
