# Setup

```bash
cp .env.example .env
# set AICREDITS_API_KEY
# set FILEBASE_ACCESS_KEY, FILEBASE_SECRET_KEY, FILEBASE_BUCKET_NAME
# set JWT_SECRET (long random value) for real environments
pnpm run setup
pnpm run db:migrate        # app tables incl. tenants/users/RLS (alembic)
pnpm run db:queue-schema   # Procrastinate queue tables (one-time, idempotent)
pnpm run db:app-role       # non-superuser role for RLS (only needed if using APP_DATABASE_URL)
pnpm run db:seed
pnpm run dev               # api + web (does NOT start the worker)
pnpm run worker            # in a second terminal: consumes ingestion jobs
```

**Multi-tenancy & auth.** The API is multi-tenant. Clients authenticate via
`POST /auth/register` (creates a tenant + its user) and `POST /auth/login` (resolves the
tenant by `domain`), then send `Authorization: Bearer <access_token>`. Row isolation is
enforced by an ORM tenant-filter and, when `APP_DATABASE_URL` points at the non-superuser
`kb_app` role, by Postgres RLS as well. Set `TENANCY_DEFAULT_FALLBACK=true` (default) to let
requests without a token fall back to a seeded default tenant during rollout; set it `false`
once clients authenticate. A **Valkey** cache is required by `docker-compose` (`cache`
service); locally it degrades gracefully if absent (`CACHE_URL`).

Ingestion is asynchronous: `POST /documents/upload` stores the file, enqueues a
job, and returns `202` with a `queued` asset. The **worker** (`pnpm run worker`)
runs the extract → chunk → embed pipeline; the frontend polls
`GET /documents/{id}` until the asset is `ready` or `failed`. Under Docker the
worker runs as its own `worker` service (`docker compose up`).

Local development does not start Docker. It expects PostgreSQL with pgvector to
already be available at the configured `DATABASE_URL`; the default points to
`postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_new`.

Open:

- Web: http://localhost:3000
- API health: http://localhost:8000/health

Useful commands:

```bash
pnpm run db:migrate
pnpm run db:seed
pnpm run db:sql
pnpm run build
pnpm run lint
```

Docker is available only through explicit commands:

```bash
pnpm run docker:build
pnpm run docker:dev
pnpm run docker:db:migrate
pnpm run docker:db:queue-schema
pnpm run docker:db:seed
pnpm run docker:db:sql
```

The Docker scripts use `infra/compose.sh`, which prefers `docker compose` and
falls back to `docker-compose`.
