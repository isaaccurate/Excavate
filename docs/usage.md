# Using Excavate

Start with the [README](../README.md) for installation and the basic CLI workflow.

## Commands

Run each command after `knowledge-assistant`.

| Command | What it does |
| --- | --- |
| `ingest --root /path/to/vault "Note.md"` | Index or update one selected note. |
| `search "question"` | Show matching sections and compare search rankings. |
| `ask --openai-model MODEL "question"` | Generate an answer with source citations. |
| `delete "Note.md"` | Remove a note from local storage, or hide it for seven-day recovery in AWS. |
| `restore "Note.md"` | Recover a deleted AWS note before its deadline. |
| `purge "Note.md"` | Permanently erase an AWS note's tracked copies. |
| `cleanup` | Remove expired AWS notes and old versions. |

Use `knowledge-assistant --help` to list commands, or add `--help` after a command to see its options.

## Select and update notes

Ingest one UTF-8 Markdown file at a time, using forward slashes in the path relative to the vault root. Use one vault per database and keep path spelling consistent. The local CLI defaults to `knowledge.sqlite3`. Put `--db /path/to/notes.sqlite3` before the command to select a different database.

Re-run `ingest` to update a note. After a rename, ingest the new path and delete the old one. These commands leave the original files in your vault. SQLite stores selected note text in plaintext. If you indexed notes before heading-only sections were supported, re-ingest them to pick up those sections.

## Search and answer

Search compares BM25, FAISS, and combined rankings and prints source paths, headings, and chunk IDs. Both search and answering use local token-hash vectors by default. Each invocation of `search` or `ask`, or request to `POST /answer`, rebuilds the search indexes from the current corpus.

For semantic embeddings, set `OPENAI_API_KEY` and pass `--openai-model text-embedding-3-small` to `search` or `--embedding-model text-embedding-3-small` to `ask`. The API equivalent is `KNOWLEDGE_ASSISTANT_EMBEDDING_MODEL`. This sends the question and all indexed chunks, including their filename stems and headings, to OpenAI on each search.

Answer generation uses the OpenAI Responses API with Structured Outputs. It sends the question and selected excerpts with their paths and headings. The result includes an answer and citations with source paths, headings, and chunk IDs. Excavate checks that each cited ID was supplied to the model. Review the cited text to verify that it supports the claims. An `insufficient_evidence` result has a null answer and an empty citations list. [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)

## Use the local API

With `OPENAI_API_KEY` set, point the server at the SQLite database created by ingestion:

```sh
KNOWLEDGE_ASSISTANT_DB=knowledge.sqlite3 \
KNOWLEDGE_ASSISTANT_OPENAI_MODEL=gpt-6-luna \
uvicorn knowledge_assistant.api:app
```

From another terminal:

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"What does the project cover?"}'
```

The health route checks that the process is running. The local server has no authentication. The deployed API requires IAM-signed requests.

## Manage notes in AWS

Install the AWS extra and configure the CLI to use an existing private, unversioned S3 bucket and a dedicated DynamoDB table with a string partition key named `document_id` and no sort key. The profile or role needs access to the bucket's `documents/` prefix and the table. The AWS extra supports browser sign-in profiles.

```sh
python -m pip install -e '.[retrieval,aws]'
export AWS_PROFILE=excavate
export AWS_DEFAULT_REGION=us-east-2
export KNOWLEDGE_ASSISTANT_STORAGE=aws
export KNOWLEDGE_ASSISTANT_S3_BUCKET=YOUR_BUCKET
export KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE=YOUR_TABLE
```

Use the same `ingest`, `search`, and `ask` commands as in local mode. In AWS mode, ingestion uploads the selected note's parsed text and source path to S3. Set `KNOWLEDGE_ASSISTANT_STORAGE=sqlite` to return to local storage.

In AWS mode, `delete` hides a note and starts a seven-day recovery window. Repeating it keeps the original deadline. Use `restore` before that deadline, or `purge` to erase tracked copies immediately. The deployed hourly job runs `cleanup`, which erases expired deleted notes and versions replaced by edits at least seven days earlier. Untracked objects left by an interrupted write still need separate reconciliation.

For stack setup and smoke testing, see the [deployment guide](../deploy/README.md).
