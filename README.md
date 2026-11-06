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

## D3 AWS storage preview

SQLite remains the default. The optional AWS backend works with an existing private, unversioned S3 bucket and a dedicated DynamoDB table with a string partition key named `document_id` and no sort key. Use an AWS credential profile or role with access to the bucket's `documents/` prefix and the table. If you signed in with `aws login --profile excavate`, set `AWS_PROFILE=excavate`. The AWS extra installs the runtime required for browser-sign-in credentials.

```sh
python -m pip install -e '.[dev,retrieval,aws]'
export AWS_DEFAULT_REGION=us-east-2
export KNOWLEDGE_ASSISTANT_STORAGE=aws
export KNOWLEDGE_ASSISTANT_S3_BUCKET=YOUR_BUCKET
export KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE=YOUR_TABLE
knowledge-assistant ingest --root /path/to/vault "Projects/Example.md"
knowledge-assistant search "What does the project cover?"
```

AWS mode sends each selected note's parsed text and source path to your bucket. It uses the same CLI and API configuration for search and answering, with AWS storage in place of the local database. Use `KNOWLEDGE_ASSISTANT_STORAGE=sqlite` to return to local storage. Start a live smoke test with synthetic notes. Normal ingest and retrieval use S3 `GetObject` and `PutObject`. DynamoDB uses `GetItem`, `PutItem`, `Scan`, and `DeleteItem`.

Each search scans the table and fetches the current payloads before building the in-process BM25 and FAISS indexes. The adapter has been verified with AWS SDK stubs.

### Delete, restore, and cleanup

In AWS mode, `delete` hides a note and starts a seven-day recovery window. Repeating delete keeps the original deadline. `restore` makes the last indexed version searchable again before that deadline. `purge` skips recovery and erases tracked payloads. These commands leave the source file in your vault.

```sh
knowledge-assistant delete "Projects/Example.md"
knowledge-assistant restore "Projects/Example.md"
knowledge-assistant cleanup
```

Schedule `knowledge-assistant cleanup` hourly in your deployment environment using the AWS settings above and the cleanup role. For example, configure these environment variables in the job and use `0 * * * * /path/to/.venv/bin/knowledge-assistant cleanup` in cron. Expired content is erased on the next successful run. The job also removes payloads seven days after an edit replaces them. The AWS deployment uses EventBridge Scheduler. See the [deployment guide](deploy/README.md).

The cleanup role needs S3 `GetBucketVersioning` on the bucket, `DeleteObject` on its document prefix, and DynamoDB `Scan`, `PutItem`, and `DeleteItem` on the table. For manual `purge`, also grant `GetItem`. Cleanup requires an unversioned bucket so a successful S3 delete erases the object. A failed DynamoDB publication after a successful upload can leave an untracked object. Cleanup covers tracked payloads. Reconciliation of untracked objects is pending.
