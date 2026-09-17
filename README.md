# DocMind AI

An AI-powered document assistant built on retrieval-augmented generation (RAG).

Upload a PDF, Word file, or plain-text document; DocMind extracts the text,
splits it into overlapping chunks, embeds them into a pgvector index, and then
answers your questions using only the passages that actually match — with
citations pointing back to the page they came from.

Built with **FastAPI**, **PostgreSQL + pgvector**, **SQLAlchemy 2 (async)**,
**Redis**, and **Claude**.

---

## Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Walkthrough](#walkthrough)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Embeddings](#embeddings)
- [Answer generation](#answer-generation)
- [Project layout](#project-layout)
- [Database migrations](#database-migrations)
- [Testing](#testing)
- [Production notes](#production-notes)

---

## How it works

```
      upload                  background task
  ┌────────────┐   ┌──────────────────────────────────────────┐
  │  PDF/DOCX  │──▶│ extract text ─▶ chunk ─▶ embed ─▶ store   │
  │  TXT/MD    │   └──────────────────────────────────────────┘
  └────────────┘                         │
                                         ▼
                             ┌───────────────────────┐
                             │ document_chunks       │
                             │ (content + vector)    │
                             └───────────────────────┘
      question                           │
  ┌────────────┐   embed query   ┌───────▼────────┐   top-k passages
  │ "How did   │───────────────▶ │ cosine search  │────────────────┐
  │  revenue…" │                 │   (pgvector)   │                │
  └────────────┘                 └────────────────┘                ▼
                                                        ┌──────────────────┐
       answer with citations  ◀──────────────────────── │ Claude           │
       "Revenue grew 12% [1]"                           │ (grounded prompt)│
                                                        └──────────────────┘
```

1. **Upload** — the file is streamed to disk under a name derived purely from
   IDs, and a `documents` row is created with status `pending`. The request
   returns immediately.
2. **Index** — a background task extracts the text (per page for PDFs), splits
   it into overlapping chunks on natural boundaries, embeds each chunk, and
   writes them to `document_chunks`. Status becomes `ready`, or `failed` with
   an `error_message`.
3. **Ask** — the question is embedded and compared against the document's
   chunks by cosine distance. The best passages are rendered as numbered
   excerpts and sent to Claude with a prompt that forbids outside knowledge.
4. **Answer** — the response cites passages as `[1]`, `[2]`, and both turns are
   stored on the conversation along with the sources used.

---

## Quick start

### With Docker (recommended)

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY
docker compose up --build
```

The API is then at <http://localhost:8000>, with interactive docs at
<http://localhost:8000/docs>. Migrations run automatically on start.

### Locally

Requires PostgreSQL 14+ with the `vector` extension available, and (optionally)
Redis.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # point DATABASE_URL at your database
alembic upgrade head
uvicorn src.main:app --reload
```

You do **not** need any API keys to try it: the default `hash` embedder runs
locally, and without `ANTHROPIC_API_KEY` the chat endpoint returns the matching
passages verbatim instead of a written answer.

---

## Walkthrough

```bash
BASE=http://localhost:8000

# 1. Sign up and log in
curl -sX POST $BASE/users/ -H 'Content-Type: application/json' \
  -d '{"first_name":"Ada","last_name":"Lovelace","email":"ada@example.com","password":"correct-horse-battery"}'

TOKEN=$(curl -sX POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"ada@example.com","password":"correct-horse-battery"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 2. Upload a document
DOC=$(curl -sX POST $BASE/documents/upload -H "$AUTH" -F 'file=@report.pdf' | jq -r .id)

# 3. Wait for indexing to finish
curl -s $BASE/documents/$DOC/status -H "$AUTH" | jq '{status, page_count, chunk_count}'
# {"status": "ready", "page_count": 12, "chunk_count": 47}

# 4. Start a conversation and ask a question
CONV=$(curl -sX POST $BASE/conversations/ -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"document_id\":\"$DOC\"}" | jq -r .id)

curl -sX POST $BASE/conversations/$CONV/chat -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"question":"How did European revenue change this quarter?"}' | jq '{answer, sources: [.sources[] | {page_number, score}]}'
```

For a token-by-token response, post to `/conversations/$CONV/chat/stream`,
which emits server-sent events: one `sources` event, a run of `delta` events,
then `done`.

---

## API reference

Interactive docs live at `/docs`. All endpoints require a bearer token except
signup, login, the health checks, and `/`.

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/users/` | Sign up |
| `POST` | `/auth/login` | Exchange credentials for an access + refresh token |
| `POST` | `/auth/refresh` | Mint a new access token from a refresh token |
| `POST` | `/auth/logout` | Revoke tokens (blocklisted until they expire) |
| `GET` | `/auth/me` | The authenticated user |

### Users
| Method | Path | Description |
|---|---|---|
| `GET` `PATCH` `DELETE` | `/users/me` | Read, update or delete your own account |
| `POST` | `/users/me/password` | Change password (requires the current one) |
| `GET` | `/users/id/{id}` | Read a user — yourself, or anyone if admin |
| `GET` | `/users/` | List users — **admin only** |
| `GET` | `/users/email/{email}` | Look up by email — **admin only** |

### Documents
| Method | Path | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload a file and queue it for indexing |
| `GET` | `/documents/` | Your documents (`?status=ready`, `?limit=`, `?offset=`) |
| `GET` | `/documents/{id}` | One document |
| `GET` | `/documents/{id}/status` | Poll indexing progress |
| `GET` | `/documents/{id}/chunks` | The indexed chunks |
| `POST` | `/documents/{id}/reindex` | Re-run the pipeline |
| `DELETE` | `/documents/{id}` | Delete the document, its chunks and its file |

### Search
| Method | Path | Description |
|---|---|---|
| `POST` | `/chunks/search` | Semantic search across your documents |
| `GET` | `/chunks/document/{id}` | Chunks for one document |

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/conversations/` | Start a conversation about a `ready` document |
| `GET` | `/conversations/` | Your conversations (`?document_id=`) |
| `GET` | `/conversations/{id}` | Conversation with its full message history |
| `PATCH` `DELETE` | `/conversations/{id}` | Rename or delete |
| `POST` | `/conversations/{id}/chat` | Ask a question |
| `POST` | `/conversations/{id}/chat/stream` | Ask a question (SSE) |
| `GET` | `/conversations/{id}/messages` | Message history |
| `GET` | `/messages/conversation/{id}` | Message history (alternate path) |

### Health
`GET /health` is a liveness probe. `GET /health/ready` verifies the database and
token blocklist, returning `503` when either is unavailable.

---

## Configuration

Every setting is read from the environment or a `.env` file; see
[`.env.example`](.env.example) for the annotated list. The ones worth knowing:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local Postgres | Must use the `postgresql+asyncpg://` driver |
| `SECRET_KEY` | `dev-secret-change-me` | Startup **fails** if left at the default when `ENVIRONMENT=production` |
| `REDIS_URL` | *(empty)* | Empty falls back to an in-process token blocklist |
| `MAX_UPLOAD_SIZE_MB` | `25` | Enforced while streaming, not after the fact |
| `ALLOWED_EXTENSIONS` | `.pdf,.docx,.txt,.md` | Anything else is rejected with `415` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1200` / `200` | Characters. Overlap must be smaller than size |
| `EMBEDDING_PROVIDER` | `hash` | `hash`, `voyage` or `openai` |
| `ANTHROPIC_API_KEY` | *(empty)* | Without it, `/chat` returns excerpts instead of prose |
| `RAG_TOP_K` | `5` | Passages retrieved per question |

---

## Embeddings

Three providers, selected with `EMBEDDING_PROVIDER`:

- **`hash`** (default) — a deterministic hashing vectoriser over word unigrams
  and bigrams. No API key, no network, fully reproducible. It matches on shared
  vocabulary, so it finds "the engineering team grew" for "how large did the
  engineering team grow", but it will miss pure paraphrases. Ideal for local
  development and what the test suite uses.
- **`voyage`** — [Voyage AI](https://voyageai.com), Anthropic's recommended
  embedding partner. Set `EMBEDDING_API_KEY` and `EMBEDDING_MODEL`.
- **`openai`** — any OpenAI-compatible `/embeddings` endpoint. Set
  `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, and optionally `EMBEDDING_BASE_URL`.

All providers emit unit-length vectors of exactly `EMBEDDING_DIMENSIONS` (1536,
matching the database column). A provider with a narrower native width is
zero-padded, which leaves dot products — and therefore cosine similarity —
mathematically unchanged.

> **Switching providers invalidates your index.** Vectors from different models
> are not comparable. After changing the provider, call
> `POST /documents/{id}/reindex` for each document.

---

## Answer generation

Answers come from the Anthropic Messages API, configured in
[`src/services/llm.py`](src/services/llm.py):

- **Model** — `claude-opus-5` by default (`LLM_MODEL`).
- **Adaptive thinking** — on by default. Set `LLM_THINKING=off` if you point
  `LLM_MODEL` at a model older than Claude 4.6, which does not support it.
- **Effort** — `medium` by default, a reasonable balance for chat. Raise
  `LLM_EFFORT` to `high`/`xhigh` for harder analytical questions.
- **Refusal fallback** — enabled by default (`LLM_REFUSAL_FALLBACK`). If the
  model declines a request, the API transparently retries it on a fallback
  model within the same call. Set it to `false` to opt out.

The system prompt in [`src/services/rag.py`](src/services/rag.py) instructs the
model to answer strictly from the supplied excerpts, cite them by number, and
say plainly when the document does not contain the answer.

**Without an API key** the endpoint still works and returns the best-matching
passages verbatim, labelled with their page numbers. That keeps the whole
pipeline explorable before you add credentials.

---

## Project layout

```
src/
├── config.py              # Settings, validated at import
├── main.py                # App wiring, CORS, domain-error -> HTTP mapping
├── db/database.py         # Async engine, session factory, declarative base
├── models/                # SQLAlchemy models (users, documents, chunks, chats)
├── schemas/               # Pydantic request/response models
├── routers/               # HTTP layer only - no business logic
├── services/
│   ├── extraction.py      # PDF/DOCX/text -> pages
│   ├── chunking.py        # pages -> overlapping chunks with page attribution
│   ├── embeddings.py      # hash / voyage / openai providers
│   ├── ingestion.py       # the pipeline, with status tracking
│   ├── chunks.py          # storage + cosine search (pgvector, with fallback)
│   ├── rag.py             # retrieval, prompt construction, answer persistence
│   └── llm.py             # Claude client, refusals, error mapping
└── utils/                 # JWT, password hashing, token blocklist, errors
```

Routers stay thin: they resolve the caller, delegate to a service, and let the
handler in `main.py` turn domain errors (`NotFoundError`, `ConflictError`,
`LLMError`, …) into the right status codes.

---

## Database migrations

```bash
alembic upgrade head                        # apply
alembic revision --autogenerate -m "..."    # create after editing models
alembic downgrade -1                        # roll back one
```

The initial migration creates the `vector` extension before any table that uses
it. The second adds the ingestion-status columns, `ON DELETE CASCADE` across
every foreign key, the supporting indexes, and an HNSW index on the embedding
column for cosine search.

---

## Testing

```bash
pytest                    # 145 tests
pytest --cov=src          # with coverage, if pytest-cov is installed
```

The suite runs entirely offline — SQLite stands in for PostgreSQL, the
blocklist is in-memory, and the `hash` embedder needs no key. It covers the
auth and permission rules, upload validation (type, size, path traversal),
ownership isolation between users, the extraction and chunking logic, retrieval
ranking, the chat flow (both buffered and streamed), and the Claude wrapper's
request shape and error handling.

Because SQLite ignores foreign keys by default, the engine enables
`PRAGMA foreign_keys=ON` so the cascade behaviour under test matches
PostgreSQL.

---

## Production notes

Worth doing before this faces real traffic:

- **Set `SECRET_KEY`** to a random 32-byte value and `ENVIRONMENT=production`;
  startup refuses the development default.
- **Set `REDIS_URL`.** The in-memory blocklist is per-process, so a logged-out
  token would still work on other workers.
- **Move uploads to object storage.** Files currently live on local disk, which
  does not survive a container restart or scale past one node.
- **Run ingestion on a worker.** `BackgroundTasks` ties indexing to the web
  process; a queue (Celery, ARQ, RQ) survives restarts and handles retries.
- **Add rate limiting** on `/auth/login` and the chat endpoints.
- **Tune the HNSW index** (`m`, `ef_construction`) once you know your corpus
  size, and consider a `VACUUM ANALYZE` schedule.
