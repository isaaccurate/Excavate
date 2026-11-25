# Excavate frontend

A standalone single-page React app for asking Excavate a question and reading
the answer with the note sections behind it. It talks to the local FastAPI
server over `POST /answer` through the Vite development proxy.

The browser never holds a provider key. `OPENAI_API_KEY` and any AWS settings
stay in the backend process; the page posts a question and receives an answer.

## Run it

Requires Node.js 22.12 or newer. Use two terminals, both from the repository root.

Start the backend first, pointing it at a database you have ingested notes
into (see [docs/usage.md](../docs/usage.md) for ingestion):

```sh
source .venv/bin/activate
export OPENAI_API_KEY=...
KNOWLEDGE_ASSISTANT_DB=knowledge.sqlite3 \
KNOWLEDGE_ASSISTANT_OPENAI_MODEL=gpt-6-luna \
uvicorn knowledge_assistant.api:app
```

Then the page:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Requests to `/answer` and `/health` are forwarded
to `http://127.0.0.1:8000`. Point the proxy somewhere else with
`VITE_API_TARGET=http://127.0.0.1:9000 npm run dev`.

| Script | What it does |
| --- | --- |
| `npm run dev` | Development server with the API proxy. |
| `npm test` | Run the unit tests once. |
| `npm run typecheck` | Type-check without emitting. |
| `npm run build` | Type-check, then build into `dist/`. |
| `npm run preview` | Serve the built output, with the same API proxy. |

The proxy exists only in these local servers. A deployed build needs `/answer`
served from its own origin, which is part of the hosting decision below.

Error messages are written for visitors. The dev server adds a line under each
one with setup advice, such as which environment variable to check; built
pages leave it out.

## What the page does

The page opens on a short introduction and an input box. Enter asks;
Shift + Enter adds a line. Questions run to 1000 characters, the limit the API
enforces.

Each question is answered on its own: the API keeps no conversation, so the
page shows one question and its answer at a time, and asking again replaces
them. `New question` clears the page and cancels a request still in flight.

Answers render as Markdown with math typeset by KaTeX. Both Obsidian's `$…$`
and `$$…$$` and LaTeX's `\(…\)` and `\[…\]` work; code stays literal. Raw HTML
in an answer or excerpt is shown as text, never run, since both quote note text.

An answer is followed by the sections it cites, written as `[[note#heading]]`
links. Each one expands to show the note's path, its heading trail with indent
guides, and the cited excerpt. Excerpts render like answers, as Markdown with
math, and keep single line breaks as Obsidian does. Images in a note show as
their caption instead of loading. A backend that sends no `text`, or a blank
one, shows the path and trail alone.

The other outcomes each say what to do next:

| Outcome | Shown as |
| --- | --- |
| `insufficient_evidence` | A warning that no indexed section supports an answer. |
| 503 from the API | The backend needs a key and a model. |
| 500 from the API | Retrieval failed; check `KNOWLEDGE_ASSISTANT_DB`. |
| 502 from the API | The model call failed; ask again. |
| No reply at all | The request never reached the backend. |

A failure offers `Ask again`, which resends the same question.

### Suggested questions

The opening screen offers up to four starter questions, listed in
`src/suggestions.ts`. They ship with the page when it is built. Choose them by
running each against the same notes and retrieval settings the deployed backend
uses, keep the ones that return a clear answer and useful excerpts, and update
the list when the index changes. An empty list shows no suggestions.

Inter is bundled with the page, so it needs no font requests. The page
respects `prefers-reduced-motion`.

## Not done here

No authentication and no production hosting: the deployed API requires
IAM-signed requests, and whether this ships as a standalone demo or folds into
the portfolio is still open.
