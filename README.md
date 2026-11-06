# Knowledge Assistant

Local backend for answering questions from explicitly selected Obsidian Markdown notes.

## Run locally

Use Python 3.12 or later on macOS or Linux.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,retrieval]'
uvicorn knowledge_assistant.api:app
```

`GET /health` returns `{"status":"ok"}`. It is a process health check.

## Manage notes

```sh
knowledge-assistant --db knowledge.sqlite3 ingest --root /path/to/vault "Projects/Example.md"
knowledge-assistant --db knowledge.sqlite3 delete "Projects/Example.md"
```

Run ingestion once per selected UTF-8 Markdown file. Paths are relative to the supplied root and use forward slashes. Keep one vault per database and use consistent path spelling. Re-run ingestion to update a note. Delete its stored path after removing it, or ingest the new path and delete the old path after renaming it. The database stores selected note text in plaintext.

## Compare retrieval modes

```sh
knowledge-assistant --db knowledge.sqlite3 search "How does the algorithm terminate?"
```

Search includes note titles, heading ancestry, and body text. Search shows BM25, FAISS, and hybrid rankings with source paths, headings, and chunk IDs. The default uses local token-hash vectors for testing the pipeline. For semantic embeddings, set `OPENAI_API_KEY` and add `--openai-model text-embedding-3-small`. This explicitly sends all stored chunks in the selected database and the query to OpenAI. Search rebuilds its snapshot on each CLI invocation.

Notes ingested before heading-only sections were supported need re-ingestion to recover those sections. Existing stored notes gain title search on their next search invocation. Blank queries and zero-result requests return empty rankings before any embedding requests.

## Ask a question

Set `OPENAI_API_KEY` and choose an OpenAI model that supports Structured Outputs in the Responses API. Replace `YOUR_GENERATION_MODEL` below with that model's API ID. [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)

```sh
knowledge-assistant --db knowledge.sqlite3 ask --openai-model YOUR_GENERATION_MODEL \
  "How does the algorithm terminate?"
```

The CLI prints JSON with `status`, `answer`, and `citations`. An answered result cites stored chunk IDs, note paths, and heading ancestry. An `insufficient_evidence` result has a null answer and an empty citations array. The application checks that each cited ID was in the evidence sent to the model. Assessing whether the cited text supports each claim still requires reviewing the sources.

For API access, start the server with the same key and set the database and generation model explicitly. The server is intended for local use and has no authentication.

```sh
KNOWLEDGE_ASSISTANT_DB=knowledge.sqlite3 \
KNOWLEDGE_ASSISTANT_OPENAI_MODEL=YOUR_GENERATION_MODEL \
uvicorn knowledge_assistant.api:app

curl http://127.0.0.1:8000/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does the algorithm terminate?"}'
```

By default, retrieval uses BM25 with local token-hash vectors for testing the pipeline. For semantic retrieval, add `--embedding-model text-embedding-3-small` to `ask` or set `KNOWLEDGE_ASSISTANT_EMBEDDING_MODEL` for the API. This sends the question and all stored chunks with filename stems and headings to OpenAI for embeddings on each request. Generation always sends the question and selected passage excerpts, including their paths and headings. Use these options only with notes you intend to send.

See [architecture](docs/architecture.md), [decisions](docs/decisions.md), [testing](docs/testing.md), and [progress](docs/progress.md).
