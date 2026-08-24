# PROJECT_EXPLANATION.md

> A deep architectural blueprint of this repository, written to double as an interview
> preparation guide for system design and codebase walkthroughs.
>
> **What this system is:** a multi-tenant, citation-backed RAG (Retrieval Augmented
> Generation) knowledge base. Users upload PDFs / slides / audio or paste YouTube URLs;
> the system extracts text, splits it into passages, embeds them into vectors, stores them
> in PostgreSQL + pgvector, and answers questions by retrieving relevant passages and
> streaming an LLM answer that cites its sources.
>
> **Stack:** FastAPI (Python 3.11+) · SQLAlchemy 2.x · PostgreSQL + pgvector ·
> Procrastinate (Postgres-backed job queue) · Next.js 15 / React 19 (two apps) ·
> pnpm + Turborepo monorepo · Docker + GHCR + a VPS behind Caddy.

---

## Table of Contents

1. [End-to-End System Architecture & Workflow](#1-end-to-end-system-architecture--workflow)
2. [Structural Breakdown (Directory & File Organization)](#2-structural-breakdown-directory--file-organization)
3. [Deep-Dive Subsystem Analysis](#3-deep-dive-subsystem-analysis)
   - [3.1 The API Server](#31-the-api-server-appsapi)
   - [3.2 The Background Worker & Queue](#32-the-background-worker--queue)
   - [3.3 The Web / Frontend Layer](#33-the-web--frontend-layer)
   - [3.4 The Data Layer](#34-the-data-layer)
4. [Interview Prep & Deep-Dive Concepts](#4-interview-prep--deep-dive-concepts)

---

# 1. End-to-End System Architecture & Workflow

## 1.1 The 10,000-foot view

There are **four runtime processes** and **three stateful backing services**:

```
                          ┌──────────────────────────────────────┐
                          │            Caddy (reverse proxy)     │
                          │  one origin: https://saga.dedyn.io   │
                          └───────┬───────────┬──────────────┬───┘
                            /*    │      /app/*              │ /api/*
                                  │           │              │
                    ┌─────────────▼──┐  ┌─────▼─────────┐  ┌─▼──────────────────┐
                    │  @kb/website   │  │   @kb/web     │  │   @kb/api          │
                    │  Next.js       │  │   Next.js     │  │   FastAPI/uvicorn  │
                    │  (marketing)   │  │   (product)   │  │   (HTTP)           │
                    └────────────────┘  └───────┬───────┘  └─┬────────────────┬─┘
                                                │            │                │
                                        fetch / SSE ─────────┘                │
                                                                              │
                                                        ┌─────────────────────▼───────┐
                                                        │  PostgreSQL 16 + pgvector   │
                                                        │  • domain tables (RLS)      │
                                                        │  • embeddings (HNSW)        │
                                                        │  • chunks.fts (GIN)         │
                                                        │  • procrastinate_jobs       │
                                                        └───────▲──────────────┬──────┘
                                                     LISTEN/NOTIFY             │
                                                                │              │
                                                        ┌───────┴──────────────▼──────┐
                                                        │  kb-worker                  │
                                                        │  procrastinate worker       │
                                                        │  (same image as the API)    │
                                                        └───────┬──────────────┬──────┘
                                                                │              │
                                            ┌───────────────────▼──┐   ┌───────▼─────────────┐
                                            │ Filebase (S3-compat) │   │ AICredits gateway   │
                                            │ original files       │   │ (OpenAI-compatible) │
                                            └──────────────────────┘   │ chat/embed/STT      │
                                                                       └─────────────────────┘
                                            ┌──────────────────────┐
                                            │ Valkey (Redis-proto) │  ← provisioned, port
                                            │ ICache adapter only  │    reserved, unused today
                                            └──────────────────────┘
```

**The single most important architectural decision in this codebase:** the API process
never does slow work. Uploading a 200-page PDF returns `202 Accepted` in milliseconds;
the extract → chunk → embed pipeline runs in a *separate worker process*, communicating
through a job queue whose broker is the same PostgreSQL database the app already uses.

The second most important: **multi-tenancy is enforced twice**, from one source of truth
(a `contextvars` variable), once in the ORM and once in the database via Row-Level
Security. Neither layer trusts the caller to pass a tenant ID.

## 1.2 End-to-end path: "user uploads a PDF"

This is the flagship flow. Follow it once and most of the system falls into place.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (@kb/web)
    participant P as Caddy
    participant A as FastAPI (kb-api)
    participant S3 as Filebase (S3)
    participant DB as PostgreSQL
    participant W as Worker (kb-worker)
    participant AI as AICredits (embeddings)

    B->>P: POST /api/documents/upload (multipart, Bearer token)
    P->>A: POST /documents/upload
    Note over A: AuthenticationMiddleware decodes JWT → Identity
    Note over A: TenantContextMiddleware binds contextvars
    A->>A: await file.read()  (async handler)
    A->>A: sanitize filename → resolve SourceType → registry.get()
    A->>DB: ensure_default() knowledge base
    A->>DB: latest_for_filename() → lineage_id / version
    A->>S3: put_object("{tenant_id}/{asset_id}/{name}")
    A->>DB: INSERT knowledge_assets (status=queued)
    A->>DB: INSERT ingestion_jobs (status=queued)
    A->>DB: INSERT procrastinate_jobs (ingest_asset, tenant_id, user_id)
    A->>DB: INSERT ingestion_job_events ("queued")
    A-->>B: 202 Accepted + KnowledgeAsset{status:"queued"}

    Note over B: useIngestionPoll starts a 2s poll loop

    DB-->>W: LISTEN/NOTIFY wakes the worker
    W->>W: @tenant_task rebuilds tenant contextvars from payload
    W->>DB: session_scope() opens a worker-scoped Session
    W->>DB: mark_running (attempts += 1)
    W->>S3: get_object(storage_key)          [handler.acquire]
    W->>W: PyMuPDF4LLM → markdown + one Document per page  [handler.parse]
    W->>DB: UPDATE status=extracting → chunking
    W->>W: RecursiveCharacterTextSplitter (tiktoken, 800/120)
    W->>DB: DELETE+INSERT chunks (fts column auto-computed)
    W->>AI: POST /embeddings (batch of chunk texts)
    W->>DB: INSERT embeddings (vector(1536))
    W->>DB: UPDATE status=ready - supersede previous versions
    W->>DB: INSERT ingestion_job_events ("ready"), mark_succeeded

    B->>A: GET /documents/{id}  (poll)
    A-->>B: {status:"ready", passage_count: 143}
    Note over B: toast "“Paper.pdf” is ready"
```

**Key properties of this flow to be able to state out loud:**

| Property | How it's achieved |
| --- | --- |
| The request never blocks on parsing | `enqueue_ingestion` only stores + enqueues; `process_ingestion` runs in the worker ([`application/ingestion/service.py`](apps/api/src/application/ingestion/service.py)) |
| File bytes never travel through the queue | Only `asset_id`, `tenant_id`, `user_id` are in the payload; the worker re-downloads from S3 |
| A failed step is resumable | `knowledge_assets.failed_step` is persisted; `_run_pipeline` skips completed stages on retry |
| The worker knows *whose* data it is touching | `@tenant_task` rebuilds the tenant contextvars from the payload and **refuses to run** without them |
| Progress is visible | Each transition writes an `ingestion_job_events` row *and* updates `knowledge_assets.status`, which the frontend polls |
| Re-uploading the same filename doesn't duplicate | `lineage_id` + `version`; the old version is marked `superseded_at` once the new one is `ready` |

## 1.3 End-to-end path: "user asks a question"

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as FastAPI
    participant DB as PostgreSQL
    participant AI as AICredits

    B->>A: POST /conversations/new/messages {question}  (Accept: text/event-stream)
    A->>A: sync def handler → runs in anyio threadpool
    A->>A: builds a generator, returns StreamingResponse
    Note over A: generator opens its OWN session_scope() — not Depends(get_db)
    A->>DB: create conversation (title = first question, no LLM call)
    A-->>B: event: conversation {id, title}
    A->>DB: recent_messages(limit=4)  → history
    Note over A,DB: nothing is persisted yet — a failure here leaves the thread untouched
    A->>AI: POST /embeddings  (previous question + this question)
    A->>DB: dense arm  — ORDER BY vector <=> query LIMIT 30
    A->>DB: lexical arm — WHERE fts @@ websearch_to_tsquery LIMIT 30
    A->>A: Reciprocal Rank Fusion → top 5
    alt fewer than min_context_chunks (2)
        A-->>B: event: delta "not enough context…"
    else enough context
        A->>AI: POST /chat/completions (stream=true)
        loop each token chunk
            AI-->>A: delta
            A-->>B: event: delta "…"
        end
    end
    A-->>B: event: citations [...]
    A->>DB: INSERT user message, then assistant message (citations as JSONB) — one turn
    A-->>B: event: done {user_message_id, message_id}
```

**Notice what is deliberately *not* here:** no LLM call to name the conversation
([`chat/titles.py`](apps/api/src/application/chat/titles.py) derives the title from the
question string), and no persistence of a partial answer — the assistant message is
written *after* the stream completes, so a mid-stream failure leaves nothing behind. The
frontend mirrors that promise exactly by deleting both optimistic messages
([`use-ask.ts`](apps/web/src/lib/use-ask.ts)).

## 1.4 Request lifecycle through the middleware stack

Middleware order in FastAPI/Starlette is **reverse of registration order** — the last
`add_middleware` call is the outermost layer. [`main.py`](apps/api/src/main.py) registers
`TenantContext`, then `Authentication`, then `CORS`, producing:

```
request →  CORSMiddleware
             └→ AuthenticationMiddleware   (resolve credentials → Identity, or 401)
                  └→ TenantContextMiddleware (bind Identity → contextvars)
                       └→ router / endpoint (sync endpoints hop to the threadpool here)
                            └→ Depends(get_db) opens a Session
                                 └→ after_begin listener sets Postgres RLS GUCs
```

Three things about this stack are deliberate and worth memorising:

1. **CORS is outermost** so that even a `401` or a preflight `OPTIONS` carries CORS
   headers. If auth were outside CORS, a browser would see an opaque network error
   instead of a readable 401.
2. **Authentication and tenancy are separate layers.** Authentication owns *how* you
   proved who you are (bearer token today; API keys, OAuth later — each a new
   `Authenticator` in the chain). Tenancy owns *binding* that identity. The tenant layer
   never grows a branch when a credential type is added.
3. **Both are pure ASGI classes, not `BaseHTTPMiddleware`.** This is the single most
   non-obvious decision in the HTTP layer, and it is explained in the next section.

---

# 2. Structural Breakdown (Directory & File Organization)

## 2.1 Repository tree

```text
KB/
├── apps/
│   ├── api/                          # ← the Python backend (API + worker share this image)
│   │   ├── Dockerfile                # multi-stage uv build; ONE image, two commands
│   │   ├── docker-entrypoint.sh      # runs alembic + procrastinate schema iff RUN_MIGRATIONS=1
│   │   ├── pyproject.toml            # dependency manifest (uv-managed lockfile: uv.lock)
│   │   ├── alembic/versions/         # 0001..0006 schema migrations (incl. the RLS policies)
│   │   ├── scripts/create_app_role.sql   # creates the NON-superuser role so RLS actually bites
│   │   ├── tests/unit/               # stdlib unittest; pure-logic tests, no DB
│   │   └── src/
│   │       ├── main.py               # FastAPI app: lifespan, middleware order, router mounting
│   │       ├── composition.py        # ★ COMPOSITION ROOT — the only module that knows adapters
│   │       │
│   │       ├── core/                 # framework-free primitives
│   │       │   ├── config.py         #   pydantic-settings Settings + @lru_cache get_settings
│   │       │   ├── tenant_context.py #   ★ the contextvars that drive ALL tenant isolation
│   │       │   ├── identity.py       #   Identity(tenant_id, user_id) — mechanism-agnostic
│   │       │   ├── exceptions.py     #   KBError hierarchy
│   │       │   ├── text.py           #   sanitizers (NUL bytes etc. before Postgres)
│   │       │   └── logging.py        #   structlog configuration
│   │       │
│   │       ├── domain/               # No FastAPI / SQLAlchemy / Procrastinate. (langchain
│   │       │                         #   Document is the one allowed 3rd-party data type.)
│   │       │   ├── entities/         #   dataclasses: KnowledgeAsset, Chunk, IngestionJob…
│   │       │   ├── interfaces/       #   ★ PORTS (typing.Protocol): IJobQueue, IVectorStore,
│   │       │   │                     #     ISourceHandler, IFileStorage, ITokenService…
│   │       │   └── value_objects/
│   │       │
│   │       ├── application/          # USE CASES. Depend only on domain ports.
│   │       │   ├── auth/service.py   #   register / login / google / refresh / logout / me
│   │       │   ├── ingestion/service.py  # ★ enqueue_* (request) + process_ingestion (worker)
│   │       │   ├── chat/             #   service.py, prompt_builder.py, citations.py, titles.py
│   │       │   └── knowledge_base/
│   │       │
│   │       ├── http/                 # HTTP CONCERNS ONLY
│   │       │   ├── routes/           #   auth, documents, jobs, chat, conversations, kb, health
│   │       │   ├── schemas/          #   Pydantic request/response DTOs (the wire contract)
│   │       │   ├── dependencies/     #   thin Depends() wrappers over composition.py
│   │       │   └── middleware/       #   authentication.py + tenant_context.py (pure ASGI)
│   │       │
│   │       ├── ingestion/            # source-specific acquisition + parsing
│   │       │   ├── source_types.py   #   edge resolvers: extension → SourceType, URL → SourceType
│   │       │   ├── registry.py       #   SourceType → ISourceHandler (Registry pattern)
│   │       │   └── handlers/         #   pdf / youtube / markdown / pptx / audio + _documents.py
│   │       │
│   │       ├── processing/chunking/  # source-agnostic: splits Documents, keeps locators
│   │       ├── retrieval/            # retriever.py (two arms) + fusion.py (RRF) + filters.py
│   │       │
│   │       └── infrastructure/       # ADAPTERS. Everything external lives behind here.
│   │           ├── database/         #   base.py, models.py, session.py, ★ tenancy.py
│   │           ├── repositories/     #   one class per aggregate + mappers.py (model↔entity)
│   │           ├── queue/            #   ★ app.py, tasks.py, tenant_task.py, procrastinate_queue.py
│   │           ├── vector_store/     #   pgvector.py
│   │           ├── storage/          #   filebase_adapter.py (boto3)
│   │           ├── document_parsing/ #   pymupdf_pdf.py
│   │           ├── langchain_adapters/ # chat_model.py, embeddings.py, text_splitter.py
│   │           ├── ai_providers/     #   aicredits_client.py, transcription.py
│   │           ├── auth/             #   jwt_token_service.py, password_hasher.py, google_id_token.py
│   │           └── cache/            #   valkey_cache.py, keys.py (tenant-namespaced keys)
│   │
│   ├── web/                          # ← the PRODUCT app (Next.js 15, basePath: "/app")
│   │   ├── next.config.ts            #   basePath "/app", output "standalone", transpilePackages
│   │   └── src/
│   │       ├── app/
│   │       │   ├── (app)/            #   route group behind RequireAuth + providers
│   │       │   │   ├── layout.tsx    #     RequireAuth → SourcesProvider → ConversationsProvider
│   │       │   │   ├── page.tsx      #     new conversation ("ask")
│   │       │   │   ├── c/[id]/       #     an existing thread
│   │       │   │   ├── library/      #     the source list
│   │       │   │   ├── sources/[id]/ #     source detail + activity timeline
│   │       │   │   ├── view/[id]/    #     citation viewer (passage in context)
│   │       │   │   └── account/
│   │       │   ├── login/ register/  #   OUTSIDE the (app) group → no shell, no data fetch
│   │       │   └── api/health/       #   Next route handler for the container healthcheck
│   │       ├── components/saga/      #   chat.tsx, app-shell, add-source-dialog, source-row…
│   │       ├── lib/
│   │       │   ├── api.ts            #   ★ fetch wrapper: bearer + silent refresh + SSE reader
│   │       │   ├── auth.ts           #   cookie-backed session storage
│   │       │   ├── auth-context.tsx  #   AuthProvider + RequireAuth guard
│   │       │   ├── sources-context.tsx      # single source-of-truth for the library
│   │       │   ├── conversations-context.tsx
│   │       │   ├── use-ask.ts        #   ★ optimistic streaming chat state machine
│   │       │   └── use-ingestion-poll.ts  # ★ resilient polling with failure tolerance
│   │       └── types/api.ts          #   hand-written mirrors of the Pydantic schemas
│   │
│   └── website/                      # ← the MARKETING site (Next.js, served at "/")
│
├── packages/                         # shared workspace libraries (raw TS, transpiled by Next)
│   ├── ui/                           #   design system primitives + theme.css + use-theme
│   ├── shared/                       #   ★ sources.ts — the API's stage names → human copy
│   ├── config/
│   └── sdk/
│
├── deploy/docker-compose.yml         # PRODUCTION stack (external postgres/redis/caddy networks)
├── docker-compose.yml                # LOCAL stack (db + cache + api + worker + web + website)
├── .github/workflows/{ci,deploy}.yml # PR checks; push-to-main → GHCR → rsync → VPS
├── scripts/{run,compose}.mjs         # cross-platform script shims (no `sh` assumed)
├── turbo.json                        # task graph + env passthrough allowlist
└── docs/                             # architecture.md, DESIGN.md, setup.md, deployment.md
```

## 2.2 The layering rule, and how to verify it

The backend follows **Ports & Adapters (Hexagonal Architecture)** with a strict
dependency direction:

```
http ──┐
       ├──→ application ──→ domain (entities + interfaces/ports)
worker ┘                        ▲
                                │ implements
                         infrastructure + ingestion + processing + retrieval
                                ▲
                                │ wires together
                          composition.py
```

Rules you can state and check in seconds:

| Rule | Verification |
| --- | --- |
| `domain/` imports no framework (one exception: the `Document` data type) | `grep -r "fastapi\|sqlalchemy\|procrastinate" apps/api/src/domain/` → empty |
| The queue engine is confined to one directory | `grep -r "procrastinate" apps/api/src/domain/ apps/api/src/application/` → empty |
| LangChain *machinery* is confined to adapters (the `Document` type is shared) | `grep -rn "^from langchain" apps/api/src/ \| grep -v "documents import Document"` → only `langchain_adapters/` |
| Only one module knows concrete classes | `composition.py` — every other module receives its collaborators |

This is why the `docs/architecture.md` file literally ships those grep commands: the
boundary is *executable documentation*, not a convention someone has to remember.

---

# 3. Deep-Dive Subsystem Analysis

# 3.1 The API Server (`apps/api`)

## A. Core Workflow & Architectural Mechanics

### A.1 Application startup and the `lifespan` context manager

```python
# apps/api/src/main.py
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Open the Procrastinate connector for the lifetime of the web process so the
    # synchronous `.defer()` in request handlers has a live connection pool.
    with queue_app.open():
        yield

app = FastAPI(title="AI Knowledge Base PDF MVP", lifespan=lifespan)
```

**What `lifespan` is:** the modern replacement for the deprecated `@app.on_event("startup")`
/ `@app.on_event("shutdown")` decorators. It is an *async context manager*: everything
before `yield` runs once at process start, everything after runs at graceful shutdown.
Starlette drives it via the ASGI `lifespan` protocol.

**Why it matters here:** Procrastinate's `App` owns a connection pool. Deferring a job
(`.defer()`) from inside a request needs that pool open, otherwise it raises `AppNotOpen`.
Opening it once per process — rather than per request — is the difference between one
pool and one pool *per upload*.

> **Interview point:** "Where do you put things that must exist for the life of the
> process but must not be created per-request?" — connection pools, ML model weights,
> HTTP client sessions, background schedulers. Answer: `lifespan`. And the corollary: do
> **not** put per-request state there; `lifespan` runs once per *worker process*, so with
> `uvicorn --workers 4` it runs four times.

### A.2 Routers: composing the URL surface

Each file in [`http/routes/`](apps/api/src/http/routes/) creates an `APIRouter` with a
prefix and tags, and `main.py` mounts them:

```python
# apps/api/src/http/routes/documents.py
router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/{asset_id}", response_model=KnowledgeAssetSchema)
def get_asset(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> KnowledgeAssetSchema:
    ...
```

Three FastAPI mechanics are visible in that one signature:

- **`asset_id: UUID`** — because the name matches the `{asset_id}` path placeholder,
  FastAPI treats it as a *path parameter* and coerces + validates it as a UUID. A
  malformed UUID never reaches your code; it becomes a `422` automatically.
- **`transcript: bool = False`** (in `download_asset`) — a name with a default that
  *isn't* in the path becomes a **query parameter**, parsed as a bool
  (`?transcript=true`).
- **`Annotated[X, Depends(...)]`** — dependency injection, covered in depth in §C.3.

`tags=["documents"]` groups endpoints in the auto-generated OpenAPI docs at `/docs`
(Swagger UI) and `/redoc`.

### A.3 The composition root — the heart of the design

[`composition.py`](apps/api/src/composition.py) is the only module in the backend that
imports concrete adapter classes. Everything else receives its collaborators.

```python
# apps/api/src/composition.py
def build_ingestion_service(db: Session, settings: Settings) -> IngestionService:
    file_storage = build_file_storage(settings)
    return IngestionService(
        kb_repo=KnowledgeBaseRepository(db),
        asset_repo=KnowledgeAssetRepository(db),
        chunk_repo=ChunkRepository(db),
        job_repo=IngestionJobRepository(db),
        job_event_repo=IngestionJobEventRepository(db),
        source_handler_registry=_build_source_handler_registry(file_storage, settings),
        chunker=RecursiveKnowledgeAssetChunker(
            RecursiveSplitterAdapter(settings.chunk_size_tokens, settings.chunk_overlap_tokens)
        ),
        embedding_provider=_build_embedding_provider(settings),
        vector_store=PgVectorStore(db),
        file_storage=file_storage,
        job_queue=build_job_queue(),
    )
```

**Why this shape is powerful:** the *exact same builder* is called from two completely
different execution contexts:

```python
# HTTP path — apps/api/src/http/dependencies/services.py
def get_ingestion_service(db: DbSession, settings: AppSettings) -> IngestionService:
    return build_ingestion_service(db, settings)

# Worker path — apps/api/src/infrastructure/queue/tasks.py
with session_scope() as db:
    service = build_ingestion_service(db, get_settings())
    service.process_ingestion(UUID(asset_id))
```

The only difference is *where the `Session` comes from*. That is why behaviour cannot
drift between "what happens in a request" and "what happens in a worker" — a class of bug
that is extremely common in codebases with two separate wiring paths.

> **Interview point:** this is manual **Constructor Injection** with a composition root,
> not a DI *container*. Python's ecosystem does have containers (`dependency-injector`,
> `punq`), but a composition root is explicit, greppable, type-checked, and has zero
> runtime magic. The trade-off is verbosity: every new collaborator means editing this
> file. That's a feature at this size and a chore at 100 services.

Note the two deliberate **singletons** in this file and *why* each exists:

```python
_cache: ValkeyCache | None = None          # one connection pool process-wide
_google_verifier: GoogleIdTokenVerifier | None = None  # so the JWKS cache is reused
```

And the deliberate *non*-singleton, with its reasoning preserved in a comment:

```python
def _build_pdf_parser() -> PyMuPDF4LLMAdapter:
    # No singleton/lock needed here (unlike the old Docling adapter): PyMuPDF4LLMAdapter has
    # no model weights or expensive per-instance state to cache.
    return PyMuPDF4LLMAdapter()
```

### A.4 The exception strategy

There is **no global exception handler** (`@app.exception_handler`) in this codebase.
Instead, each route translates domain exceptions to HTTP status codes explicitly:

```python
# apps/api/src/http/routes/auth.py
try:
    tokens = auth_service.register(email=..., password=..., name=...)
except EmailAlreadyExistsError as exc:
    raise HTTPException(status_code=409, detail=str(exc)) from exc
except ValueError as exc:
    raise HTTPException(status_code=422, detail=str(exc)) from exc
```

**Trade-off to be able to argue both ways:**

| Explicit per-route (this codebase) | Global `@app.exception_handler` |
| --- | --- |
| ✅ The mapping is visible where the endpoint is read | ✅ Zero repetition; one place to change |
| ✅ Same exception can map differently per route | ❌ Same exception always maps the same way |
| ❌ Repetition across routes | ✅ Impossible to forget |
| ❌ Easy to forget on a new route → leaks a 500 | ✅ A catch-all guarantees a shaped error body |

The domain hierarchy in [`core/exceptions.py`](apps/api/src/core/exceptions.py) is
already designed for a global handler (everything derives from `KBError`) — adding one
would be a small, low-risk refactor and is a good "what would you change?" answer.

### A.5 Two auth-adjacent details worth knowing cold

**Anti-enumeration in login.** Every failure returns the *same* generic 401; the actual
reason is only logged server-side:

```python
# apps/api/src/application/auth/service.py
def _deny(self, reason: str, **fields) -> None:
    logger.info("login_denied", reason=reason, **fields)
    raise InvalidCredentialsError("Invalid credentials or inactive account")
```

Unknown email, wrong password, suspended account, and "this is a Google-only account" are
indistinguishable to a caller. Without this, `POST /auth/login` becomes an oracle for
"does this person have an account here?"

**Refresh token rotation with reuse detection.** Refresh tokens are stored *hashed*
(SHA-256 — fast is fine, they are high-entropy random strings, unlike passwords), carry a
`family_id`, and are single-use:

```python
# apps/api/src/application/auth/service.py — refresh()
if record.revoked_at is not None:
    self.refresh_repo.revoke_family(record.family_id)   # ← theft detected
    self.uow.commit()
    raise TokenError("Refresh token reuse detected")
```

If an attacker steals a refresh token and uses it, the legitimate client's next refresh
presents an already-revoked token → the entire family is revoked → both parties are logged
out. This is the standard OAuth 2.1 "refresh token rotation with automatic reuse
detection" pattern.

---

## B. Library & Framework Deep Dives (API layer)

### B.1 FastAPI

**Overview & how it works under the hood.** FastAPI is a thin, opinionated layer over
three things:

1. **Starlette** — the actual ASGI framework: routing, middleware, requests/responses,
   background tasks, WebSockets, test client. FastAPI's `APIRouter` subclasses
   Starlette's router.
2. **Pydantic** — data validation and serialization, driven by Python type hints.
3. **`typing.get_type_hints` + `inspect.signature`** — at *import time*, FastAPI inspects
   every route function's signature and builds a **dependency graph** and a set of
   Pydantic models describing the request. That analysis is done once at startup, not per
   request, which is why the runtime overhead is small.

From those signatures FastAPI also generates an **OpenAPI 3.1 schema** automatically,
which is what powers `/docs` and `/redoc`. In this project that means the entire wire
contract in [`http/schemas/`](apps/api/src/http/schemas/) is self-documenting.

**Why it was chosen here.** Four reasons that are visible in the code:

- The team wanted **declarative validation at the edge**. Look at
  [`schemas/auth.py`](apps/api/src/http/schemas/auth.py): `password: str = Field(min_length=8, max_length=1024)`.
  That single line is validation, documentation, and an OpenAPI constraint.
- **Dependency injection** was needed for request-scoped resources (the DB session) and
  for swapping implementations in tests. `Depends` provides that natively.
- The project is **AI/ML-adjacent**, and the Python ecosystem (LangChain, PyMuPDF,
  tiktoken, pgvector bindings) is where the tools live. Node/Go would have meant either
  reimplementing or shelling out.
- **Streaming (SSE)** was a hard requirement for chat. Starlette's `StreamingResponse`
  makes that a few lines.

**Alternatives & trade-offs.**

| | **FastAPI** (chosen) | **Flask** (+ extensions) | **Django REST Framework** | **Litestar** |
| --- | --- | --- | --- | --- |
| Concurrency model | ASGI native; sync routes auto-offloaded to a threadpool | WSGI (sync); ASGI is bolted on | WSGI-first; ASGI support exists but the ORM is sync | ASGI native |
| Validation | Pydantic, from type hints, free | Manual, or `marshmallow`/`flask-pydantic` | DRF Serializers (verbose, powerful) | Pydantic/attrs/msgspec |
| DI | First-class (`Depends`) with caching + yield teardown | None; app context + globals | None; class-based views | First-class, arguably cleaner |
| OpenAPI | Automatic and accurate | Add-on (`flasgger`, `apispec`), drifts | `drf-spectacular`, decent | Automatic |
| Batteries | Deliberately few — bring your own ORM/auth/admin | Few | **Everything**: ORM, admin, auth, migrations | Few |
| Perf (rough) | Very high (uvloop + httptools) | Moderate | Lower (heavier stack) | Comparable to or faster than FastAPI |
| Ecosystem/hiring | Enormous, still growing | Enormous, mature | Enormous, mature | Small |

- **Why not Flask?** Streaming an SSE chat response *and* running a threadpool-backed sync
  ORM under a WSGI server means a worker thread is occupied for the entire duration of a
  30-second LLM answer. With gunicorn's default sync worker you'd need `gevent`/`eventlet`
  monkey-patching to survive. ASGI handles long-lived responses natively.
- **Why not Django/DRF?** You'd get auth, admin, and migrations for free — genuinely
  valuable. But this project's core value is a *pipeline*, not CRUD screens, and the
  Django ORM would fight the hand-rolled tenant-filter/RLS design (Django's ORM has no
  equivalent of SQLAlchemy's `do_orm_execute` event hook; you'd use a custom manager on
  every model, which is opt-in and forgettable). The hexagonal architecture here would
  also be swimming upstream against Django's "fat models" convention.
- **Why not Litestar?** Technically a strong choice and in places a better DI story. The
  cost is ecosystem size: fewer answers, fewer integrations, harder hiring.

**Known FastAPI weak spots to mention (shows depth):** DI has no built-in scoping beyond
per-request; `Depends` results are cached *per request* by default which surprises people;
sync/async mixing is a footgun (§C.1); and there is no built-in background *worker* — hence
this project's separate queue.

### B.2 Pydantic (v2) & pydantic-settings

**Overview.** Pydantic v2's validation core is **`pydantic-core`, written in Rust**. When
you declare a model, Pydantic compiles the type hints into a Rust validator "schema" once;
validating an instance then runs that compiled validator. This is why v2 is roughly 5–20×
faster than v1 for typical payloads.

Two model surfaces are used in this repo:

```python
# apps/api/src/http/schemas/documents.py — a response DTO
class KnowledgeAssetSchema(BaseModel):
    id: UUID
    metadata: dict[str, Any]
    passage_count: int = 0
    job: IngestionJobSchema | None = None   # nested model
    created_at: datetime | None
```

```python
# apps/api/src/core/config.py — configuration
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(*ENV_FILES, ".env"), extra="ignore")
    database_url: str = "postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_new"
    retrieval_top_k: int = 5

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`BaseSettings` (from `pydantic-settings`, split out of Pydantic in v2) reads each field
from the environment (case-insensitively: `RETRIEVAL_TOP_K` → `retrieval_top_k`), falling
back to `.env` files, falling back to the declared default. The `@lru_cache` makes
`get_settings` a **memoised singleton** — the env is parsed once per process — while
remaining perfectly injectable as a FastAPI dependency (`Annotated[Settings, Depends(get_settings)]`),
and overridable in tests via `app.dependency_overrides`.

Note the clever `ENV_FILES` line — it walks *up* the directory tree so the same `.env`
works whether you run from the repo root or from `apps/api/`:

```python
ENV_FILES = tuple(parent / ".env" for parent in reversed(Path(__file__).resolve().parents))
```

**Why it was chosen.** It comes with FastAPI, and it removes an entire class of bug:
untyped dictionaries crossing the HTTP boundary. `response_model=KnowledgeAssetSchema`
means the response is *filtered and validated on the way out* too — if a repository ever
started returning an extra field, it would not leak to the client.

**Alternatives & trade-offs.**

| | **Pydantic v2** (chosen) | **marshmallow** | **attrs + cattrs** | **msgspec** |
| --- | --- | --- | --- | --- |
| Speed | Very fast (Rust core) | Slow (pure Python) | Fast | **Fastest** |
| Ergonomics | Type hints, minimal boilerplate | Explicit schema classes | Explicit converters | Type hints |
| FastAPI integration | Native | Manual | Manual | Via Litestar, not FastAPI |
| JSON Schema / OpenAPI | Built-in | Add-on | Manual | Built-in |
| Ecosystem | Massive (LangChain, SQLModel, …) | Mature | Moderate | Small |

The main Pydantic *cost* worth naming: import time and memory. Building validators for
hundreds of models measurably slows cold starts — relevant for serverless, irrelevant for
a long-lived container like this one.

### B.3 SQLAlchemy 2.0 (ORM Core usage in the API)

Covered in depth in [§3.4 The Data Layer](#34-the-data-layer). The API-layer-relevant
piece is the **session-per-request** dependency:

```python
# apps/api/src/infrastructure/database/session.py
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### B.4 Uvicorn

**Overview.** Uvicorn is the ASGI *server*: it owns the event loop, the socket, and HTTP
parsing. `uvicorn[standard]` (as pinned in `pyproject.toml`) pulls in **uvloop** (a
libuv-based event loop, faster than asyncio's default) and **httptools** (a Node.js-derived
C HTTP parser).

**In production here** it is started as a single process per container:

```dockerfile
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Trade-off:** no `--workers`. One uvicorn process uses one CPU core for Python bytecode
(the GIL). Horizontal scaling is done by running more *containers* rather than more
processes inside one — which is the right call under Docker/compose, because the
orchestrator, not uvicorn, then owns restarts and health. Alternatives: **Gunicorn with
`uvicorn.workers.UvicornWorker`** (a battle-tested process manager with graceful reloads),
or **Hypercorn** (adds HTTP/3). For a container-per-process deployment, plain uvicorn is
simplest and correct.

### B.5 PyJWT, pwdlib[argon2], structlog, boto3

- **PyJWT** (`jwt_token_service.py`) — HS256 symmetric signing. Access tokens carry
  `sub` (user), `tid` (tenant), `jti`, `type`, `exp`. The `type: "access"` check on decode
  prevents a refresh token from ever being presented as an access token — a real
  vulnerability class ("token confusion"). `pyjwt[crypto]` pulls `cryptography` because
  Google's ID tokens are **RS256** and need asymmetric verification.
  *Alternatives:* `python-jose` (broader JWE/JWK support, slower-moving),
  `authlib` (full OAuth framework — more than needed here).
- **pwdlib[argon2]** — Argon2id password hashing. Argon2id is **memory-hard**, which is
  what makes GPU/ASIC cracking expensive; it won the 2015 Password Hashing Competition.
  `pwdlib` is the modern successor to `passlib` (which is effectively unmaintained and had
  a bcrypt-version incompatibility that broke many FastAPI tutorials).
  *Alternatives:* bcrypt (fine, but a 72-byte input limit and not memory-hard), scrypt,
  PBKDF2 (FIPS-approved but weakest of the four against dedicated hardware).
- **structlog** — structured, key-value logging (`logger.info("ingestion_step", step=step, knowledge_asset_id=...)`).
  Emits JSON that a log aggregator can query, instead of prose you have to regex. Note the
  deliberate design decision in this codebase: **structlog output is not the audit trail**.
  Anything the product needs to *show a user* is written to the `ingestion_job_events`
  table instead, because stdout is ephemeral and unqueryable.
- **boto3** — the AWS SDK, pointed at Filebase via `endpoint_url`. Because Filebase speaks
  the S3 API, zero code changes are needed to move to AWS S3, MinIO, Cloudflare R2, or
  Backblaze B2. That is the whole point of choosing an S3-compatible provider.
  *Alternative:* `aioboto3`/`aiobotocore` for async — unnecessary here because the calls
  happen either in a threadpool endpoint or in the worker.

---

## C. Specialized FastAPI Focus

This is the section to read twice if FastAPI is new to you.

### C.1 `async def` vs `def` — and the anyio threadpool

**The rule.** FastAPI inspects each route function:

- **`async def`** → the coroutine is awaited **directly on the event loop**.
  ⚠️ Any blocking call inside it (a sync DB query, `requests.get`, `time.sleep`,
  CPU-heavy work) **blocks the entire event loop** — i.e. every other concurrent request
  in that process stalls.
- **`def`** (plain sync) → FastAPI runs it via `anyio.to_thread.run_sync`, i.e. in a
  **threadpool worker**. The event loop stays free. This is *safe* but *bounded*: anyio's
  default threadpool is **40 threads**.

**How this codebase uses it.** Nearly every route is **sync (`def`)**:

```python
# apps/api/src/http/routes/documents.py — sync, runs in the threadpool
@router.get("/{asset_id}", response_model=KnowledgeAssetSchema)
def get_asset(asset_id: UUID, db: ..., file_storage: ...) -> KnowledgeAssetSchema:
    asset = KnowledgeAssetRepository(db).get(asset_id)
```

**All 27 handlers are sync.** There are no exceptions, and
[`tests/unit/test_routes_are_sync.py`](apps/api/tests/unit/test_routes_are_sync.py)
enforces that — it walks every mounted `APIRoute` and fails on any coroutine endpoint.

That test exists because of a real bug that used to live here, and the story is the sharpest
FastAPI material in this codebase.

**What it looked like.** `upload_document` was the one `async def` route:

```python
# BEFORE — async, so it ran on the event loop
@router.post("/upload", status_code=202)
async def upload_document(..., file: UploadFile = File(...)) -> KnowledgeAssetSchema:
    file_data = await file.read()
    ...
    asset = ingestion_service.enqueue_ingestion(file_data, ...)  # ← blocking, on the loop!
```

The subtle part: **`await file.read()` was never the problem** — that call correctly
offloads to the threadpool once the upload spools to disk. The bug was the *unawaited*,
fully synchronous `enqueue_ingestion` sitting right after it. Audited, that one call does:

| Blocking work | Where |
| --- | --- |
| `SELECT` + `COMMIT` (`ensure_default`) | `postgres_kb_repository.py` |
| `SELECT` (`latest_for_filename`) | `postgres_document_repository.py` |
| **HTTPS `put_object` of the entire file body** | `filebase_adapter.py` |
| `INSERT` + `COMMIT` ×3 (asset, job, job event) | three repositories |
| **fresh sync PG connection** + `INSERT` + `NOTIFY` (`.defer()`) | `procrastinate_queue.py` |

One remote S3 round-trip, five Postgres commits, and a brand-new synchronous database
connection — all on the single event loop thread. While one user uploaded a PDF, *nothing
else in that process made progress*: not chat, not the 2-second status polls, not `/health`.

**The fix that was applied** — make the handler plain `def` and read the upload
synchronously:

```python
# AFTER — sync, so FastAPI dispatches the whole thing to the threadpool
@router.post("/upload", status_code=202)
def upload_document(..., file: UploadFile = File(...)) -> KnowledgeAssetSchema:
    file_data = file.file.read()   # the SpooledTemporaryFile, already rewound by the parser
    ...
    asset = ingestion_service.enqueue_ingestion(file_data, ...)  # blocking, but off the loop
```

**Why this option over the other two.** The candidates were:

1. **Make it `def`** (chosen). Matches all 26 other routes; the app is deliberately
   sync-first, and `def` is what makes that safe automatically. One threadpool dispatch for
   what is logically one unit of blocking work.
2. **Keep `async def`, wrap the call:**
   `await run_in_threadpool(ingestion_service.enqueue_ingestion, data, name, ctype)`.
   Works, and the tenant contextvars still propagate (`run_in_threadpool` copies the current
   context) — but it pays for two threadpool hops on a >1 MB upload and leaves the handler
   looking async for no benefit.
3. **Go async end-to-end** (async SQLAlchemy + `aioboto3`). A whole-stack change, not a fix.

**Measured, not assumed.** With a 2-second stub standing in for the blocking work and
`/health` probed 150 ms in:

```
  sync handler   → /health answered at 0.18s   loop FREE
  async handler  → /health answered at 2.17s   loop BLOCKED
```

**Two honest caveats.** It had never actually bitten in production — one low-traffic
instance, and typical PDFs upload fast. It was a *latent* scaling bug, and saying so is the
framing an interviewer wants. And the fix does **not** address the separate problem that
`read()` pulls the whole upload into RAM against a 512 MB container limit; that needs
streaming multipart straight to S3 and is still open.

**The mental model to memorise:**

```
                     ┌────────────── event loop (1 thread) ──────────────┐
  async def route ──▶│ awaited here. Blocking call = whole server stalls │
                     └───────────────────────────────────────────────────┘
                                        │ anyio.to_thread.run_sync
                                        ▼
                     ┌──────── threadpool (default 40 workers) ──────────┐
  def route ────────▶│ blocking is fine. Bounded: 41st request queues.   │
                     └───────────────────────────────────────────────────┘
```

**And the capacity arithmetic**, which is a great thing to volunteer:

- anyio threadpool default: **40** threads.
- SQLAlchemy `QueuePool` default: `pool_size=5`, `max_overflow=10` → **15** connections.
- Therefore: 40 concurrent sync requests contend for 15 connections. The 16th waits
  (default `pool_timeout=30s`, then `TimeoutError`).
- **The DB pool is the real ceiling, not the threadpool.** If you tune one number in this
  system for throughput, it is `create_engine(..., pool_size=..., max_overflow=...)` in
  [`session.py`](apps/api/src/infrastructure/database/session.py) — and it must be tuned
  against Postgres's `max_connections` divided across (API replicas + worker replicas).

**Why the middleware is pure ASGI — the contextvar propagation argument.** This is the
non-obvious decision flagged in §1.4:

```python
# apps/api/src/http/middleware/tenant_context.py
class TenantContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        identity = scope.get(SCOPE_IDENTITY_KEY) if scope["type"] == "http" else None
        if identity is None:
            await self.app(scope, receive, send)
            return
        tokens = set_tenant_context(identity.tenant_id, identity.user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_tenant_context(tokens)
```

Starlette's `BaseHTTPMiddleware` is a convenience wrapper that gives you a
`dispatch(request, call_next)` signature. To do that, it runs the downstream app in a
**separate anyio task** connected by a memory stream. A separate task means a **separate
context copy** — so a `ContextVar` set in `BaseHTTPMiddleware.dispatch` **does not
reliably reach the endpoint**, and definitely not the threadpool call beneath it.

Writing the middleware as a raw ASGI callable (`async def __call__(self, scope, receive, send)`)
keeps **one continuous context chain** from middleware → endpoint → threadpool worker.
Since the entire tenant isolation system depends on those contextvars being visible inside
SQLAlchemy session listeners, this is not a style preference — it is load-bearing.

> **Interview gold:** "Why not `BaseHTTPMiddleware`?" → contextvar propagation, plus
> `BaseHTTPMiddleware` historically interfered with `StreamingResponse` (it buffers) and
> with `BackgroundTasks` ordering. Pure ASGI middleware is also measurably faster (no
> extra task + stream per request).

### C.2 Pydantic validation, serialization, and schema generation in this app

**Request validation.** The model *is* the contract:

```python
# apps/api/src/http/schemas/auth.py
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    name: str | None = Field(default=None, max_length=255)
```

A body failing any constraint never enters the route — FastAPI returns `422 Unprocessable
Entity` with a per-field error list. Note the pragmatic choice of `str` over Pydantic's
`EmailStr`: `EmailStr` requires the `email-validator` package and rejects some
technically-valid addresses; here the semantic check (`"@" not in email`) lives in the
auth service instead. That's a defensible trade-off (fewer deps, validation with the
business rule) and a fine thing to discuss.

**Response serialization.** `response_model` does more than document:

```python
@router.get("", response_model=list[KnowledgeAssetSchema])
def list_assets(db: ...) -> list[KnowledgeAssetSchema]:
```

FastAPI validates and **filters** the outgoing object against the model. Fields not in the
schema are dropped. This is a genuine security property: if a repository returned an
internal field (say, a raw storage credential in `metadata`), the response model is the
gate. It also means `datetime` → ISO-8601 string and `UUID` → string conversions happen
automatically.

**A subtle inconsistency worth noticing** (good "code review" material): `chat.py` declares
`response_model=AskQuestionResponse` but the function's return annotation is `-> dict`,
and `ChatService.ask` returns a plain dict. FastAPI still validates against the response
model, so the contract holds — but the annotation and the model disagree, so a type
checker cannot help. The conversations route does the same thing more explicitly by
constructing schema objects.

**Schema generation.** From these models FastAPI produces `/openapi.json`, and thus
`/docs`. All four are on the auth-exempt list in
[`middleware/authentication.py`](apps/api/src/http/middleware/authentication.py) so the
docs are reachable without a token.

### C.3 Dependency Injection — `Depends`, `Annotated`, caching, and yield lifecycle

**The basic mechanism.** `Depends(f)` tells FastAPI: before calling this route, call `f`,
resolving *its* parameters the same way (recursively), and pass the result in.

This codebase uses the modern **`Annotated`** form, and factors out repeated dependencies
into type aliases:

```python
# apps/api/src/http/dependencies/services.py
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

def get_ingestion_service(db: DbSession, settings: AppSettings) -> IngestionService:
    return build_ingestion_service(db, settings)
```

Then a route just writes:

```python
ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)]
```

`Annotated[X, Depends(y)]` is preferred over the older `x: X = Depends(y)` because the
parameter keeps a real default-free signature — so the same function is directly callable
in a unit test, and non-`Depends` defaults don't have to come last.

**Dependency caching.** Within a *single request*, FastAPI calls each dependency **once**
and reuses the result. In this route:

```python
def rename_asset(
    asset_id: UUID,
    request: RenameKnowledgeAssetRequest,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
): ...
```

`get_db` may be requested by three different dependencies in one request — it still opens
**one** session. That is what makes "one transaction per request" work at all. Caching can
be disabled with `Depends(f, use_cache=False)`.

**The yield lifecycle.** A dependency that `yield`s is a context manager:

```python
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db          # ← the route runs here
    finally:
        db.close()        # ← teardown, after the route returns
```

⚠️ **The critical gotcha, and this codebase handles it explicitly.** Since FastAPI 0.106,
exit code in a yield-dependency runs **before the response is sent** — which means a
`StreamingResponse` whose generator uses `db` would find the session already closed. The
conversations route sidesteps it by *not taking the request session at all*:

```python
# apps/api/src/http/routes/conversations.py
@router.post("/{conversation_id}/messages")
def ask_in_conversation(
    conversation_id: str,
    request: AskRequest,
    identity: Annotated[Identity, Depends(get_current_identity)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Deliberately does **not** take the request-scoped `get_db` session. ...

    The generator must **not** bind the tenant context itself — see the box below."""

    def events() -> Iterator[str]:
        with session_scope() as db:
            chat_service = build_chat_service(db, settings)
            for event, payload in chat_service.ask_stream(target, question):
                yield _frame(event, payload)

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)
```

> ### 🐛 The bug that lived here — the single best story in this codebase
>
> This route used to bind the tenant contextvar at the top of `events()` and reset it in a
> `finally`. It looked like textbook defensive hygiene. It broke **100% of streamed answers.**
>
> **The mechanism.** Starlette iterates a *sync* generator via `iterate_in_threadpool`, which
> calls `anyio.to_thread.run_sync(next, it)` once per yielded frame — and anyio does a fresh
> `copy_context()` for **each** call. So `set_tenant_context` ran during the *first* `next()`
> and `reset_tenant_context` during the *last*, in two different `Context` objects. A `Token`
> can only be reset in the context that produced it, so `ContextVar.reset` raised
> `ValueError: <Token …> was created in a different Context`.
>
> **Why it was invisible.** That `finally` sat *outside every `except`* in the generator, and
> it fired **after** the `done` frame had gone out on the wire and after `session_scope()` had
> committed. So: HTTP 200, complete body, answer saved — and then the ASGI app raised
> mid-body, uvicorn dropped the connection without its terminating chunk, and the browser
> reported `ERR_INCOMPLETE_CHUNKED_ENCODING`. The client's `catch` deleted both messages from
> the screen. Users saw the answer stream in, render, then vanish behind a "network error" —
> and reloading the page brought it back, because it had been saved all along.
>
> **How it was proven.** Not by reading. By mounting the real route on a real socket with a
> real signed JWT and the real middleware stack (only the DB and chat service stubbed), and
> draining it: 3/3 attempts returned HTTP 200 with the full body, then
> `RemoteProtocolError: peer closed connection without sending complete message body`.
> Removing the in-generator pair: 3/3 clean EOF, with the tenant still resolving correctly on
> every frame.
>
> **The fix, and why this one.** The pair was *redundant as well as broken*:
> `TenantContextMiddleware` has already bound tenant/user in the enclosing context, the whole
> streaming body is sent inside its `await self.app(...)`, and `copy_context()` carries that
> binding into every frame. So the binding was deleted outright. `reset_tenant_context` was
> *also* made tolerant of a foreign-context token — falling back to unset, which fails closed
> — so this class of bug cannot silently kill a response body anywhere else.
>
> **The lesson worth stating out loud in an interview:** `set`/`reset` in a `finally` is a
> correct idiom *only when both halves run in the same context*. A sync generator behind
> `StreamingResponse` violates that invariant, and the failure is maximally deceptive — it
> presents as a transport fault, for a request that fully succeeded. The alternatives
> considered were an `async def` generator (one context, no threadpool hop) and running the
> generator inside one explicitly captured `Context`; deleting a redundant binding beat both
> on simplicity.
>
> Pinned by `apps/api/tests/unit/test_conversation_stream.py`, which drives the route through
> the real `iterate_in_threadpool` — no socket, no timing, and it fails loudly if anyone
> reintroduces the pattern.

**Dependency overrides in tests.** The reason `get_db` and `get_settings` are dependencies
rather than module globals:

```python
app.dependency_overrides[get_db] = lambda: fake_session
```

This is the FastAPI-idiomatic seam for integration tests, and it is only available because
nothing reaches for a global session.

**A security-relevant dependency.** `get_current_identity` reads what the middleware
already resolved, rather than decoding a token a second time:

```python
# apps/api/src/http/dependencies/services.py
def get_current_identity(request: Request) -> Identity:
    identity: Identity | None = request.scope.get(SCOPE_IDENTITY_KEY)
    if identity is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity
```

The token is decoded **exactly once per request**, in the middleware. The 401 here is a
defensive backstop for the case where someone mistakenly adds a route to the exempt-prefix
list.

### C.4 Middleware, CORS, exception handlers, and background tasks

**Middleware** — covered in §1.4 and §C.1. The authentication chain deserves one more look
because its three-way return contract is a nice piece of API design:

```python
# apps/api/src/http/middleware/authentication.py
class Authenticator(Protocol):
    def authenticate(self, scope) -> Identity | None:
        """Return an ``Identity`` if this mechanism's credential is present and valid,
        ``None`` if it isn't present, or raise ``AuthError`` if present but invalid."""
```

- `Identity` → authenticated; stop the chain.
- `None` → "my credential isn't here"; try the next authenticator.
- raise `AuthError` → a credential *was* present but bad → **immediate 401**.

That third case is the security-critical one: a malformed bearer token must **not** fall
through to a weaker authenticator behind it. Distinguishing "absent" from "invalid" is how
you avoid auth-downgrade attacks.

**CORS.**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # parsed from a comma-separated env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Note the comment in `config.py`: in production this barely matters, because **Caddy serves
the frontends and the API from one origin** (`/app/*` → web, `/api/*` → API), so browser
requests are same-origin and never preflight. CORS exists for local dev, where Next runs
on `:3000`/`:3001` and the API on `:8000`.

⚠️ Note that `allow_credentials=True` with `allow_origins=["*"]` is silently rejected by
browsers (and by Starlette). Here `cors_origins` is an explicit list, so it's correct — but
this is a classic bug to be able to spot.

**Exception handlers.** As discussed in §A.4, there are none registered globally; routes
translate explicitly. Custom 401s are produced by the ASGI middleware writing the response
itself, since it sits above the exception-handling middleware:

```python
async def _unauthorized(send, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send({"type": "http.response.start", "status": 401, "headers": [...]})
    await send({"type": "http.response.body", "body": body})
```

**Background tasks — and why they are *not* used here.** FastAPI ships
`BackgroundTasks`, which runs a function *after the response is sent, in the same
process*:

```python
# NOT used in this codebase — shown for contrast
@app.post("/upload")
async def upload(background_tasks: BackgroundTasks):
    background_tasks.add_task(process_pdf, asset_id)
    return {"status": "queued"}
```

**Why this project uses a real queue instead** — and this is one of the best "why" answers
in the whole codebase:

| `BackgroundTasks` | Procrastinate (chosen) |
| --- | --- |
| Dies with the process — a deploy or a crash **loses the work silently** | Job row is committed to Postgres; survives restarts |
| No retries | `RetryStrategy(max_attempts=3, exponential_wait=5)` |
| No visibility — you cannot list what is pending | `SELECT * FROM procrastinate_jobs`, plus the domain `ingestion_jobs` table |
| Competes with request handling for the same CPU/threadpool | Runs in a **separate container**, scaled independently |
| No concurrency control | `procrastinate worker --concurrency N` |

Rule of thumb to state: `BackgroundTasks` is for *fire-and-forget work you can afford to
lose* (an audit log line, a cache warm, a best-effort email). Anything a user is waiting on
or paying for needs a durable queue.

---

# 3.2 The Background Worker & Queue

## A. Core Workflow & Architectural Mechanics

### A.1 The four files that constitute the queue

```text
apps/api/src/infrastructure/queue/
├── app.py                  # the Procrastinate App (broker = our Postgres)
├── tasks.py                # @app.task definitions + retry policy
├── tenant_task.py          # @tenant_task decorator: rebuild tenant context from the payload
└── procrastinate_queue.py  # ProcrastinateJobQueue — the IJobQueue port implementation
```

Plus one line in `docker-compose.yml` that turns the *same image* into a worker:

```yaml
worker:
  build: { context: ./apps/api }        # identical image to `api`
  command: procrastinate --app=src.infrastructure.queue.app.app worker
  healthcheck: { disable: true }        # no HTTP server → the inherited healthcheck would fail
```

> **"One image, two commands"** is worth calling out explicitly. The worker cannot drift
> from the API: same code, same dependencies, same `composition.py`. Only the entrypoint
> command differs. The `healthcheck: disable: true` line shows someone actually ran it —
> the API's `HEALTHCHECK` curls `:8000/health`, which a worker doesn't serve.

### A.2 The Procrastinate App

```python
# apps/api/src/infrastructure/queue/app.py
def _libpq_dsn(sqlalchemy_url: str) -> str:
    # SQLAlchemy uses "postgresql+psycopg://..."; the Procrastinate psycopg connector
    # wants a plain libpq DSN. Strip the driver suffix so one DATABASE_URL feeds both.
    return sqlalchemy_url.replace("+psycopg", "", 1)

app = App(
    connector=PsycopgConnector(conninfo=_libpq_dsn(get_settings().database_url)),
    import_paths=["src.infrastructure.queue.tasks"],
)
```

Two mechanics here:

- **`import_paths`** tells the `procrastinate worker` CLI which modules to import so the
  `@app.task`-decorated functions register themselves in the app's task registry. It is
  imported *lazily at worker startup*, which breaks an import cycle
  (`tasks` → `composition` → `queue adapter` → `tasks`).
- **The connector uses `database_url` (the superuser role), not `app_database_url`.**
  That is intentional: Procrastinate's own tables are infrastructure, not tenant data, and
  are not subject to RLS.

### A.3 Enqueue — what actually crosses the boundary

```python
# apps/api/src/infrastructure/queue/procrastinate_queue.py
class ProcrastinateJobQueue(IJobQueue):
    def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        ingest_asset.defer(
            asset_id=str(asset_id), tenant_id=str(tenant_id), user_id=str(user_id)
        )
```

`.defer()` is a plain `INSERT` into `procrastinate_jobs`, followed by a Postgres
`NOTIFY`. A worker sitting in `LISTEN` wakes immediately; if none is listening, the job
simply sits in the table until one polls.

**Three deliberate properties of this payload:**

1. **Only IDs.** No file bytes, no parsed text, no settings. The payload stays small
   (queue rows are cheap), and — critically — the worker re-reads from the *authoritative*
   source (Postgres + S3) rather than trusting a possibly-stale snapshot.
2. **`tenant_id` and `user_id` travel explicitly.** A background job has no HTTP request,
   so there is no middleware to bind the tenant. The queue payload *is* the propagation
   mechanism.
3. **It is called synchronously from a request handler.** Since the FastAPI process opens
   the Procrastinate app in `lifespan`, the async connector has a live pool it can derive a
   one-off sync connection from.

⚠️ **The ordering subtlety.** In `enqueue_ingestion` the sequence is:

```python
asset = self.asset_repo.create_pending(...)   # commits
job   = self.job_repo.create(IngestionJob(asset_id=asset.id))   # commits
self._enqueue(asset.id)                        # separate INSERT + NOTIFY
```

The asset and job rows are committed **before** the job is deferred. That ordering
guarantees a worker can never wake up and find an asset that isn't persisted yet. But it
means enqueue is **not atomic with** the asset insert: if the process dies between the
commit and the `defer`, you get an asset stuck in `queued` forever with no queue row.

> **This is the classic dual-write problem, and Procrastinate has the textbook answer:**
> `defer` in the *same transaction* as the domain writes. Because the queue lives in the
> same Postgres database, `INSERT INTO knowledge_assets` and `INSERT INTO
> procrastinate_jobs` **can** be one atomic commit — that is the headline advantage of a
> Postgres-backed queue over Redis/RabbitMQ, where you'd need the Transactional Outbox
> pattern. This codebase doesn't currently take that win (each repository commits
> independently), which is a precise, high-value "what would you improve?" answer.
>
> The mitigation that *does* exist: the `/jobs` dashboard and the asset's `status` column
> make a stuck `queued` asset visible, and `POST /documents/{id}/retry` re-enqueues it.

### A.4 The task, and the `@tenant_task` decorator

```python
# apps/api/src/infrastructure/queue/tasks.py
_RETRY = RetryStrategy(max_attempts=3, exponential_wait=5)

@app.task(name="ingest_asset", retry=_RETRY)
@tenant_task
def ingest_asset(asset_id: str) -> None:
    from src.composition import build_ingestion_service   # deferred: breaks an import cycle

    logger.info("ingest_task_received", asset_id=asset_id)
    with session_scope() as db:
        service = build_ingestion_service(db, get_settings())
        service.process_ingestion(UUID(asset_id))
```

Decorator order matters: `@app.task` is outermost (it registers the *wrapped* callable),
`@tenant_task` is innermost-but-one, so the tenant context is established before the body
runs.

```python
# apps/api/src/infrastructure/queue/tenant_task.py
def tenant_task(fn: Callable) -> Callable:
    def wrapper(**kwargs):
        tenant_id = kwargs.pop("tenant_id", None)
        user_id = kwargs.pop("user_id", None)
        if not tenant_id or not user_id:
            raise ValueError(
                f"Task '{getattr(fn, '__name__', 'task')}' was enqueued without "
                "tenant_id/user_id — refusing to run unscoped"
            )
        tokens = set_tenant_context(UUID(str(tenant_id)), UUID(str(user_id)))
        try:
            return fn(**kwargs)
        finally:
            reset_tenant_context(tokens)

    # Don't use functools.wraps: it sets __wrapped__, which would make signature
    # introspection follow through to the inner fn and hide the tenant kwargs.
    wrapper.__name__ = getattr(fn, "__name__", "tenant_task")
    wrapper.__doc__ = fn.__doc__
    return wrapper
```

Two details a careful reader should catch:

- **Fail loud, not silent.** A job without a tenant raises rather than running unscoped.
  This is the queue-side counterpart of the ORM filter's fail-closed rule. A "helpful"
  fallback here would be a cross-tenant data leak.
- **The deliberate absence of `functools.wraps`.** `wraps` sets `__wrapped__`, and
  Procrastinate introspects the task signature to validate deferred kwargs. Following
  `__wrapped__` would show `ingest_asset(asset_id)` — with no `tenant_id`/`user_id` — and
  reject valid defers. Copying just `__name__`/`__doc__` keeps the wrapper's own signature
  visible. This is a genuinely subtle Python-internals detail and a great thing to be able
  to explain.

### A.5 The pipeline state machine

`process_ingestion` is the worker's entry point; `_run_pipeline` is the state machine:

```python
# apps/api/src/application/ingestion/service.py (condensed)
def _run_pipeline(self, asset, handler, job_id):
    step = "extracting"
    try:
        if asset.failed_step in (None, "extracting"):
            asset.status = AssetStatus.EXTRACTING
            self.asset_repo.update_from_domain(asset)
            raw   = handler.acquire(asset)        # ← S3 download / YouTube fetch / STT
            asset = handler.parse(asset, raw)     # ← PyMuPDF → markdown + Documents
            self.asset_repo.update_from_domain(asset)

        step = "chunking"
        if asset.failed_step in (None, "chunking"):
            chunks = self.chunker.chunk(asset)
            if not chunks:
                raise ValueError("Source produced no indexable text chunks")
            chunks = self.chunk_repo.replace_for_asset(asset.id, chunks)
        else:
            chunks = self.chunk_repo.list_for_asset(asset.id)

        step = "embedding"
        embeddings = self.embedding_provider.embed_texts([c.text for c in chunks])
        self.vector_store.upsert_embeddings(asset, chunks, embeddings)

        step = "persisting"
        asset.status = AssetStatus.READY
        ready = self.asset_repo.update_from_domain(asset)
        self.asset_repo.supersede_previous_versions(asset.lineage_id, asset.id)
        return ready
    except Exception as exc:
        asset.status = AssetStatus.FAILED
        asset.failed_step = step          # ← this is what makes retries resumable
        asset.error_message = str(exc)
        return self.asset_repo.update_from_domain(asset)
```

Then, one level up:

```python
if result.status == AssetStatus.FAILED:
    if job is not None:
        self.job_repo.mark_failed(job.id, error)
    raise IngestionError(error)      # ← re-raise so Procrastinate retries
```

**The three-part design here is the thing to articulate:**

1. **`failed_step` makes retries resumable.** A failure during embedding does not
   re-download and re-parse the PDF; the `if asset.failed_step in (None, "chunking")`
   guards skip completed stages. That saves the expensive PDF parse *and* the S3 egress on
   every retry.
2. **The exception is caught, recorded, and *re-raised*.** Swallowing it would leave
   Procrastinate thinking the job succeeded. Re-raising is what hands control back to the
   retry policy.
3. **Two status vocabularies, on purpose.** `AssetStatus` tracks the *pipeline stage*
   (`extracting`/`chunking`/`embedding`/`ready`); `JobStatus` tracks *whether the work ran
   and how many times we tried* (`queued`/`running`/`succeeded`/`failed`). Conflating them
   would make "failed at embedding on attempt 2 of 3" unrepresentable.

### A.6 The persisted worker log

Every transition writes a row:

```python
def _record(self, asset, event, message=None, *, level="info", job_id=None, data=None):
    try:
        self.job_event_repo.append(JobEvent(asset_id=asset.id, job_id=job_id, ...))
    except Exception:   # noqa: BLE001 - logging is non-fatal by design
        logger.warning("job_event_record_failed", ...)
```

Note the swallowed exception, and why it's correct here: *a logging failure must never
fail an ingestion*. The structlog trail still fires. This table is what
`GET /documents/{id}/events` serves and what the activity timeline in the UI renders — a
user-facing, queryable audit trail that stdout could never provide.

### A.7 Idempotency and the "at-least-once" contract

Procrastinate, like nearly every queue, is **at-least-once**: a worker that crashes after
doing the work but before acknowledging will re-run the job. So every step must be safe to
repeat. It is, and here's why:

| Step | Why re-running is safe |
| --- | --- |
| `acquire` | Read-only S3 GET / HTTP fetch |
| `parse` | Pure function of the bytes |
| `chunk` persistence | `replace_for_asset` does `DELETE ... WHERE knowledge_asset_id = ?` then re-inserts |
| `embedding` persistence | `replace_for_chunks` does `DELETE ... WHERE chunk_id IN (...)` then re-inserts, and there's a `uq_embedding_chunk_model` constraint |
| status updates | Idempotent writes of the same value |

The cost of re-running is real money (re-embedding calls the paid API) but the *result* is
correct. Trading a little cost for a much simpler correctness story is the right call at
this scale.

## B. Library & Framework Deep Dives (Worker layer)

### B.1 Procrastinate

**Overview & how it works.** Procrastinate is a Postgres-backed job queue for Python. Its
mechanism:

- **Storage:** a `procrastinate_jobs` table (plus supporting tables/functions), created by
  `procrastinate schema --apply`.
- **Enqueue:** `task.defer(**kwargs)` inserts a row and issues `NOTIFY procrastinate_any_queue`.
- **Dequeue:** the worker runs `LISTEN`, and on wake calls a stored procedure that does
  `SELECT ... FOR UPDATE SKIP LOCKED` — the standard Postgres queue idiom. `SKIP LOCKED`
  is what lets N workers pull disjoint jobs without a distributed lock.
- **Retries:** `RetryStrategy` computes the next `scheduled_at` and the row goes back to
  `todo`.
- **Async-native:** the worker is an asyncio application; sync tasks (like `ingest_asset`)
  are run in a threadpool by the worker.

**Why it was chosen.** The comment in [`app.py`](apps/api/src/infrastructure/queue/app.py)
says it plainly: *"its broker IS our existing Postgres, so there is no extra infrastructure
to run."* Concretely:

- The deployment target is a **shared VPS** running multiple apps behind one Caddy, with
  one shared Postgres and one shared Redis. Adding a broker means another daemon to
  monitor, back up, secure, and pay for.
- **Transactional enqueue is possible** (even if not yet used) — see §A.3.
- One backup covers your data *and* your queue. With Redis-backed Celery, a Redis flush
  loses every pending job while your data survives; the two can disagree.
- Operational visibility is `psql`. Debugging "why didn't this job run?" is a `SELECT`.

**Alternatives & trade-offs.**

| | **Procrastinate** (chosen) | **Celery** (+Redis/RabbitMQ) | **RQ** (+Redis) | **Dramatiq** | **Temporal** | **BullMQ** (Node) |
| --- | --- | --- | --- | --- | --- | --- |
| Broker | **PostgreSQL** | Redis / RabbitMQ / SQS | Redis | Redis / RabbitMQ | Its own cluster | Redis |
| Extra infra | **None** | Yes | Yes | Yes | Substantial | Yes |
| Transactional enqueue | ✅ possible | ❌ needs Outbox | ❌ | ❌ | ✅ (via workflow) | ❌ |
| Throughput ceiling | ~hundreds–low-thousands/s (Postgres-bound) | Very high | High | High | High | High |
| Retries/backoff | ✅ built-in | ✅ rich | Basic | ✅ good | ✅ excellent | ✅ good |
| Scheduling/cron | ✅ periodic tasks | ✅ Beat (separate process) | Add-on | Add-on | ✅ | ✅ |
| Workflows / long-running orchestration | ❌ | Chains/chords (fragile) | ❌ | ❌ | ✅ **best in class** | Flows |
| Async-native | ✅ | Partial (improving) | ❌ | ❌ | ✅ | ✅ |
| Ecosystem / hiring | Small | **Huge** | Moderate | Moderate | Growing | Node-only |
| Operational complexity | **Lowest** | High (famously) | Low | Low | **Highest** | Low |

- **Why not Celery?** Celery is the default answer in Python and would work. The costs:
  another broker service; a configuration surface that is legendarily easy to
  misconfigure (`acks_late`, `visibility_timeout`, prefetch multiplier, result backends);
  and the dual-write problem for enqueue. On a single shared VPS, Celery's throughput
  headroom buys nothing while its operational weight costs daily.
- **Why not BullMQ?** It's excellent — but it's Node. This pipeline needs PyMuPDF,
  tiktoken, and the Python LangChain adapters. Running the worker in Node would mean an
  RPC hop to a Python service for the actual work.
- **Why not Temporal?** Temporal is the right answer when you have *durable, long-running,
  multi-step workflows with compensation* — sagas, human-in-the-loop approvals,
  month-long processes. Here the "workflow" is a four-step pipeline that completes in
  seconds to minutes and whose resumability is already captured by one column
  (`failed_step`). Temporal would add a server cluster, a new programming model, and a
  large conceptual tax for a problem that a `failed_step` string solves.
- **When would you outgrow Procrastinate?** When queue throughput starts to contend with
  application queries for the same Postgres connections and I/O — realistically thousands
  of jobs/second, or when job payloads/tables grow enough to affect autovacuum. The
  `IJobQueue` port means that migration touches four files.

### B.2 The AI/ML libraries used inside the worker

**PyMuPDF4LLM** (`infrastructure/document_parsing/pymupdf_pdf.py`) — a wrapper over PyMuPDF
(MuPDF C bindings) that emits **Markdown** rather than raw text, preserving headings,
lists, and table structure. That structural fidelity matters for RAG: a chunk that retains
its heading is far more useful as context than a flat paragraph.

The migration comment in `deploy/docker-compose.yml` tells the real story:

> *PDF parsing moved from Docling (torch, ~18GB image with the CUDA bundle it kept
> resolving) to PyMuPDF4LLM (pure Python, no model weights).*

**That is one of the best trade-off stories in this repo.** Docling produces better
extraction on complex layouts (it runs layout-detection models). But an 18 GB image on a
small VPS is not a deployment, it's a hostage situation. PyMuPDF4LLM: ~50 MB, no GPU, no
model download at boot, container memory limit of 512 MB. **Quality was traded for
deployability, deliberately and with the reasoning written down.**

*Alternatives:* `pdfplumber` (great tables, slow), `PyPDF2`/`pypdf` (pure Python, poor
layout), `unstructured.io` (excellent, heavy), AWS Textract / Azure Document Intelligence
(best OCR quality, per-page cost, network dependency).

**LangChain — machinery behind adapters, data type shared.** The dependency is split in
two deliberately, and being able to state the split is the interesting part.

The **machinery** — the chat client, the embeddings client, the splitter — stays confined
to [`langchain_adapters/`](apps/api/src/infrastructure/langchain_adapters/):

```python
# text_splitter.py
self.splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="cl100k_base",
    chunk_size=chunk_size_tokens,     # 800
    chunk_overlap=chunk_overlap_tokens,  # 120
)
```

- `RecursiveCharacterTextSplitter` tries separators in order (`\n\n`, `\n`, ` `, `""`),
  falling back only when a piece is still too big — so it prefers to split at paragraph
  then sentence boundaries.
- `from_tiktoken_encoder` measures in **tokens, not characters**, using OpenAI's
  `cl100k_base` BPE. That matters because both the embedding model's input limit and the
  LLM's context window are denominated in tokens.
- The **120-token overlap** exists so a sentence spanning a chunk boundary still appears
  whole in at least one chunk. Cost: ~15% storage and embedding overhead. That's the
  overlap trade-off in one sentence.

`ChatOpenAI` and `OpenAIEmbeddings` are used purely as OpenAI-compatible HTTP clients
pointed at a different `base_url`.

The **data type** — `langchain_core.documents.Document` — is treated as shared vocabulary
and is allowed anywhere, the way `uuid.UUID` or `datetime` are. Handlers produce them,
`KnowledgeAsset.documents` carries them, the chunker consumes them, the repository mappers
serialize them:

```python
# ingestion/handlers/pdf_handler.py — one Document per page
documents.append(
    Document(
        page_content=page_text,
        metadata={"locator": {"type": "page", "value": page.get("page_number")}},
    )
)
```

```python
# infrastructure/langchain_adapters/text_splitter.py
split_documents = self.splitter.split_documents(documents)  # metadata copied onto each split
```

> **The trade-off to be able to argue.** This project originally kept LangChain behind a
> single directory and used a private `{"text": ..., "locator": ...}` dict convention
> instead of `Document`. That maximised removability — drop LangChain and three files
> change — at the cost of a translation layer at every seam and an untyped shape enforced
> only by handler unit tests.
>
> The current split says: the *machinery* is what you actually want to swap (a different
> splitter, a different model client), and it is still one file each. The *data type* is
> not something you swap — it's a text-plus-metadata pair that any RAG library would model
> identically — so paying a translation cost to avoid depending on it bought type-safety
> nothing and cost clarity. Adopting the ecosystem's own type means LangChain loaders,
> splitters and retrievers drop in later without adapters at every boundary.
>
> The honest cost: `langchain_core` is now imported by `domain/entities/`, which is
> otherwise framework-free. If LangChain were dropped tomorrow, `Document` is a two-field
> Pydantic model that takes ten minutes to reimplement — but it is a real dependency in the
> purest layer, and pretending otherwise would be dishonest.
>
> What did *not* change: the retriever, prompt builder, RRF fusion, and citation logic are
> still hand-written domain code. LangChain's chains, agents, retrievers and memory are
> still entirely unused.
>
> *Alternatives:* the raw `openai` SDK (fewer deps, more glue), `LlamaIndex`
> (RAG-specialised, more opinionated about the index), `Haystack` (pipeline-first).

**tiktoken** — Rust-backed BPE tokenizer; used only for chunk-size measurement.

**youtube-transcript-api** — note the version floor comment in `pyproject.toml` and the
error-classification function in
[`youtube_handler.py`](apps/api/src/ingestion/handlers/youtube_handler.py), which turns
library exceptions into messages a user can act on:

```python
if isinstance(exc, (RequestBlocked, PoTokenRequired)):
    return ("YouTube is blocking transcript requests from this server. Download the "
            "video's audio and upload it as an audio source instead — you'll get the same "
            "timestamped citations.")
```

That is a nice piece of product thinking inside an infrastructure adapter: an
unrecoverable failure is converted into a **working alternative path**, not a dead end.

---

# 3.3 The Web / Frontend Layer

## A. Core Workflow & Architectural Mechanics

### A.1 Two Next.js apps, one origin

| | `apps/website` | `apps/web` |
| --- | --- | --- |
| Purpose | Marketing / landing | The product |
| Served at | `/` | `/app/*` (`basePath: "/app"`) |
| Auth | None | Required |
| Container | `kb-website` | `kb-web` |

```ts
// apps/web/next.config.ts
const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@kb/ui", "@kb/shared"],  // workspace packages ship raw TS/TSX
  basePath: "/app",     // so both apps share one origin behind Caddy
  output: "standalone", // self-contained server bundle for the Docker image
};
```

**Why one origin matters:** because `/app/*` and `/api/*` are the same origin as `/`, the
browser never issues a CORS preflight in production, cookies are trivially shared, and
there is exactly one TLS certificate. The cost is a routing rule in Caddy and the `basePath`
awareness sprinkled through the client (e.g. `LOGIN_PATH = "/app/login"` in `api.ts`,
because `window.location.assign` — unlike `next/navigation`'s router — knows nothing about
`basePath`).

`output: "standalone"` makes Next trace exactly the `node_modules` files the server needs
and emit a minimal `server.js` bundle — the difference between a ~1 GB and a ~150 MB image.

### A.2 The App Router structure and the `(app)` route group

```text
apps/web/src/app/
├── layout.tsx              # root layout (html/body, theme, toaster, AuthProvider)
├── login/page.tsx          # ← OUTSIDE the (app) group
├── register/page.tsx       # ← OUTSIDE the (app) group
└── (app)/                  # ← parenthesised = route GROUP: shares a layout, adds no URL segment
    ├── layout.tsx          #   RequireAuth → SourcesProvider → ConversationsProvider → AppShell
    ├── page.tsx            #   /app          — new conversation
    ├── c/[conversationId]/ #   /app/c/{id}   — an existing thread
    ├── library/            #   /app/library
    ├── sources/[sourceId]/ #   /app/sources/{id}
    ├── view/[sourceId]/    #   /app/view/{id} — citation viewer
    └── account/
```

```tsx
// apps/web/src/app/(app)/layout.tsx
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <SourcesProvider>
        <ConversationsProvider>
          <AppShell>{children}</AppShell>
        </ConversationsProvider>
      </SourcesProvider>
    </RequireAuth>
  );
}
```

**The route group earns its keep in one specific way:** login and register sit *outside*
it, so they render without the app shell and — importantly — **without mounting
`SourcesProvider`**, which fetches the library on mount. A signed-out user hitting
`/app/login` triggers zero authenticated API calls. Putting them inside the group would
mean a 401 storm on the login page.

### A.3 The API client — bearer tokens, silent refresh, and one retry

[`lib/api.ts`](apps/web/src/lib/api.ts) is the entire network layer, and its core is one
function:

```ts
async function request<T>(path: string, init: RequestInit = {}, opts: ReqOpts = {}): Promise<T> {
  const { auth = true, retry = true } = opts;
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });

  if (response.status === 401 && auth && retry) {
    if (await tryRefresh()) {
      return request<T>(path, init, { ...opts, retry: false });  // ← exactly one retry
    }
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }

  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as Promise<T>;
}
```

The `retry: false` on the recursive call is the important line: it bounds recursion to
depth 1. Without it, a server that always 401s (say, a rotated JWT secret) would produce
infinite recursion.

`API_URL` defaults to the relative `"/api"`, which is why the deploy workflow deliberately
does **not** bake an absolute `NEXT_PUBLIC_API_URL` into the image:

> *"apps/web and apps/website both default to relative paths … which is correct behind
> Caddy's single-origin routing and survives switching between the bare IP and either real
> domain without a rebuild."*

That comment records a real bug that was fixed: baking in an absolute URL sent users to
the bare-IP host on every login click regardless of which domain they arrived on. This is a
good example of the general lesson — **`NEXT_PUBLIC_*` variables are inlined at build time,
not read at runtime**, so anything environment-specific in them creates one image per
environment.

### A.4 Session storage: why a cookie and not `localStorage`

```ts
// apps/web/src/lib/auth.ts
function writeCookie(value: string, maxAgeSeconds: number | null): void {
  const secure = typeof window !== "undefined" && window.location.protocol === "https:";
  let cookie = `${KEY}=${value}; Path=/; SameSite=Lax`;
  if (maxAgeSeconds !== null) cookie += `; Max-Age=${maxAgeSeconds}`;
  if (secure) cookie += "; Secure";
  document.cookie = cookie;
}
```

The stated reason is behavioural, not security: a cookie without `Max-Age` is a **session
cookie** that dies with the browser, while one with `Max-Age` persists — which is exactly
what a "remember me" checkbox means. `localStorage` has no equivalent.

> **Be ready to critique this honestly.** These are **JS-readable** cookies (not
> `HttpOnly`), so they are XSS-exfiltratable — the same exposure as `localStorage`. The
> genuinely safer design is `HttpOnly; Secure; SameSite=Strict` cookies set by the API,
> with the browser never touching the token. That requires the API to read the cookie
> instead of the `Authorization` header, plus CSRF protection (which `SameSite=Strict` +
> a token largely handles). The mitigations that *are* present: 15-minute access tokens,
> rotating refresh tokens with reuse detection, and `SameSite=Lax`. Those bound the damage
> without eliminating it. Saying this plainly — "here's the exposure, here's the
> mitigation, here's what I'd do with more time" — is a much stronger answer than
> defending the choice.

### A.5 The streaming chat client — a hand-rolled SSE reader

The browser's built-in `EventSource` **cannot send custom headers** (no `Authorization`)
and only does `GET`. Since this endpoint is an authenticated `POST`, the client reads the
`fetch` body stream manually:

```ts
// apps/web/src/lib/api.ts
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

let finished = false;
try {
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // Normalise line endings first: SSE permits \r\n.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    // SSE frames are separated by a blank line; the last piece may be incomplete.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";       // ← keep the partial frame for the next read
    for (const frame of frames) dispatchFrame(frame, handlers);
  }
  if (buffer.trim()) dispatchFrame(buffer, handlers);
  finished = true;
} finally {
  if (!finished) await reader.cancel().catch(() => {});
  reader.releaseLock();
}
```

Five details that make this correct rather than merely working:

- **`decoder.decode(value, { stream: true })`** — a UTF-8 multi-byte character can be split
  across two network chunks. The `stream: true` flag makes `TextDecoder` hold the partial
  bytes rather than emitting a replacement character. Without it, non-ASCII answers get
  corrupted at random chunk boundaries.
- **`frames.pop()`** — TCP gives you arbitrary byte boundaries, not message boundaries.
  The last element after splitting on `\n\n` is *probably incomplete*, so it goes back into
  the buffer.
- **A malformed frame is skipped, not fatal** (`catch { return; }` around `JSON.parse`).
- **`\r\n` is normalised before splitting.** The split is the load-bearing line in the whole
  reader: if a proxy rewrote line endings, `split("\n\n")` would never match, no frame would
  ever dispatch, and the answer would silently arrive empty — no error, no `done`.
- **`reader.cancel()` on the abnormal path.** An `error` frame *throws* out of
  `dispatchFrame`, which unwinds the loop with the body half-consumed. Releasing the lock
  without cancelling leaves the fetch body dangling; cancelling releases the connection.

### A.6 Optimistic UI with honest rollback

[`use-ask.ts`](apps/web/src/lib/use-ask.ts) is a compact state machine worth studying:

```ts
// 1. Render both messages immediately with temporary local ids
setConversation((c) => ({ ...c, messages: [...c.messages, userMessage, assistantMessage] }));
setStreamingId(assistantId);

try {
  await api.streamAnswer(conversationId, question, {
    onConversation: (created) => { /* adopt the server's id + title */ },
    onDelta: (delta) => { streamed += delta; patchAssistant({ content: streamed }); },
    onCitations: (citations) => patchAssistant({ citations }),
    onDone: (done) => patchAssistant({ id: done.message_id, ... }),  // ← reconcile ids
  }, controller.signal);
} catch (err) {
  if (controller.signal.aborted) return;   // navigated away — not an error worth showing
  // 2. Drop BOTH optimistic messages: the server saved neither.
  setConversation((c) => ({
    ...c,
    messages: c.messages.filter((m) => m.id !== userId && m.id !== assistantId),
  }));
  setError(...);
}
```

**The frontend rollback mirrors the backend's persistence rule exactly.** The server writes
the question and the answer together, only *after* the stream completes, so on failure
nothing is persisted; the client therefore removes both bubbles. A reload after a failure
shows the same thing the screen showed — no phantom half-answer.

> **This is exactly where most implementations quietly diverge — and this one did too.**
> The comment above used to be a lie. The server appended the *user* message before
> retrieval, and `append_message` commits immediately, so every failure left an orphan
> question in the database while the UI deleted it from the screen. Worse, `recent_messages`
> fed that orphan into the *next* prompt, so each press of "Try again" made the prompt longer
> and more degenerate — a marginal failure became a deterministic one.
>
> The fix was to make the code match the claim rather than soften the claim: `_persist_turn`
> writes both messages at the end of a successful answer. The general lesson is that an
> optimistic-UI rollback is a *contract with the server*, and a comment asserting that
> contract is worth exactly nothing unless a test pins it — which is what
> `test_conversation_stream.py::NothingIsSavedUntilTheAnswerCompletesTest` now does.

Also note the `AbortController` wired to an unmount effect:

```ts
useEffect(() => () => abort.current?.abort(), []);
```

Navigating away mid-answer cancels the HTTP request rather than leaking a reader and a
server-side LLM stream.

### A.7 Resilient polling for ingestion progress

[`use-ingestion-poll.ts`](apps/web/src/lib/use-ingestion-poll.ts) polls
`GET /documents/{id}` every 2 s until a terminal status, with three specific guards:

```ts
const POLL_INTERVAL_MS = 2000;
const MAX_CONSECUTIVE_FAILURES = 5;   // tolerate a sleeping laptop / flaky wifi

const follow = useCallback((assetId: string) => {
  if (tracked.current.has(assetId)) return;   // (1) never double-follow one asset
  tracked.current.add(assetId);
  void (async () => {
    let failures = 0;
    try {
      while (!cancelled.current) {            // (2) stop on unmount
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        if (cancelled.current) return;
        let asset: KnowledgeAsset;
        try { asset = await api.getAsset(assetId); failures = 0; }
        catch {
          failures += 1;                      // (3) tolerate transient failures
          if (failures >= MAX_CONSECUTIVE_FAILURES) { handlers.current.onLost?.(...); return; }
          continue;
        }
        handlers.current.onUpdate(asset);
        if (isTerminal(asset.status)) { ... return; }
      }
    } finally { tracked.current.delete(assetId); }
  })();
}, []);
```

Plus a `handlers` ref so `follow` stays referentially stable:

```ts
const handlers = useRef({ onUpdate, onReady, onLost });
handlers.current = { onUpdate, onReady, onLost };
```

Without that ref, `follow` would be recreated on every parent render, restarting every
effect that depends on it — the classic React "infinite loop of polling loops" bug.

> **Interview: why polling and not WebSockets/SSE for progress?** Polling is stateless, so
> it survives a reload, a reconnect, and a horizontally-scaled API without sticky sessions
> or a pub/sub fan-out. The costs are latency (up to 2 s) and request volume (one request
> per in-flight source per 2 s). At this scale that's negligible. The upgrade path, if
> needed: reuse the existing SSE machinery for a `/documents/{id}/stream` endpoint, with
> the worker publishing progress through Postgres `LISTEN/NOTIFY` — which is why the
> pieces are already in the box.

### A.8 State management: React Context, no library

Three contexts, each with a stated reason:

| Context | Why it exists |
| --- | --- |
| `AuthProvider` | Session + status; wraps everything |
| `SourcesProvider` | *"One place the library lives, so the sidebar's 'N working' badge, the composer's 'answering from N ready sources' hint, and the library page can't disagree with each other."* |
| `ConversationsProvider` | *"Shared so asking a question on one screen updates the thread list on another."* |

Every value is `useMemo`'d and every callback `useCallback`'d, which is what keeps a
context provider from re-rendering its whole subtree on each parent render.

> **Trade-off vs. TanStack Query / SWR / Redux:** those give you caching, dedup, background
> refetch, and stale-while-revalidate for free — real value at scale. Here, three
> resources with hand-written invalidation are simpler than a cache layer, and the
> streaming + polling flows are custom enough that a query library's model wouldn't fit
> cleanly anyway. The honest cost: manual `refresh()` calls after every mutation, which is
> exactly what a query library's cache invalidation would automate. This is a *reasonable*
> choice at this size and the first thing to reach for as the surface grows.

### A.9 The `@kb/shared` package — one vocabulary, two apps

```ts
// packages/shared/src/sources.ts
/**
 * The product's user-facing vocabulary for sources.
 * The API speaks in stage names (`extracting`, `chunking`, `embedding`); the UI never does.
 */
export const statusCopy: Record<SourceStatus, { label: string; hint: string; tone: StatusTone }> = {
  queued:     { label: "Waiting to start",     hint: "In line — starting shortly.",      tone: "pending" },
  extracting: { label: "Reading the file",     hint: "Pulling the text out.",            tone: "active"  },
  chunking:   { label: "Breaking into passages", hint: "Splitting it into quotable pieces.", tone: "active" },
  embedding:  { label: "Making it searchable", hint: "Almost done — indexing passages.", tone: "active"  },
  ready:      { label: "Ready to use",         hint: "Answers can cite this source.",    tone: "ready"   },
  failed:     { label: "Couldn't be added",    hint: "Something went wrong — you can retry.", tone: "failed" },
};
```

This is an **Anti-Corruption Layer** at the presentation boundary: the backend's pipeline
vocabulary is translated exactly once, in one file, and both apps consume the translation.
The same module owns `formatLocator` (page N / slide N / `m:ss` timestamp) and
`progressForStatus` (the progress-bar percentage per stage).

## B. Library & Framework Deep Dives (Frontend)

### B.1 Next.js 15 / React 19

**Overview.** Next's App Router is built on **React Server Components**: components render
on the server by default, ship no JS, and can fetch data directly. `"use client"` marks the
boundary where interactivity (and hydration) begins.

**How this project actually uses it** — and this is worth being candid about: nearly every
component here is `"use client"`. `app/(app)/layout.tsx`, `page.tsx`, all three contexts,
and the chat components all opt out of server rendering. The app is, in practice, a **SPA
that happens to be served by Next**.

> **Is that wrong? No — but know the reasoning.** Everything behind the login wall depends
> on a bearer token held in a JS-readable cookie. Server Components can't read that token
> (it's not `HttpOnly`, and the RSC render happens before hydration), so server-rendering
> the library or a thread would produce an empty shell anyway. What Next still buys here:
> file-system routing, `output: "standalone"` for a small image, `basePath` for the
> single-origin deployment, the bundler and TS toolchain, and a clean path to server
> rendering later if the auth model moves to `HttpOnly` cookies.
>
> The `apps/website` marketing app, by contrast, is exactly what RSC is for — static
> content, no auth.
>
> *Alternatives:* **Vite + React Router** would be a more honest fit for the product app
> today (faster dev server, no RSC concepts to reason around) at the cost of losing the
> `basePath`/standalone/one-toolchain benefits and any future SSR. **Remix/React Router 7**
> would push toward cookie-session auth, which is arguably the better security model.

### B.2 Tailwind CSS v4 + the `@kb/ui` package

Tailwind v4 configures itself in CSS (`@import "tailwindcss"` + `@theme`) rather than a
`tailwind.config.js`, and its new Rust-based engine (Oxide) is dramatically faster. Design
tokens live in [`packages/ui/src/theme.css`](packages/ui/src/theme.css) and primitives in
`packages/ui/src/primitives/`, consumed by both apps via `transpilePackages`.

*Alternatives:* CSS Modules (scoped, no utility vocabulary), styled-components /
Emotion (runtime cost, and awkward with RSC), vanilla-extract (zero-runtime, more setup),
shadcn/ui (copy-in components — essentially what `@kb/ui` is, hand-rolled).

### B.3 pnpm workspaces + Turborepo

**pnpm** uses a content-addressable store with hard links, so a dependency shared by three
workspace packages is on disk once. Its strict, non-flat `node_modules` also prevents
"phantom dependencies" (importing a package you never declared) — which npm/yarn's
hoisting silently allows.

**Turborepo** builds a task graph from `turbo.json`:

```json
{ "tasks": { "build": { "dependsOn": ["^build"], "outputs": [".next/**", "dist/**"] } } }
```

`^build` means "build my dependencies first". `outputs` declares what to cache, so an
unchanged package is restored from cache instead of rebuilt.

Note `globalPassThroughEnv` — Turbo hashes the environment as part of its cache key, so
env vars must be explicitly allowlisted. That's why every `NEXT_PUBLIC_*` and backend
variable is enumerated there.

*Alternatives:* **Nx** (more powerful, more opinionated, heavier), **Lerna** (largely
superseded), plain **pnpm scripts** (fine until the task graph matters).

---

# 3.4 The Data Layer

## A. Core Workflow & Architectural Mechanics

### A.1 The schema

```
tenants ──┬──< users ──< refresh_tokens
          │       (NOT TenantScoped — read pre-auth under system_scope)
          │
          └──< knowledge_bases ──< knowledge_assets ──< chunks ──< embeddings
                                          │              └─ fts (GENERATED tsvector)
                                          ├──< ingestion_jobs ──< ingestion_job_events
                                          │
              conversations ──< messages (citations JSONB, GIN indexed)

   Every table below `tenants` carries BOTH tenant_id and user_id (the TenantScoped mixin).
```

The **`tenant_id` denormalisation is deliberate**: `chunks` could reach its tenant through
`knowledge_assets → knowledge_bases`, but storing it on the row means both the ORM filter
and the RLS policy can key on the row itself — **no join in the security predicate**.
A security check that requires a join is a security check that can be optimised away by a
future query rewrite.

Similarly, `user_id` is stored *independently* of `tenant_id` even though there is one user
per tenant today — so growing to multiple users per workspace needs no migration on domain
tables.

### A.2 The two-layer tenant isolation

**Layer 1 — the ORM auto-filter** ([`database/tenancy.py`](apps/api/src/infrastructure/database/tenancy.py)):

```python
def _on_do_orm_execute(state) -> None:
    if state.is_column_load or state.is_relationship_load: return
    if not (state.is_select or state.is_update or state.is_delete): return
    if in_system_scope() or not _touches_tenant_scoped(state): return
    # Resolve the tenant OUTSIDE the lambda (fail closed if unset) and close over the value
    # — SQLAlchemy's lambda cache extracts it as a bound parameter but forbids calling
    # functions inside the lambda itself.
    tenant_id = current_tenant_id()
    state.statement = state.statement.options(
        with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tenant_id, include_aliases=True)
    )
```

`do_orm_execute` fires for **every** ORM SELECT/UPDATE/DELETE, and `with_loader_criteria`
applies the predicate to the entity *everywhere it appears* — including eager loads and
relationship traversals. That last part is the reason this is better than a base-query
helper: `asset.chunks` gets filtered too, without anyone remembering to filter it.

The comment about resolving `tenant_id` outside the lambda is a real SQLAlchemy constraint
worth knowing: `with_loader_criteria`'s lambda is *analysed and cached*; calling a function
inside it would either be evaluated once and frozen, or rejected outright.

```python
def _on_before_flush(session, _ctx, _instances) -> None:
    if in_system_scope(): return
    for obj in session.new:
        if not isinstance(obj, TenantScoped): continue
        if getattr(obj, "tenant_id", None) is None: obj.tenant_id = current_tenant_id()
        if getattr(obj, "user_id", None) is None:   obj.user_id  = current_user_id()
```

Inserts are **stamped**, so no repository ever passes a tenant. Combined, reads are filtered
and writes are attributed, automatically and unforgettably.

**Layer 2 — Postgres Row-Level Security** ([`0001_initial.py`](apps/api/alembic/versions/0001_initial.py)):

```python
_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)

for table in DOMAIN_TABLES:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} "
               f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})")
