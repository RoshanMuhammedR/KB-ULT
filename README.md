# AI Knowledge Base PDF MVP

Backend-first RAG MVP for uploading PDFs, ingesting them into PostgreSQL/pgvector, and chatting with citation-backed answers through AICredits.

## Run Locally

Start PostgreSQL with pgvector locally and make sure `.env` points at it through
`DATABASE_URL` or the default localhost settings.

```bash
cp .env.example .env
# edit .env and set AICREDITS_API_KEY
# edit .env and set FILEBASE_* values
pnpm run setup
pnpm run db:migrate
pnpm run db:seed
pnpm run dev
```

Open the web app at http://localhost:3000 and the API health check at http://localhost:8000/health.

## Commands

```bash
pnpm run setup      # install JS deps, copy .env if missing, install API Python deps
pnpm run dev        # run local API + web; expects local PostgreSQL/pgvector
pnpm run db:migrate # run Alembic migrations against configured DATABASE_URL
pnpm run db:seed    # create the default KnowledgeBase
pnpm run db:sql     # open local psql using .env database settings
pnpm run lint       # run workspace lint tasks
pnpm run test       # run workspace tests
```

Docker is opt-in:

```bash
pnpm run docker:build
pnpm run docker:dev
pnpm run docker:db:migrate
pnpm run docker:db:seed
pnpm run docker:db:sql
```

The Docker scripts call `infra/compose.sh`, which uses `docker compose` when
the plugin exists and falls back to `docker-compose` on machines with the
legacy binary.

## MVP Scope

Built now:

- PDF upload and Docling Markdown extraction
- Filebase S3-compatible object storage for uploaded PDFs
- Token-aware chunking
- AICredits/OpenAI-compatible embeddings
- pgvector storage and retrieval
- AICredits/OpenAI-compatible chat
- Citation-backed answers

Documented only:

- Background jobs
- Authentication and multi-tenancy enforcement
- Conversation persistence
- Additional sources
- Hybrid search, reranking, semantic chunking, alternate vector stores
