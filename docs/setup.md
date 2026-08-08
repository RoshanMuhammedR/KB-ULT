# Setup

Every `pnpm` script below runs on Windows, macOS and Linux. The shell-specific logic lives in
`scripts/run.mjs` (a small Node runner), so nothing depends on `sh`, `cp` or
`.venv/bin/activate` being available.

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Node.js | 20+ | |
| pnpm | 9 | `corepack enable && corepack prepare pnpm@9.15.0 --activate` |
| Python | **3.11+** | the API's `pyproject.toml` sets `requires-python >= 3.11` |
| PostgreSQL | 16+ **with the `pgvector` extension** | the first migration runs `CREATE EXTENSION vector` |
| Valkey or Redis | any recent | optional locally — the cache degrades gracefully if absent |

Installing Python and PostgreSQL+pgvector:

```bash
# macOS
brew install python@3.12 pgvector
brew install postgresql@16 valkey && brew services start postgresql@16

# Debian/Ubuntu  (match the -NN suffix to your server version)
sudo apt install python3.12 python3.12-venv postgresql-16 postgresql-16-pgvector valkey-server

# Windows
winget install --id Python.Python.3.12 --source winget
winget install --id PostgreSQL.PostgreSQL.16      # then build/install pgvector, see below
```

`pgvector` ships no official Windows binary. Build it against your installed server with the
MSVC toolchain (`winget install Microsoft.VisualStudio.2022.BuildTools` with the
"Desktop development with C++" workload), from an **elevated** *x64 Native Tools Command Prompt*:

```bat
set "PGROOT=C:\Program Files\PostgreSQL\18"
git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

The database user in `DATABASE_URL` must be a **superuser**, because `CREATE EXTENSION vector`
requires it. That matches `docker-compose`, where `POSTGRES_USER=kb_user` owns the cluster.

## Running it

```bash
cp .env.example .env       # or: pnpm run setup, which does this for you
# set AICREDITS_API_KEY
# set FILEBASE_ACCESS_KEY, FILEBASE_SECRET_KEY, FILEBASE_BUCKET_NAME
# set JWT_SECRET (long random value) for real environments
pnpm run setup             # installs JS deps, creates .env, builds apps/api/.venv
pnpm run db:migrate        # app tables incl. tenants/users/RLS (alembic)
pnpm run db:queue-schema   # Procrastinate queue tables (one-time, idempotent)
pnpm run db:app-role       # non-superuser role for RLS (only needed if using APP_DATABASE_URL)
pnpm run dev               # api + web + website (does NOT start the worker)
pnpm run worker            # in a second terminal: consumes ingestion jobs
```

`pnpm run setup` picks the newest Python 3.11+ it can find. Override the choice by pointing
`PYTHON` at a specific interpreter:

```bash
PYTHON=/usr/bin/python3.12 pnpm run setup          # macOS / Linux
$env:PYTHON='C:\Python312\python.exe'; pnpm run setup   # Windows PowerShell
```

`psql` is looked up on `PATH`, and on Windows also under
`C:\Program Files\PostgreSQL\<version>\bin`, so the `db:*` scripts work without editing `PATH`.

**Multi-tenancy & auth.** The API is multi-tenant, and accounts are ordinary **email +
password**. `POST /auth/register` creates a workspace (tenant) and its owner user in one
atomic step and returns a signed-in session; `POST /auth/login` takes an email and a password
— `users.email` is globally unique, so the tenant is resolved from the user. Every other
request sends `Authorization: Bearer <access_token>`. There is no fallback identity: a
request without a valid token gets a `401`.

Row isolation is enforced by an ORM tenant-filter and, when `APP_DATABASE_URL` points at the
non-superuser `kb_app` role, by Postgres RLS as well. A **Valkey** cache runs in
`docker-compose`, but no code path uses it today — the port and adapter are kept for the next
feature that needs one.

Ingestion is asynchronous: `POST /documents/upload` stores the file, enqueues a
job, and returns `202` with a `queued` asset. The **worker** (`pnpm run worker`)
runs the extract → chunk → embed pipeline; the frontend polls
`GET /documents/{id}` until the asset is `ready` or `failed`. Under Docker the
worker runs as its own `worker` service (`docker compose up`).

Local development does not start Docker. It expects PostgreSQL with pgvector to
already be available at the configured `DATABASE_URL`; the default points to
`postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_new`.

Open:

- Product app: http://localhost:3000/app — sign up at `/app/register`
- Website (marketing): http://localhost:3001
- API health: http://localhost:8000/health

The product app is served under the `/app` base path even in dev, so it matches production,
where Caddy routes `/app/*` to it and `/*` to the marketing site on a single port.

Useful commands:

```bash
pnpm run db:migrate
pnpm run db:sql
pnpm run db:reset          # drops the public schema, then re-runs migrate/queue/app-role
pnpm run build
pnpm run lint
```

There is no seed step: each workspace's default knowledge base is created lazily on first
use, so a fresh database only needs migrating.

Docker is available only through explicit commands:

```bash
pnpm run docker:build
pnpm run docker:dev
pnpm run docker:db:migrate
pnpm run docker:db:queue-schema
pnpm run docker:db:sql
```

For deploying to a server, see [deployment.md](deployment.md).

The Docker scripts use `scripts/compose.mjs`, which prefers `docker compose` and
falls back to `docker-compose`.
