# AI Knowledge Base PDF MVP

**🔗 Live: [https://saga.dedyn.io](https://saga.dedyn.io)** — [sign up](https://saga.dedyn.io/app/register) · [log in](https://saga.dedyn.io/app/login) · [API health](https://saga.dedyn.io/api/health)

Backend-first RAG MVP for uploading PDFs, ingesting them into PostgreSQL/pgvector, and chatting with citation-backed answers through AICredits.

## Run Locally

Needs Node 20+, pnpm 9, **Python 3.11+**, and PostgreSQL with the **pgvector** extension.
Start PostgreSQL locally and make sure `.env` points at it through `DATABASE_URL` or the
default localhost settings. See [docs/setup.md](docs/setup.md) for per-OS install steps
(including building pgvector on Windows, which has no official binary).

```bash
cp .env.example .env
# edit .env and set AICREDITS_API_KEY
# edit .env and set FILEBASE_* values
pnpm run setup
pnpm run db:migrate
pnpm run db:queue-schema
pnpm run dev
pnpm run worker   # second terminal: consumes ingestion jobs
```

Sign up at http://localhost:3000/app/register (the product app is served under `/app`), browse
the marketing site at http://localhost:3001, and check the API at http://localhost:8000/health.

Accounts are ordinary email + password. Registration creates a workspace and its owner user in
one step and signs you straight in.

All scripts run on Windows, macOS and Linux — the shell-specific bits live in
`scripts/run.mjs`, so no `sh`, `cp` or `.venv/bin/activate` is assumed.

## Commands

```bash
pnpm run setup      # install JS deps, copy .env if missing, install API Python deps
pnpm run dev        # run local API + web; expects local PostgreSQL/pgvector
pnpm run db:migrate # run Alembic migrations against configured DATABASE_URL
pnpm run db:reset   # drop and rebuild the schema from scratch
pnpm run db:sql     # open local psql using .env database settings
pnpm run lint       # run workspace lint tasks
pnpm run test       # run workspace tests
```

Docker is opt-in:

```bash
pnpm run docker:build
pnpm run docker:dev
pnpm run docker:db:migrate
pnpm run docker:db:sql
```

Deploying to a server is documented in [docs/deployment.md](docs/deployment.md): a push to
`main` builds images to GHCR and rolls them onto the VPS behind a health gate.

The Docker scripts call `scripts/compose.mjs`, which uses `docker compose` when
the plugin exists and falls back to `docker-compose` on machines with the
legacy binary.

## MVP Scope

Built now:

- Email + password authentication (register, login, rotating refresh tokens)
- Multi-tenancy enforced by an ORM tenant filter **and** Postgres row-level security
- Asynchronous ingestion: a Procrastinate queue and a worker with retry accounting
- PDF upload and Docling Markdown extraction
- YouTube transcripts as a second source type
- Filebase S3-compatible object storage for uploaded PDFs
- Token-aware chunking
- AICredits/OpenAI-compatible embeddings
- pgvector storage and retrieval
- AICredits/OpenAI-compatible chat
- Citation-backed answers
- Push-to-deploy CI/CD onto a VPS behind a health gate

Not built yet:

- Email verification and password reset (`users.email_verified_at` is reserved for it)
- More than one user per workspace (the schema allows it; nothing creates them)
- Conversation persistence
- Hybrid search, reranking, semantic chunking, alternate vector stores