```

The GUC is set per transaction by a third listener:

```python
def _on_after_begin(session, transaction, connection) -> None:
    if in_system_scope():
        connection.exec_driver_sql("SELECT set_config('app.tenant_bypass', 'on', true)")
        return
    tenant_id = try_current_tenant_id()
    if tenant_id is not None:
        connection.exec_driver_sql(
            "SELECT set_config('app.current_tenant', %s, true)", (str(tenant_id),)
        )
```

Four subtleties here, each of which is an interview answer on its own:

1. **`set_config(..., is_local => true)` rather than `SET`.** `SET` doesn't accept bind
   parameters (so you'd be string-concatenating a UUID into SQL — an injection surface),
   and `is_local => true` makes the setting **transaction-scoped**, which is what makes it
   safe under connection pooling. A session-scoped `SET` would leak one request's tenant
   to the next request that got the same pooled connection. **This is the single most
   important detail in the RLS implementation.**
2. **`FORCE ROW LEVEL SECURITY`.** Plain `ENABLE` exempts the table *owner*. `FORCE` makes
   the policy apply to the owner too.
3. **A non-superuser role is required.** Superusers bypass RLS entirely, which is why
   `create_app_role.sql` exists and why `APP_DATABASE_URL` is separate from
   `DATABASE_URL`. Migrations and Procrastinate keep the superuser role; ORM sessions use
   `kb_app`.
4. **Unset GUC = fail closed.** `current_setting('app.current_tenant', true)` returns
   `NULL` when unset; `NULLIF(...)::uuid` is `NULL`; `tenant_id = NULL` is `NULL`, which is
   not `TRUE` — so **zero rows**. The database's default is deny.

> **Why two layers at all?** The ORM filter is the primary defence, and it's the one with
> good error messages. But it only covers **ORM statements**. Raw SQL, a CTE,
> `session.get()`, a `text()` query, or a future bug that bypasses the listener would slip
> straight past it. RLS catches all of those, in the database, where no application code
> can be wrong.
>
> This is precisely why `EmbeddingRepository._ready_chunks_base` is built from ORM
> `select()` constructs rather than raw SQL, with the reasoning written in the docstring:
> *"a raw-SQL or CTE query would silently escape it and leave only RLS, which is dormant
> whenever `APP_DATABASE_URL` is unset."*

**The one authorised door out** is `system_scope()`:

```python
@contextmanager
def system_scope() -> Iterator[None]:
    """The single, auditable "cross-tenant door": registration (creating the tenant/user
    before any context exists), login/refresh (reading tenants/users pre-auth), migrations,
    seeds, and a future break-glass path."""
    token = _system_scope.set(True)
    try: yield
    finally: _system_scope.reset(token)
