# Architecture

This MVP is a backend-first AI Knowledge Base for uploading PDFs to Filebase object storage, converting them to Docling Markdown-backed `KnowledgeAsset` domain objects, chunking, embedding, storing vectors in PostgreSQL/pgvector, and chatting with citation-backed answers.

Ingestion is **asynchronous**. The upload request only stores the file and enqueues a job; a separate **worker** runs the acquire → parse → chunk → embed pipeline. The queue is Postgres-backed (Procrastinate), so no extra infrastructure is required, and it sits behind the `IJobQueue` port so the engine stays swappable.

Ingestion is also **source-agnostic**. Everything source-specific (how to fetch raw content and how to parse it) lives behind a single `ISourceHandler` port, one per `SourceType`, resolved through a `SourceHandlerRegistry`. **PDF** (uploaded file) and **YouTube** (URL) are implemented; websites are added later as another handler without touching the service, chunker, embedder, or chat. Handlers emit source-neutral **segments** (each with a typed `locator` — a page number for PDF, a transcript timestamp for YouTube), so chunking and citations never special-case a source.

There are two request entry points into ingestion: `enqueue_ingestion` for uploaded files (store bytes, then queue) and `enqueue_url` for URL sources like YouTube (no upload — persist the URL + a `queued` asset with an empty `storage_key`; the worker's handler fetches the content in `acquire`). Both converge on the same worker `process_ingestion` path.

The worker keeps a **persisted event log**: each pipeline transition/terminal state writes an `IngestionJobEvent` row (distinct from stdout structlog output), which the `/jobs` dashboard reads.

## Multi-Tenancy & Auth

The system is **multi-tenant with row-level isolation**. A **tenant** is the isolation boundary, identified by a globally-unique `domain` slug; each tenant has (today) exactly one **user**, enforced by a `UNIQUE(tenant_id)` constraint that can be dropped later with no domain-table migration. Every domain table stores `tenant_id` **and** `user_id`.

Isolation is enforced in **two layers**, both driven from one source of truth — the current tenant, held in a `contextvars` variable (`core/tenant_context.py`):

1. **ORM auto-filter** (the Prisma-extension equivalent, `infrastructure/database/tenancy.py`). A `TenantScoped` mixin marks tenant-owned models; session listeners then (a) append a `with_loader_criteria` tenant filter to every SELECT/UPDATE/DELETE touching a scoped entity, and (b) stamp `tenant_id`/`user_id` onto inserts. It **fails closed**: a scoped query with no tenant in context raises `MissingTenantContextError`. `system_scope()` suspends it for pre-auth/cross-tenant work.
2. **Postgres RLS** (migration `0006`). A per-table policy keyed on `current_setting('app.current_tenant')` is the database backstop for raw SQL, `Session.get()`, and future bugs. The ORM sessions connect as a **non-superuser role** (`kb_app`, `APP_DATABASE_URL`) so RLS actually applies; an `after_begin` listener sets the GUC each transaction. Migrations and the Procrastinate connector keep the superuser role.

**Context propagation.** HTTP uses two pure-ASGI layers with separated responsibilities: an `AuthenticationMiddleware` runs a chain of `Authenticator`s (bearer token today; API keys/OAuth later) that establish *who* is calling and produce a mechanism-agnostic `Identity` (`tenant_id`/`user_id`), and a downstream `TenantContextMiddleware` binds that `Identity` into the contextvars — it neither decodes tokens nor knows how identity was proven. New credential types are added as authenticators without touching tenant binding. Background jobs have no request, so every payload carries `tenant_id`/`user_id` and a shared `@tenant_task` wrapper re-establishes context (and fails loud if absent).

**Auth.** Registration creates a tenant + its user atomically. Login resolves the tenant by `domain`, verifies the (Argon2id) password, and returns a short-lived **access JWT** (`tid`/`sub`, ~15 min) plus a **rotating refresh token** (stored hashed in Postgres; reuse revokes the family). All auth crypto sits behind ports (`IPasswordHasher`, `ITokenService`) in `infrastructure/auth/`.

**Caching.** Valkey is the cache; tenant-scoped keys must be built with `tenant_cache_key` (`tenant:{tenant_id}:…`), which fails closed without a tenant — cross-tenant cache bleed is structurally impossible.

## Backend Structure

```text
apps/api/src/
├── composition.py       # composition root: builds the object graph for HTTP + worker
├── http/
│   ├── routes/          # FastAPI handlers only
│   ├── schemas/         # Pydantic API DTOs
│   └── dependencies/    # thin FastAPI Depends wrappers over composition.py
├── domain/
│   ├── entities/        # KnowledgeBase, KnowledgeAsset, Chunk, IngestionJob, JobEvent, RawContent, SourceType
│   ├── interfaces/      # ISourceHandler, repo, embedder, LLM, vector store, job queue ports
│   └── value_objects/
├── application/
│   ├── ingestion/       # enqueue (request) + process (worker) use cases
│   ├── chat/            # retrieval + prompt + LLM use case
│   └── knowledge_base/  # KB use cases
├── ingestion/
│   ├── source_types.py  # edge resolvers: filename/extension + URL -> SourceType (+ URL identity)
│   ├── registry.py      # SourceHandlerRegistry: SourceType -> handler
│   └── handlers/        # PdfSourceHandler, YouTubeSourceHandler (acquire + parse)
├── processing/
│   └── chunking/        # chunker implementation + strategies
├── retrieval/           # query-time retrieval orchestration
├── infrastructure/
│   ├── database/        # SQLAlchemy models/session (get_db + session_scope)
│   ├── repositories/    # Postgres repositories (incl. ingestion jobs)
│   ├── queue/           # Procrastinate app, task, and IJobQueue adapter
│   ├── vector_store/    # pgvector adapter
│   ├── storage/         # Filebase S3-compatible adapter (upload/download)
│   ├── document_parsing/ # Docling-backed parser adapters
│   ├── langchain_adapters/
│   └── ai_providers/    # AICredits providers
└── core/                # config, logging, exceptions, constants
```

## Flow

Enqueue (fast, in the request):

```mermaid
sequenceDiagram
  participant Web
  participant HTTP
  participant IngestionService
  participant Storage
  participant JobRepo
  participant JobQueue

  Web->>HTTP: POST /documents/upload
  HTTP->>IngestionService: enqueue_ingestion(file bytes, filename)
  IngestionService->>Storage: upload(storage_key, file bytes)
  IngestionService->>JobRepo: create(IngestionJob QUEUED)
  IngestionService->>JobQueue: enqueue_ingestion(asset_id)
  IngestionService-->>HTTP: KnowledgeAsset (queued)
  HTTP-->>Web: 202 Accepted
  Web->>HTTP: GET /documents/{id} (poll until ready/failed)
```

Process (slow, in the worker):

```mermaid
sequenceDiagram
  participant Queue as Procrastinate
  participant Task
  participant IngestionService
  participant Registry
  participant Handler
  participant Chunker
  participant Embedder
  participant VectorStore
  participant JobRepo
  participant EventRepo

  Queue->>Task: ingest_asset(asset_id)
  Task->>IngestionService: process_ingestion(asset_id)
  IngestionService->>JobRepo: mark_running (attempt++)
  IngestionService->>Registry: get(SourceType.PDF)
  IngestionService->>Handler: acquire(asset) [download from storage]
  IngestionService->>Handler: parse(asset, raw) [Docling -> markdown + segments]
  IngestionService->>Chunker: chunk(asset) [segments -> chunks w/ locator]
  IngestionService->>Embedder: embed_texts(chunks)
  IngestionService->>VectorStore: upsert_embeddings(...)
  IngestionService->>JobRepo: mark_succeeded / mark_failed (+re-raise for retry)
  Note over IngestionService,EventRepo: each step also appends an IngestionJobEvent (worker log)
```

```mermaid
sequenceDiagram
  participant Web
  participant HTTP
  participant ChatService
  participant Embedder
  participant Retriever
  participant PromptBuilder
  participant LLM

  Web->>HTTP: POST /chat/ask
  HTTP->>ChatService: ask(question)
  ChatService->>Embedder: embed_query(question)
  ChatService->>Retriever: retrieve(query_embedding)
  ChatService->>PromptBuilder: build(question, results)
  ChatService->>LLM: generate(messages)
  ChatService-->>HTTP: answer + citations
```

## Boundaries

- `http` owns HTTP concerns only.
- `domain` has no FastAPI, SQLAlchemy, LangChain, or Procrastinate imports.
- `application` orchestrates use cases and depends on domain ports (including `IJobQueue` and `ISourceHandler`).
- `composition.py` is the only module that knows every concrete adapter (including which handler serves each `SourceType`); HTTP and the worker both build services through it.
- `ingestion` normalizes raw sources into domain assets: `source_types` resolves the `SourceType`, the registry maps it to an `ISourceHandler`, and each handler owns acquisition + parsing for its source.
- `processing` operates on parsed assets and is source-agnostic (it consumes `segments`/`locator`, never a source-specific field like a page number).
- `retrieval` owns query-time search orchestration.
- `infrastructure` implements external concerns: DB, pgvector, object storage, the Procrastinate queue, LangChain wrappers, and AICredits.

The queue engine is confined to `infrastructure/queue/`. Verify:

```bash
grep -r "procrastinate" apps/api/src/domain/ apps/api/src/application/
```

LangChain imports are only allowed in:

```text
apps/api/src/infrastructure/langchain_adapters/
```

Verification:

```bash
grep -r "import langchain" apps/api/src/
```

## API

- `GET /health`
- `POST /auth/register` — create a tenant + its user; returns access + refresh tokens
- `POST /auth/login` — resolve tenant by `domain`, verify credentials; returns tokens
- `POST /auth/refresh` — rotate the refresh token; returns new tokens
- `POST /auth/logout` — revoke the refresh-token family
- `GET /documents`
- `GET /documents/{asset_id}` — single asset + latest job (status polling)
- `GET /documents/{asset_id}/events` — persisted worker-log trail for the asset
- `POST /documents/upload` — enqueues an uploaded file; returns `202` with a `queued` asset
- `POST /documents/ingest-url` — enqueues a URL source (YouTube); returns `202` with a `queued` asset
- `POST /documents/{asset_id}/retry` — re-enqueues a failed asset (`202`)
- `PATCH /documents/{asset_id}`
- `DELETE /documents/{asset_id}`
- `GET /jobs` — recent ingestion jobs for the worker-activity dashboard
- `GET /knowledge-bases/default`
- `POST /chat/ask`

## Data Model

- `Tenant`: the isolation boundary — globally-unique `domain`, `status` (active/suspended/deleted).
- `User`: a tenant's user — `(tenant_id, email)` unique, one-per-tenant via `UNIQUE(tenant_id)`, `status` (active/suspended/deleted/invited), Argon2id `password_hash`.
- `RefreshToken`: durable, revocable refresh-token record (hash + `family_id`); rotation-based revocation.
- Every domain table below also carries `tenant_id` + `user_id` (`TenantScoped`).
- `KnowledgeBase`: default container, with nullable `owner_id` (legacy, superseded by `tenant_id`/`user_id`).
- `KnowledgeAsset`: immutable source version with `lineage_id`, `version`, status (now including `queued`), failure step, metadata, and supersession state. Tracks the **pipeline stage**.
- `IngestionJob`: the unit of work and its **retry accounting** (status, attempts, `max_attempts`, `last_error`, timings) for one asset. Domain-owned and queue-engine-agnostic; distinct from Procrastinate's internal tables.
- `IngestionJobEvent`: append-only **worker log** — one row per pipeline transition/terminal state (event name, level, message, `data`, timestamp), keyed by asset (and job when known). The durable, queryable counterpart to stdout logs; powers the `/jobs` dashboard.
- `Chunk`: text fragment tied to a specific asset version, carrying a source-neutral `locator` (e.g. `{"type": "page", "value": 3}`) in its metadata.
- `Embedding`: vector tied to a chunk, with model, dimensions, and created timestamp.