```

Auditing this system's tenant safety = `grep -rn "system_scope" apps/api/src/` and reading
each of the handful of hits.

### A.3 Session management — two lifetimes, one factory

```python
# apps/api/src/infrastructure/database/session.py
engine = create_engine(_settings.app_database_url or _settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
register_tenant_guards(SessionLocal)   # ← guards attach to EVERY session this factory makes
```

- `pool_pre_ping=True` issues a cheap `SELECT 1` before handing out a pooled connection,
  which kills the classic "stale connection after the DB restarted / a firewall idled the
  socket" error.
- `autoflush=False` means the ORM won't silently flush pending changes before every query
  — predictable, at the cost of having to be deliberate about ordering.
- **`register_tenant_guards(SessionLocal)`** is the crucial line: the isolation listeners
  are attached to the *factory*, so the HTTP session and the worker session are protected
  identically. There is no way to get an unguarded session without deliberately
  constructing one.

The two lifetimes differ only in transaction ownership:

```python
def get_db():                      # HTTP: repositories own commit/rollback
    db = SessionLocal()
    try: yield db
    finally: db.close()

@contextmanager
def session_scope():               # worker/stream: the scope owns the transaction
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

> **A candid critique to have ready.** In the HTTP path, each repository commits
> independently (`ChunkRepository._commit`, `KnowledgeAssetRepository._commit`, …). That
> means a request is **several transactions, not one** — so `enqueue_ingestion` can commit
> the asset and then fail before committing the job, leaving a partially-created state.
> The auth service is the exception and does it properly, using the `Session` itself as an
> `IUnitOfWork` so registration's tenant + user inserts are atomic. Extending that pattern
> (one transaction per request, committed at the boundary) is the highest-value
> refactor in the data layer, and naming it unprompted is a strong signal.

### A.4 Repositories and the domain/persistence split

Each repository maps between SQLAlchemy models and domain dataclasses through
[`repositories/mappers.py`](apps/api/src/infrastructure/repositories/mappers.py). The
domain layer therefore never holds an ORM object — no lazy-loading surprises leaking into
business logic, and no `DetachedInstanceError` after a session closes.

One nice N+1 avoidance to point at:

```python
# apps/api/src/http/routes/documents.py — list_assets
assets = KnowledgeAssetRepository(db).list_current(kb.id)
counts = ChunkRepository(db).count_by_asset([asset.id for asset in assets])  # ONE grouped query
```

```python
# apps/api/src/infrastructure/repositories/postgres_chunk_repository.py
def count_by_asset(self, asset_ids: list[UUID]) -> dict[UUID, int]:
    if not asset_ids: return {}
    rows = self.db.execute(
        select(ChunkModel.knowledge_asset_id, func.count(ChunkModel.id))
        .where(ChunkModel.knowledge_asset_id.in_(asset_ids))
        .group_by(ChunkModel.knowledge_asset_id)
    ).all()
    return {asset_id: int(count) for asset_id, count in rows}
```

...and one place where the N+1 was consciously *accepted*:

```python
# apps/api/src/http/routes/jobs.py
# The N asset lookups are bounded by the small `list_recent` limit.
for job in jobs:
    asset = asset_repo.get(job.asset_id)
```

Bounded at 50, on an internal dashboard. Knowing when *not* to optimise is as much a signal
as knowing how.

### A.5 Hybrid retrieval — the most interesting query in the system

Retrieval runs **two arms** over the same chunks and fuses them by rank.

**Arm 1 — dense (semantic):**

```python
distance = EmbeddingModel.vector.cosine_distance(query_embedding)
rows = self.db.execute(
    self._ready_chunks_base(knowledge_base_id, distance).order_by(distance).limit(top_k)
).all()
```

**Arm 2 — lexical (keyword):**

```python
tsquery = func.websearch_to_tsquery("english", query_text)
rows = self.db.execute(
    self._ready_chunks_base(knowledge_base_id, distance)
    .where(ChunkModel.fts.op("@@")(tsquery))
    .order_by(func.ts_rank_cd(ChunkModel.fts, tsquery).desc())
    .limit(top_k)
).all()
```

**Shared skeleton — identical visibility rules for both arms:**

```python
@staticmethod
def _ready_chunks_base(knowledge_base_id: UUID, distance):
    return (
        select(ChunkModel, KnowledgeAssetModel, (1 - distance).label("score"))
        .join(EmbeddingModel, EmbeddingModel.chunk_id == ChunkModel.id)
        .join(KnowledgeAssetModel, KnowledgeAssetModel.id == ChunkModel.knowledge_asset_id)
        .options(joinedload(ChunkModel.asset))
        .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
        .where(KnowledgeAssetModel.superseded_at.is_(None))     # ← only current versions
        .where(KnowledgeAssetModel.status == AssetStatus.READY.value)  # ← only fully-ingested
    )
```

Both arms return the **same tuple shape including the cosine score**, so the threshold,
the prompt's `score=` label, and the UI's relevance percentage work identically regardless
of which arm surfaced a chunk. Note that in the lexical arm the cosine similarity is a
*selected column*, not an ordering — so it's an exact computation over ≤30 rows and never
touches the vector index.

**Fusion — Reciprocal Rank Fusion** ([`retrieval/fusion.py`](apps/api/src/retrieval/fusion.py)):

```
score(item) = Σ_arms  weight_arm / (k + rank_in_arm)          k = 60
```

Why RRF rather than normalising and adding scores: cosine similarity (0–1) and
`ts_rank_cd` (unbounded, corpus-dependent) live on incomparable scales, and any
normalisation you invent is arbitrary and drifts with the corpus. RRF throws the scores
away and keeps only **ranks**, giving two properties you actually want:

- An item found by **both** arms outranks one found brilliantly by only one.
- The `k` constant damps the head of each list, so one confidently-wrong arm can't drag
  its top hit to the top of the fused result.

`k = 60` is from Cormack, Clarke & Büttcher (SIGIR 2009) — the paper's empirically-chosen
default.

**Over-fetching**, from `Settings`:

```python
retrieval_top_k: int = 5
retrieval_candidate_multiplier: int = 6   # each arm fetches 5 × 6 = 30 candidates
```

with a comment that shows real depth:

> *"Keep the product (5 × 6 = 30) under pgvector's default `hnsw.ef_search` of 40, or raise
> that to match."*

`ef_search` is HNSW's search-time beam width — asking for more results than `ef_search`
silently degrades recall. Over-fetching also lets the score threshold filter a *pool* rather
than an already-truncated list: a weak 5th match gets **replaced** rather than leaving a
hole.

And an honest observability hook:

```python
logger.info("retrieval_fused", ...,
    # How many of the winners the lexical arm contributed that dense had not already found.
    # If this is persistently 0, the lexical arm is earning nothing.
    lexical_only_promoted=sum(1 for r in results if r.chunk.id not in {d.chunk.id for d in dense}),
)
```

That is a metric designed to *disprove* the feature's value — which is how you should
instrument a heuristic.

### A.6 The migration that fixed a silent bug

[`0006_hybrid_retrieval.py`](apps/api/alembic/versions/0006_hybrid_retrieval.py) is worth
reading in full; two lessons:

**1. An IVFFlat index built on an empty table is worthless.** IVFFlat derives its centroids
by k-means over *existing rows*. Migration `0001` created it on a table with zero rows.
It never errored — it just silently returned worse neighbours forever. HNSW is preferred
because it builds its graph incrementally, so the failure mode cannot recur by
construction.

**2. Graceful degradation across environments.** HNSW needs pgvector ≥ 0.5, and production
is a *shared* Postgres this repo doesn't control — so the migration tries HNSW inside a
`SAVEPOINT` and falls back to a rebuilt IVFFlat:

```python
try:
    with connection.begin_nested():   # SAVEPOINT: a failed CREATE would otherwise abort
        connection.execute(sa.text("CREATE INDEX ... USING hnsw (vector vector_cosine_ops) ..."))
except Exception:
    connection.execute(sa.text("CREATE INDEX ... USING ivfflat (...) WITH (lists = 100)"))
```

The `begin_nested()` is essential: in Postgres, a failed statement aborts the whole
transaction unless a savepoint scopes it.

**And the FTS column:**

```python
_FTS_EXPRESSION = "to_tsvector('english', text)"
```

```python
# apps/api/src/infrastructure/database/models.py
fts = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), nullable=True)
```

`GENERATED ALWAYS ... STORED` means **Postgres maintains it**; the ingestion pipeline never
writes it, and the ALTER backfills every existing row. `Computed(...)` tells SQLAlchemy to
omit the column from INSERTs/UPDATEs. The two-argument `to_tsvector('english', text)` form
is required because `to_tsvector` is only `IMMUTABLE` when the config is explicit — and a
generated column requires an immutable expression.

### A.7 Citations as JSONB, with a GIN index

```python
# models.py
citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
__table_args__ = (
    Index("ix_messages_citations", "citations",
          postgresql_using="gin", postgresql_ops={"citations": "jsonb_path_ops"}),
)
```

```python
# postgres_conversation_repository.py — "which answers cited this source?"
.where(MessageModel.citations.contains([{"asset_id": str(asset_id)}]))
```

Storing citations **denormalised, verbatim** is a deliberate immutability choice: an answer
from a year ago re-reads correctly even if the source was re-ingested, renamed, or deleted.
Re-running retrieval to reconstruct them would produce *today's* answer, not the one that
was given. `jsonb_path_ops` is the smaller, faster GIN variant that supports exactly the
containment operator (`@>`) this query uses.

## B. Library & Framework Deep Dives (Data layer)

### B.1 SQLAlchemy 2.0

**Overview.** Two layers: **Core** (a SQL expression language) and the **ORM** (identity
map, unit of work, relationship loading) built on it. 2.0 unified them around
`select()` and added full typing via `Mapped[...]` / `mapped_column()`. The **Unit of
Work** pattern means `session.add()` doesn't emit SQL — the session accumulates changes and
flushes them in dependency order at commit.

**Why it was chosen (and why nothing else would have worked here).** The tenant isolation
design *depends* on SQLAlchemy-specific extension points:

- `do_orm_execute` — intercept and rewrite every ORM statement.
- `with_loader_criteria` — apply a predicate to an entity wherever it appears, including
  eager loads.
- `before_flush` — stamp new objects.
- `after_begin` — run a statement at the start of every transaction (the RLS GUC).

Plus: `pgvector.sqlalchemy.Vector` and `TSVECTOR`/`JSONB`/`Computed` support mean the whole
hybrid-retrieval query is expressible in the ORM — and therefore covered by the tenant
filter.

**Alternatives & trade-offs.**

| | **SQLAlchemy 2.0** (chosen) | **Django ORM** | **Tortoise / SQLModel** | **Prisma (Python)** | **Raw psycopg** |
| --- | --- | --- | --- | --- | --- |
| Query power | **Exceptional** (window fns, CTEs, dialect ops) | Good; awkward at the edges | Limited | Limited | Total |
| Global query interception | ✅ event hooks | ❌ (custom managers, opt-in per model) | ❌ | ✅ client extensions | N/A |
| pgvector | ✅ first-class | Third-party | Limited | Limited | Manual |
| Async | ✅ `AsyncSession` | Partial | ✅ native | ✅ | ✅ |
| Migrations | Alembic (separate, powerful) | Built-in, excellent | Aerich | Built-in | Manual |
| Learning curve | **Steep** | Moderate | Gentle | Gentle | N/A |
| Typing | Strong in 2.0 | Weak | Strong | Strong | N/A |

- **SQLModel** (Pydantic + SQLAlchemy, by FastAPI's author) is tempting because it removes
  the model↔schema mapper layer. The cost is exactly what this codebase wants to keep:
  merging your persistence model and your API contract means a schema change is a wire
  change. The explicit `mappers.py` is the price of that separation, and it's cheap.
- **Prisma's client extensions** are the closest analogue to the tenancy design here —
  which the code acknowledges directly: *"Query-level tenant isolation — the SQLAlchemy
  equivalent of a Prisma client extension."*
- **Why not async SQLAlchemy?** Because the app is sync-first (§C.1) and running sync
  sessions in a threadpool is simpler and less error-prone than an async session that must
  never be shared across tasks. Going async would be a whole-stack change (async boto3,
  async Procrastinate tasks), not a swap.

### B.2 PostgreSQL + pgvector

**Overview.** pgvector adds a `vector` type and three index types:

| Index | Build | Query | Recall | Notes |
| --- | --- | --- | --- | --- |
| none (exact) | — | O(n) | 100% | Fine to ~10k rows |
| **IVFFlat** | k-means over existing rows | probe `lists` clusters | Tunable (`probes`) | ⚠️ Must be built on populated data |
| **HNSW** (current) | Incremental graph | Beam search (`ef_search`) | Higher | More memory, slower build |

**Why one database for everything.** Vectors, relational data, full-text search, *and* the
job queue all live in one Postgres. The wins: one backup, one connection story, one thing
to monitor, **transactional consistency between an embedding and its chunk** (a dedicated
vector DB gives you a dual-write problem between "the chunk row" and "the vector"), and no
extra service on a small VPS.

**Alternatives & trade-offs.**

| | **pgvector** (chosen) | **Pinecone** | **Qdrant / Weaviate** | **Chroma** | **Elasticsearch / OpenSearch** |
| --- | --- | --- | --- | --- | --- |
| Ops burden | **None extra** | None (SaaS) | A service to run | Embedded or a service | Heavy (JVM, cluster) |
| Cost | Included | Per-vector, adds up | Self-host cost | Free | Infra cost |
| Metadata filtering | **Full SQL** — arbitrary joins | Limited filter DSL | Good | Basic | Good |
| Transactions with domain data | ✅ same DB | ❌ | ❌ | ❌ | ❌ |
| Hybrid (vector+keyword) | ✅ tsvector in the same query | Partial | ✅ | ❌ | ✅ **best-in-class BM25** |
| Scale ceiling | ~1–10M vectors comfortably | Billions | Hundreds of millions | Small | Billions |
| Multi-tenancy | ✅ **RLS covers vectors too** | Namespaces | Collections/payload filter | Manual | Index/routing |

The multi-tenancy row is the decisive one for *this* system: because embeddings are a
Postgres table, **the same RLS policy that protects `chunks` protects the vectors**. With a
separate vector store, tenant isolation for vectors would be a second, independent
implementation — a second thing to get wrong.

The honest ceiling: at tens of millions of vectors, HNSW index memory and build time become
the constraint, and a dedicated store starts to win. That's several orders of magnitude
away from this system.

### B.3 Alembic

**Overview.** SQLAlchemy's migration tool: a directed graph of revisions
(`down_revision` links them), with `upgrade()`/`downgrade()` functions and
`--autogenerate` diffing models against the live schema.

**How it's used here — with judgement.** Autogenerate is a starting point, not the output:
`0001` is a **hand-collapsed baseline** (six earlier revisions squashed after a reset, with
`tenant_id`/`user_id` `NOT NULL` from birth rather than the add-nullable/backfill/tighten
dance), and `0006` contains logic autogenerate could never produce (savepoint, index-type
fallback, a generated column).

**The operational hazard, and how it's handled.** Two containers run the same image; both
must not migrate concurrently:

```sh
# apps/api/docker-entrypoint.sh
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    alembic upgrade head
    procrastinate --app=src.infrastructure.queue.app.app schema --apply || echo "    (schema already present)"
fi
exec "$@"
```

Only the `api` service sets `RUN_MIGRATIONS=1`; the worker's `depends_on: api: {condition: service_healthy}`
means it starts only after the API is healthy — i.e. after migrations finished.

> **The honest limitation:** this is coordination-by-convention, not a lock. It works for
> one API replica. With two API replicas both setting `RUN_MIGRATIONS=1`, they race.
> Alembic does take a transaction-level lock in many cases, but the robust answers are a
> Postgres advisory lock around `upgrade`, or a dedicated migration job/init-container that
> runs exactly once. Naming this is a strong signal.
>
> Also note: `0001`'s docstring flags that **DDL is not subject to RLS, but data migrations
> are** — any future data migration touching a scoped table must set `app.current_tenant`
> or `app.tenant_bypass` itself, because the Alembic connection has no `after_begin`
> listener.

*Alternatives:* Django migrations (better, but tied to Django), `sqlx`/`dbmate`/`Flyway`
(plain SQL files — simpler to review, no Python logic like `0006` uses), Prisma Migrate.

---

# 4. Interview Prep & Deep-Dive Concepts

## 4.1 Design patterns in this codebase (with exact locations)

| Pattern | Where | What it buys |
| --- | --- | --- |
| **Ports & Adapters (Hexagonal)** | `domain/interfaces/` are ports; `infrastructure/` are adapters | Business logic testable without Postgres, S3, or an LLM |
| **Composition Root** | [`composition.py`](apps/api/src/composition.py) | One place knows concrete types; HTTP and worker wire up identically |
| **Repository** | `infrastructure/repositories/*` behind `domain/interfaces/repositories.py` | Domain never sees SQLAlchemy; ORM objects never escape |
| **Unit of Work** | `IUnitOfWork` (the `Session`) in `AuthService`; `session_scope()` | Registration's tenant+user inserts are atomic |
| **Registry** | [`ingestion/registry.py`](apps/api/src/ingestion/registry.py) | Adding a source type = one `register()` line + one handler |
| **Strategy** | `ISourceHandler` implementations (pdf/youtube/pptx/audio/markdown) | Per-source acquire+parse, one interface |
| **Adapter** | `langchain_adapters/`, `filebase_adapter.py`, `pymupdf_pdf.py` | Third-party surface confined to one file each |
| **Chain of Responsibility** | The `Authenticator` list in `AuthenticationMiddleware` | New credential types append, never branch |
| **Decorator** | [`@tenant_task`](apps/api/src/infrastructure/queue/tenant_task.py) | Cross-cutting tenant binding, applied once for all tasks |
| **Middleware / Pipeline** | The ASGI middleware stack | Cross-cutting concerns without touching handlers |
| **Ambient Context** | `contextvars` in [`core/tenant_context.py`](apps/api/src/core/tenant_context.py) | Tenant flows to the ORM without threading a parameter through 8 layers |
| **Singleton (scoped)** | `_cache`, `_google_verifier`, `@lru_cache get_settings` | Connection pools / JWKS caches actually get reused |
| **Anti-Corruption Layer** | [`packages/shared/src/sources.ts`](packages/shared/src/sources.ts) | Backend pipeline vocabulary translated once for the UI |
| **Provider (React)** | `auth-context`, `sources-context`, `conversations-context` | One source of truth per resource across screens |
| **Optimistic UI + rollback** | [`use-ask.ts`](apps/web/src/lib/use-ask.ts) | Instant feedback whose failure mode matches server truth |
| **State Machine** | `AssetStatus` × `failed_step` in `_run_pipeline` | Resumable, inspectable ingestion |
| **Event Sourcing (lite)** | `ingestion_job_events` | Queryable, user-facing audit trail |
| **Fail-closed / default-deny** | `current_tenant_id()` raises; RLS returns 0 rows; `@tenant_task` refuses | Mistakes become errors, not leaks |

## 4.2 Failure modes & edge cases

### Under load

| Pressure point | What happens | Mitigation present / missing |
| --- | --- | --- |
| **SSE stream torn down after every answer** | `set`/`reset` of a contextvar across `iterate_in_threadpool`'s per-frame `copy_context()` raised out of a `finally`, killing the connection *after* a fully successful answer | ✅ **Fixed** — the redundant binding is gone and `reset_tenant_context` fails closed instead of raising. Pinned by `test_conversation_stream.py`. See §C.3 |
| **Event loop blocked by `upload_document`** | `async def` handler does a blocking S3 PUT + 5 commits → all concurrent requests in that process stall | ❌ **Not mitigated.** A fix (plain `def` + `test_routes_are_sync.py`) was written and measured — 2.17s blocked vs 0.18s free — but was lost before it landed; the handler is `async def` again. Re-apply |
| **DB connection pool exhaustion** | Default `pool_size=5, max_overflow=10` = 15 conns; the 16th waits 30s then raises | ⚠️ Unconfigured. Fix: size explicitly against `max_connections ÷ replicas` |
| **Threadpool saturation** | 40 anyio threads; the 41st sync request queues | Rarely reached before the pool limit above |
| **Whole file in memory** | `await file.read()` and `download()` load the entire object | Only audio is capped (`max_audio_upload_bytes = 100 MB`). A 500 MB PDF is unbounded. Fix: stream to S3 multipart |
| **Embedding API rate limits / latency** | The batch call can 429 or hang | ⚠️ No explicit timeout or backoff on the LangChain client; only the job-level `RetryStrategy(3, exponential 5s)` — which re-runs the whole embed step |
| **LLM stream stalls mid-answer** | SSE connection hangs open, holding an anyio worker *and* a DB session | ✅ `ChatOpenAI(timeout=90s, max_retries=1)` — was the library default of **600s**. Client has `AbortController` on unmount. ❌ Still no SSE heartbeat, so an idle proxy can cut the silent window before the first token |
| **Worker concurrency** | One worker, default concurrency, processes jobs serially | `procrastinate worker --concurrency N` and `--scale worker=N` both available |
| **Postgres as broker** | Queue polling/LISTEN competes with app queries for connections | Fine at this scale; the ceiling is thousands of jobs/sec |

### Retries

- **Queue level:** `RetryStrategy(max_attempts=3, exponential_wait=5)` → ~5s, ~10s, ~20s.
- **Pipeline level:** `failed_step` makes the retry *resume* rather than restart.
- **Manual:** `POST /documents/{id}/retry` → `reset_for_retry` preserves the attempt count
  (so history isn't lost) and re-defers.
- **HTTP level:** the frontend retries a 401 exactly once, after a silent token refresh.
- **YouTube:** one extra in-handler retry with a 1.5s delay, because YouTube's blocking is
  partly probabilistic.
- ⚠️ **Gap:** no dead-letter queue. After 3 attempts the job is `failed` and sits there.
  A user or an operator must notice. The `/jobs` dashboard makes that possible but nothing
  alerts.

### Race conditions & concurrency

| Race | Status |
| --- | --- |
| Two workers grabbing the same job | ✅ Solved by Procrastinate's `SELECT ... FOR UPDATE SKIP LOCKED` |
| Two uploads of the same filename simultaneously | ⚠️ Both read `latest_for_filename` → both compute `version = n+1` → the `uq_asset_lineage_version` constraint makes one fail. It fails *safely* (constraint violation), but with an ugly 500 rather than a retry |
| Retry while a job is still running | ⚠️ `retry()` only guards on `status == FAILED`, and the pipeline sets `FAILED` before the queue's own retry fires — a user clicking Retry at that moment can enqueue a duplicate. Both are idempotent (replace-semantics), so the outcome is correct but the work is duplicated |
| `ensure_default()` called concurrently on a new tenant | ⚠️ Two requests can both find no KB and both insert. No unique constraint prevents it. Fix: a partial unique index on `(tenant_id)`, or `ON CONFLICT DO NOTHING` |
| Frontend double-polling one asset | ✅ Guarded by the `tracked` `Set` in `useIngestionPoll` |
| Tenant leaking between pooled connections | ✅ Prevented by `set_config(..., is_local => true)` being transaction-scoped |
| Streaming generator + contextvars across threadpool hops | ✅ **Was a live bug, now fixed** — see §C.3. The `reset` half of the pair raised on every stream; the binding is gone and `reset_tenant_context` now fails closed rather than raising |
| A failed answer polluting the conversation history | ✅ **Was a live bug, now fixed** — the question used to be appended *and committed* before generation, so every failure left an orphan turn that `recent_messages` fed into the next prompt, making each retry worse. `_persist_turn` now writes question and answer together, only once the answer is complete |

### Deadlocks

Low risk by construction: no explicit `SELECT ... FOR UPDATE` in application code, and
short transactions. The theoretical risk is `replace_for_asset`'s DELETE-then-INSERT if two
workers processed the same asset simultaneously — prevented by `SKIP LOCKED` at the queue
level.

### Network failures

| Boundary | Handling |
| --- | --- |
| Browser → API | One silent refresh + retry on 401; a redirect to `/login` on failure; 5-failure tolerance in the ingestion poll |
| API → Postgres | `pool_pre_ping=True` catches dead pooled connections |
| Worker → S3 | `FileStorageError` → pipeline `FAILED` → queue retry |
| Worker → AI gateway | Exception → `FAILED` → queue retry. ❌ No circuit breaker; a provider outage burns all 3 attempts in ~35s |
| Worker → YouTube | Classified into user-actionable messages, with an alternative path offered |
| API → Filebase (signing) | Local HMAC, no network call — presigning cannot fail on the network |

### Data-integrity edge cases handled well

- **Empty LLM completion** → `raise RuntimeError("The model returned an empty answer")`
  rather than persisting an empty assistant message.
- **Zero chunks produced** → `raise ValueError("Source produced no indexable text chunks")`
  rather than a "ready" source with nothing in it.
- **Embedding dimension mismatch** → validated per vector against `expected_dimensions`,
  catching a silent model swap before it corrupts the index.
- **NUL bytes / control characters in extracted text** → `sanitize_text_for_storage` before
  anything reaches Postgres (` ` in a `text` column is a hard error).
- **`chunks.fts` missing** (code deployed ahead of migration `0006`) → `ProgrammingError`
  caught, degrade to dense-only with a warning instead of 500-ing every question.
- **Superseded versions** excluded from retrieval, so an old version of a re-uploaded
  document never contaminates answers.

## 4.3 Scalability & bottlenecks

### Scaling each tier independently

```
┌───────────── Stateless: scale horizontally, no coordination ─────────────┐
│  kb-web (Next)  ×N      kb-website ×N      kb-api (uvicorn) ×N           │
└──────────────────────────────────────────────────────────────────────────┘
┌───── Stateless, but bounded by DB + API rate limits ─────┐
│  kb-worker ×N, each with --concurrency C                 │
└──────────────────────────────────────────────────────────┘
┌───────────────── Stateful: the real ceiling ─────────────────┐
│  PostgreSQL: vertical first, then read replicas, then shard  │
└──────────────────────────────────────────────────────────────┘
```

**API tier.** Fully stateless — JWTs mean no server session, so no sticky sessions and no
shared session store. Scale by adding containers behind Caddy. *Blockers to fix first:* the
blocking `async def` upload handler (see §4.2 — it serialises the whole process), and the
implicit assumption that only one replica runs migrations.

**Worker tier.** `docker compose up --scale worker=N`, or `--concurrency C` per worker.
Because dequeue uses `SKIP LOCKED`, N workers need no coordination whatsoever. The real
limit is downstream: the embedding provider's rate limit and the DB connection budget
(`N × C` connections).

**Database.** The ceiling, and the thing to talk about in order:

1. **Connection pooling** — put **PgBouncer** in front, in *transaction* mode. Note the
   important interaction: transaction-mode pooling is compatible with this design
   *precisely because* the RLS GUC is set with `is_local => true` (transaction-scoped).
   A session-scoped `SET` would break under PgBouncer — a great "why does that detail
   matter?" answer.
2. **Read replicas** — retrieval is read-heavy and tolerates slight staleness. Route the
   two retrieval arms to a replica; keep writes on the primary.
3. **Partitioning** — `chunks` and `embeddings` by `tenant_id`, so each tenant's index is
   smaller and vacuum is cheaper.
4. **Extract the vector store** — the last resort, at tens of millions of vectors. The
   `IVectorStore` port means this is one adapter.

**Object storage.** Filebase/S3 is effectively infinitely scalable. The improvement worth
making is **presigned direct upload**: have the browser PUT straight to S3 and only tell
the API the key. That removes file bytes from the API entirely and eliminates the
memory-per-upload problem in one stroke.

**Caching (the unused Valkey).** The adapter and tenant-namespaced key builder already
exist. The highest-value targets, in order: (1) query-embedding cache — identical questions
are common and each costs an API call; (2) `GET /documents` list per tenant, invalidated on
ingest; (3) `/auth/me`. The key builder fails closed without a tenant, so cross-tenant
cache bleed is structurally impossible.

### The ranked bottleneck list

1. **LLM/embedding provider latency** — dominates every user-visible timing. Mitigations:
   streaming (already done — perceived latency is what matters), embedding cache,
   batching.
2. **Blocking I/O on the event loop in `upload_document`** — the one clear code-level bug.
   An `async def` handler calling a fully synchronous `enqueue_ingestion` (one S3 round-trip
   + five commits) stalls *every* concurrent request in the process. Measured at 2.17s
   blocked vs 0.18s free. Fix: make it plain `def`.
3. **DB connection pool sizing** — unconfigured defaults are the first thing to hit.
4. **Full-file-in-memory uploads** — a hard memory ceiling per concurrent upload, against
   a 512 MB container limit. Distinct from #2: same handler, different problem, and fixing
   #2 does not fix this one.
5. **Single Postgres for data + vectors + queue** — fine now, the eventual split point.
6. **The `/jobs` N+1** — bounded and internal; last on the list, correctly.

*Recently resolved:* the SSE stream teardown described in §C.3 — a contextvar `Token` reset
across `iterate_in_threadpool`'s per-frame context copies raised out of a `finally`, killing
the connection after every successful answer.

## 4.4 Top 5 interview questions, with model answers

---

### Q1. "Walk me through what happens when a user uploads a 50-page PDF. Why is any of it asynchronous, and what breaks if you made it synchronous?"

**Model answer.**

The request path is deliberately short. `POST /documents/upload` hits an `async def`
handler that reads the multipart body, sanitizes the filename, resolves the `SourceType`
from the extension and confirms a handler is registered — *failing fast with a 400 if not,
before anything is stored*. It then computes lineage: if a file with this name exists, the
new asset reuses its `lineage_id` and increments `version`. The bytes go to S3 under
`{tenant_id}/{asset_id}/{filename}` — tenant-prefixed so the bucket layout mirrors the
isolation boundary the database enforces. Then two rows: a `knowledge_assets` row with
status `queued` and an `ingestion_jobs` row. Finally `.defer()` inserts into
`procrastinate_jobs` and issues a `NOTIFY`. The client gets `202 Accepted` with the queued
asset and starts polling `GET /documents/{id}` every two seconds.

A worker wakes on the NOTIFY, dequeues via `SELECT ... FOR UPDATE SKIP LOCKED`, and the
`@tenant_task` decorator rebuilds the tenant contextvars from the payload — refusing to run
at all if they're absent. It then runs the pipeline: download from S3, PyMuPDF4LLM to
Markdown plus one Document per page, split into ~800-token chunks with 120 tokens of overlap,
one batch call to the embeddings API, insert vectors, mark `ready`, and supersede the
previous version. Every transition writes both a structlog line and an `ingestion_job_events`
row, which is what the UI's activity timeline renders.

**Why async:** parsing and embedding a 50-page PDF takes tens of seconds. Synchronously
that means an HTTP request open for 30+ seconds — which browsers, load balancers, and
proxies all time out. It also occupies a worker thread and a DB connection for that entire
window, so a handful of concurrent uploads exhausts the pool and the API stops serving
*everything*, including logins. And there'd be no retry story: a transient S3 or embedding
failure would just be a 500 the user has to recover from by re-uploading.

**What we get instead:** the API stays responsive under upload load; the worker scales
independently of the API; failures retry automatically with backoff; and because
`failed_step` is persisted, a retry resumes from where it broke rather than re-parsing the
PDF.

**One thing that had to be fixed to make that true:** the upload handler used to be
`async def`, so all of that blocking boto3 and SQLAlchemy work ran on the event loop —
the request returned fast, but it froze every *other* request in the process while the S3
PUT completed. It is now a plain `def`, which lets FastAPI run the whole thing in the
threadpool. A regression test walks the mounted routes and fails if any handler becomes a
coroutine again.

**Where I'd still push back:** `read()` pulls the entire upload into memory, which for
large files should become a presigned direct-to-S3 upload with the browser doing the PUT —
that removes the file bytes from the API process altogether.

---

### Q2. "You have a multi-tenant system. How do you guarantee tenant A can never see tenant B's data — and convince me you haven't missed a path?"

**Model answer.**

Two independent layers, both driven from one source of truth, with a default of deny.

The source of truth is a `contextvars` variable in `core/tenant_context.py`. It's set in
exactly two places: the `TenantContextMiddleware` for HTTP requests, and the `@tenant_task`
decorator for queue jobs. Reading it when unset **raises** — it's `current_tenant_id()`,
not `current_tenant_id_or_none()`.

**Layer 1, the ORM auto-filter.** A `TenantScoped` mixin adds `tenant_id`/`user_id` to
every domain model. A `do_orm_execute` listener appends a `with_loader_criteria` predicate
to every SELECT/UPDATE/DELETE touching a scoped entity — including relationship and eager
loads, which is why `asset.chunks` is filtered without anyone remembering to. A
`before_flush` listener stamps `tenant_id`/`user_id` onto inserts, so repositories never
pass a tenant and therefore can't pass the wrong one.

**Layer 2, Postgres Row-Level Security.** Every domain table has a policy keyed on
`current_setting('app.current_tenant')`, set per transaction by an `after_begin` listener.
Four details make it actually work: `FORCE ROW LEVEL SECURITY` so the policy applies to the
table owner too; the ORM connects as a **non-superuser** role (`kb_app`) because superusers
bypass RLS entirely — that's why `APP_DATABASE_URL` is separate from `DATABASE_URL`;
`set_config(..., is_local => true)` makes it transaction-scoped, so a pooled connection
can't carry one request's tenant into the next; and an unset GUC makes the predicate NULL,
which returns zero rows.

**Why two layers?** The ORM filter only covers ORM statements. Raw SQL, a CTE,
`session.get()`, or a future bug slips past it. RLS catches those in the database. That's
also why the hybrid-retrieval query is built from ORM `select()` constructs rather than raw
SQL — raw SQL would silently escape layer 1.

**Convincing you nothing is missed:** the only authorised bypass is `system_scope()`, so
the audit is `grep -rn "system_scope" apps/api/src/` — a handful of hits, all in the auth
service where you *must* read `tenants`/`users` before a tenant exists (registration,
login, refresh, `/auth/me`). Those three tables are deliberately not `TenantScoped`; they
are the root of the tenant chain. Object storage is covered too: keys are
`{tenant_id}/{asset_id}/{filename}`, and presigned URLs are only minted after a
tenant-filtered repository read has already succeeded — another tenant's asset ID 404s
before it reaches the signing call.

**Weak points I'd name.** RLS is dormant if `APP_DATABASE_URL` is unset — a
misconfiguration silently drops you to one layer. I'd add a startup assertion that the
connected role is not a superuser in production. Second, the isolation is enforced but not
*tested*: there's no test that logs in as tenant A and asserts a 404 on tenant B's asset.
That's the first test I'd write, because two-layer defence is only real if it's regression-
protected.

---

### Q3. "Why did you build your own hybrid retrieval with Reciprocal Rank Fusion instead of just doing a vector search?"

**Model answer.**

Because dense retrieval fails predictably on the queries users actually care about.
Embeddings compress meaning, and in doing so they blur exactly the tokens that carry no
semantic content but total precision: error codes, config keys, version numbers, rare
proper nouns. A chunk can contain the literal string `ERR_CONN_REFUSED` and never be
retrieved for the query "ERR_CONN_REFUSED", because that token contributes almost nothing
to the vector. Conversely, keyword search alone misses everything phrased differently from
the source.

So retrieval runs two arms over the same chunks. The dense arm orders by cosine distance
over the pgvector HNSW index. The lexical arm filters on a `tsvector` column — maintained
by Postgres as a `GENERATED ALWAYS ... STORED` column, so ingestion never writes it — and
ranks by `ts_rank_cd`, using `websearch_to_tsquery` because it understands quoted phrases
and never raises on punctuation a user types.

**Fusing them is the interesting part.** Cosine similarity is bounded 0–1; `ts_rank_cd` is
unbounded and corpus-dependent. Normalising them to a common scale means inventing a
mapping that's arbitrary and drifts as the corpus grows. RRF sidesteps that entirely by
discarding the scores and keeping only ranks: `score = Σ weight / (k + rank)`. Two
properties earn it its place: an item found by *both* arms outranks one found brilliantly
by only one — which is exactly the judgement you want when a chunk is both semantically
close and contains the literal term — and the `k` constant damps the head of each list, so
one confidently-wrong arm can't drag its top hit to the top. `k = 60` is the value from
Cormack et al., SIGIR 2009.

**Two implementation details I'd highlight.** First, both arms over-fetch — `top_k × 6` =
30 candidates each — for two reasons: fusion can only promote a chunk ranked 12th by one
arm and 3rd by the other if it's *visible*, and the score threshold then filters a pool
rather than an already-truncated list, so a weak fifth match gets replaced instead of
leaving a hole. There's a comment noting that 30 must stay under pgvector's default
`hnsw.ef_search` of 40, since asking for more results than the beam width silently degrades
recall. Second, both arms return the identical tuple shape *including the cosine score*, so
the threshold, the prompt's score label, and the UI's relevance percentage behave the same
regardless of which arm surfaced a chunk.

**And the honesty check:** the retriever logs `lexical_only_promoted` — how many winners
the lexical arm contributed that dense hadn't already found. If that's persistently zero,
the second arm is earning nothing and should be removed. Instrumenting a heuristic so it
can be *disproven* is the part I'd defend hardest.

**What I'd add next:** a cross-encoder reranker over the fused top-30, which typically
gives the largest single quality jump in a RAG pipeline; and semantic (or at least
heading-aware) chunking, since fixed 800-token windows cut mid-argument.

---

### Q4. "Explain `async def` versus `def` in FastAPI. Where does this codebase get it right, and where does it get it wrong?"

**Model answer.**

FastAPI inspects each route function at import time. An `async def` route is awaited
directly on the event loop. A plain `def` route is handed to `anyio.to_thread.run_sync`
and runs in a threadpool worker — 40 threads by default.

The consequence is asymmetric. Blocking inside a `def` route is *safe*: it occupies one of
40 threads and the loop keeps serving everyone else. Blocking inside an `async def` route
is *catastrophic*: it stalls the single event loop thread, so every concurrent request in
that process — including health checks — freezes for the duration.

**This codebase is sync-first, and correctly so.** It uses sync SQLAlchemy sessions, sync
boto3, and sync LangChain clients, so every one of its 27 routes is `def` and runs in the
threadpool. That's the right pairing: mixing an async framework with sync drivers is fine
as long as the sync work stays off the loop, and `def` guarantees that automatically.

**Where it got that wrong, and how it was fixed** — this is the part worth telling as a
story rather than a rule. `upload_document` used to be the one `async def` route. It had to
be, to `await file.read()`. But right after that await it called `enqueue_ingestion`, which
is fully synchronous: an S3 PUT of the whole body, five Postgres commits, and a fresh
blocking database connection for the queue's `.defer()` — all on the event loop.

The subtlety worth volunteering: **`await file.read()` was never the problem.** That call
offloads correctly. The bug was the unawaited synchronous call *after* it — which is a much
easier mistake to make, because the `async def` looks justified by the await above it.

The fix was to make the handler plain `def` and read the spooled file directly with
`file.file.read()`, so FastAPI dispatches the whole thing to the threadpool. Chosen over
`await run_in_threadpool(enqueue_ingestion, ...)` because it matches the other 26 routes and
costs one threadpool dispatch instead of two. Measured with a 2-second stub and `/health`
probed 150 ms in: **2.17s blocked before, 0.18s after.** A test now walks the mounted routes
and fails if any handler becomes a coroutine again — because a blocking `async def` handler
returns a perfectly correct response and only starves its neighbours, so no functional test
would ever catch it.

**Where it gets it very right, in a way most codebases miss:** the middleware is written as
raw ASGI callables rather than `BaseHTTPMiddleware`. That's not style — it's load-bearing.
`BaseHTTPMiddleware` runs the downstream app in a separate anyio task, which means a
separate context copy, which means a `ContextVar` set in the middleware doesn't reliably
reach the endpoint. Since the entire tenant isolation system reads its tenant from a
contextvar inside SQLAlchemy session listeners, using `BaseHTTPMiddleware` would silently
break isolation — the filter would fail closed and every scoped query would raise. Pure
ASGI keeps one continuous context chain from middleware through the endpoint into the
threadpool worker.

**And the related detail I'd volunteer:** the streaming chat endpoint deliberately does
*not* take `Depends(get_db)`. Since FastAPI 0.106, a yield-dependency's teardown runs before
the streaming body is consumed, so the session would be closed out from under the
generator. It opens its own `session_scope()` inside the generator instead — the same
pattern the worker uses.

**The capacity arithmetic worth knowing:** 40 threadpool threads against SQLAlchemy's
default 15 connections (`pool_size=5` + `max_overflow=10`) means the connection pool, not
the threadpool, is the real ceiling. That's the number I'd tune first.

---

### Q5. "You chose Procrastinate — a Postgres-backed queue — over Celery. Defend that, and tell me when it breaks."

**Model answer.**

The decisive fact is the deployment target: a single shared VPS running several apps behind
one Caddy, with one shared Postgres and one shared Redis. In that environment, every
additional stateful service is a real, recurring cost — to monitor, back up, secure, and
reason about during an incident. Procrastinate's broker *is* the Postgres we already run,
so the queue added zero new infrastructure.

Beyond "one less service", three concrete wins:

**One backup covers data and queue.** With Celery on Redis, a Redis flush loses every
pending job while your data survives — the two can disagree about what happened. With
Procrastinate they're the same durable store and can't diverge.

**Transactional enqueue is possible.** This is the big one architecturally. Because the
queue table is in the same database, `INSERT INTO knowledge_assets` and `INSERT INTO
procrastinate_jobs` *can* be a single atomic commit. With Redis or RabbitMQ you have the
classic dual-write problem and need the Transactional Outbox pattern to solve it properly.

**Debugging is `psql`.** "Why didn't this job run?" is a `SELECT`, not an excavation
through Redis keys or a Flower dashboard.

**The mechanism is sound, not a toy.** Enqueue is an INSERT plus `NOTIFY`; the worker sits
in `LISTEN` and dequeues with `SELECT ... FOR UPDATE SKIP LOCKED` — the standard Postgres
queue idiom, which is exactly what lets N workers pull disjoint jobs with no distributed
lock and no coordination.

**Where I'd be honest about the current implementation:** it doesn't yet *take* the
transactional-enqueue win. Each repository commits independently, so the asset and job rows
are committed before the defer. If the process died in that gap you'd get an asset stuck in
`queued` with no queue row. It's visible in the `/jobs` dashboard and recoverable via the
retry endpoint, but the clean fix is to make the whole enqueue one transaction — which the
choice of Procrastinate *enables* and Celery would not.

**When it breaks.** Postgres-as-a-queue tops out somewhere in the thousands of jobs per
second, and well before that the queue's polling and row churn start contending with
application queries for the same connections and I/O, and generating autovacuum pressure on
a hot table. If jobs became high-frequency and short-lived — a per-request event stream
rather than a per-upload pipeline — I'd move to a dedicated broker. Here, jobs are
per-document-upload and take seconds to minutes, so we're several orders of magnitude from
that ceiling.

**And the migration is cheap by design.** The rest of the codebase depends only on the
`IJobQueue` port — `enqueue_ingestion(asset_id, tenant_id, user_id)`. Swapping engines means
replacing `app.py`, `tasks.py`, and `procrastinate_queue.py`. You can verify nothing else
knows: `grep -r "procrastinate" apps/api/src/domain/ apps/api/src/application/` returns
nothing.

**What I'd genuinely reconsider:** if the pipeline grew into a long-running, multi-step
workflow with compensation — human approval steps, partial rollbacks, day-long processes —
Temporal becomes the right tool, because that's a workflow problem, not a queue problem.
Today the "workflow" is four steps whose resumability is fully captured by one column,
`failed_step`. Adopting Temporal for that would be paying a large operational and
conceptual tax for a problem a string already solves.

---

## 4.5 Rapid-fire prep

**Things to be able to say in one sentence each:**

- *Why `202 Accepted` and not `201 Created`?* — the resource exists but the work isn't
  done; `202` is the honest code for "accepted for processing."
- *Why store `tenant_id` on `chunks` when it's reachable by join?* — so the security
  predicate needs no join.
- *Why is `users.email` globally unique instead of unique per tenant?* — so a login can
  present an email alone and resolve both user and tenant with no tenant selector in the UI.
- *Why hash refresh tokens with SHA-256 but passwords with Argon2id?* — refresh tokens are
  high-entropy random strings, so there's nothing to brute-force; passwords are
  low-entropy and need a deliberately slow, memory-hard hash.
- *Why does the conversation title come from the question instead of the LLM?* — a second
  round-trip before the user sees any answer is the wrong place to spend a second, and the
  first question is almost always the best label; they can rename it.
- *Why are citations stored denormalised as JSONB?* — so a year-old answer re-reads
  correctly even if the source was re-ingested or deleted, and so "which answers cited
  this?" is an indexed containment query rather than a re-run of retrieval.
- *Why is `chunks.fts` a generated column?* — Postgres maintains it, so ingestion code
  needs no change and the migration backfills every existing row for free.
- *Why `X-Accel-Buffering: no` on the SSE response?* — Caddy doesn't buffer by default, but
  an nginx in front would, and a buffered stream defeats the entire point.
- *Why does the frontend delete both messages on a stream failure?* — because the server
  persisted neither, so the UI's rollback and the server's truth agree exactly.
- *Why one Docker image for API and worker?* — they cannot drift; only the command differs.

**The five things this codebase does unusually well:**

1. Two-layer tenant isolation from one contextvar source of truth, failing closed at both
   layers.
2. A single composition root shared verbatim by the HTTP and worker paths.
3. Resumable pipeline retries via a persisted `failed_step`, plus a queryable, user-facing
   event log.
4. Rank-fusion hybrid retrieval, instrumented with a metric designed to disprove its own
   value.
5. Comments that record *why* — including reversed decisions (Docling → PyMuPDF4LLM) and
   fixed bugs (the untrained IVFFlat index, the baked-in absolute API URL).

**The five things to volunteer as "what I'd fix next":**

1. The `upload_document` handler: make it plain `def` so the blocking S3 PUT leaves the event
   loop, then stream uploads straight to S3 (presigned direct PUT) so file bytes never occupy
   the API process at all.
2. One transaction per request (extend the `IUnitOfWork` pattern beyond auth), which also
   makes enqueue atomic.
3. Explicit DB pool sizing, plus PgBouncer in transaction mode — which the
   `is_local => true` GUC already makes safe.
4. Integration tests that actually assert cross-tenant denial, and a startup assertion that
   the app role is not a superuser.
5. A dead-letter path and alerting for jobs that exhaust their retries, plus timeouts and a
   circuit breaker around the AI provider calls.
