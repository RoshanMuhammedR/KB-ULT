# Deployment

Production runs entirely on free tiers and serves **https://saga.dedyn.io**. A push to `main`
deploys everything that changed.

```
                     saga.dedyn.io   (deSEC DNS: A -> 76.76.21.21, Vercel)
                            │
                ┌───────────▼────────────┐
                │ Vercel: saga-kb-site   │  apps/website, serves /
                │  rewrites (beforeFiles)│
                │   /app/* ──────────────┼──► Vercel: saga-kb-web  (apps/web, basePath /app)
                │   /api/* ──────────────┼──► Render: saga-api     (prefix stripped)
                └────────────────────────┘
                                              Render saga-api (Docker, free, Singapore)
                                              uvicorn + Procrastinate worker in one process
                                                   │
                       ┌───────────────────────────┼───────────────────────┐
              Supabase "saga" (Postgres 17,     Filebase S3          AICredits / Langfuse
              pgvector, ap-southeast-1)         (browser PUTs
              session pooler :5432               directly via
                                                 signed URLs)
```

| Piece | Where | Config lives in |
|---|---|---|
| Marketing site + routing | Vercel project `saga-kb-site` (root `apps/website`), owns `saga.dedyn.io` | `apps/website/next.config.ts`; env `WEB_ORIGIN`, `API_ORIGIN` |
| Product app | Vercel project `saga-kb-web` (root `apps/web`) | `apps/web/next.config.ts`; env `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| API + ingestion worker | Render web service `saga-api` | [`render.yaml`](../render.yaml) (Blueprint) |
| Database | Supabase project `saga` (`aoamxnkmjmzrachewpqa`) | migrations in `apps/api/alembic` |
| Keep-alive | GitHub Actions | `.github/workflows/keepalive.yml` |

The browser only ever talks to `saga.dedyn.io`, so there is no CORS in production, and
Google sign-in's authorized origin is unchanged. File uploads go from the browser straight to
Filebase on a signed URL, so large files never pass through Vercel's proxy or the API.

## How the API boots

`apps/api/docker-entrypoint.sh`, with `RUN_MIGRATIONS=1`:

1. `alembic upgrade head`, as `DATABASE_URL`'s role (Supabase's `postgres`).
2. `procrastinate schema --apply`.
3. `scripts/ensure_app_role.py` creates or updates the non-superuser `kb_app` role with
   `APP_DB_PASSWORD`, grants it DML, and revokes Supabase's Data API roles (`anon`,
   `authenticated`) from the app's tables. Supabase's `postgres` has `BYPASSRLS`, so the ORM
   must not use it.
4. uvicorn starts. The ORM connects as `kb_app`: `Settings.orm_database_url` swaps the
   credentials into `DATABASE_URL` and keeps the pooler's `.<project-ref>` username suffix.
   `REQUIRE_RLS=1` refuses to boot if that role could bypass RLS. With
   `RUN_WORKER_IN_PROCESS=1`, the Procrastinate worker runs on the same event loop.

Render generates `APP_DB_PASSWORD` and `JWT_SECRET` (`generateValue` in `render.yaml`), so
nobody needs to know them.

## First-time setup

Done already: the Supabase project (with `vector` in `public`), both Vercel projects with
their env vars, root directories and Git link, and `saga.dedyn.io` attached (verified) to
`saga-kb-site`.

Left to do, in this order. These steps involve secrets or third-party dashboards:

1. **Supabase database password and URL.** *Supabase → project `saga` → Database → Settings →
   Reset database password* (generate one). Then *Connect → Session pooler*, copy the URI,
   and change its scheme from `postgresql://` to `postgresql+psycopg://`. That's `DATABASE_URL`.
2. **Render Blueprint.** *Render dashboard → New → Blueprint → `RoshanMuhammedR/KB-ULT`*. It
   reads `render.yaml` and asks for the values below, then click **Apply**:
   - `DATABASE_URL`: from step 1
   - `AICREDITS_API_KEY`
   - `FILEBASE_ACCESS_KEY`, `FILEBASE_SECRET_KEY`, `FILEBASE_BUCKET_NAME`

   The first build takes a few minutes. It's healthy when
   `https://saga-api.onrender.com/health` returns `{"status":"ok"}`.
3. **Check on the Vercel URL.** Open `https://saga-kb-site-roshanmuhammedrs-projects.vercel.app`,
   then `/app/register`, create an account, upload a small PDF and ask a question.
4. **Switch DNS: the one click.** In deSEC, change `saga.dedyn.io`'s `A` record from
   `37.187.140.45` to `76.76.21.21`. There's no `AAAA` or `CAA` record to clean up. The TTL is
   3600s, so allow up to an hour. Vercel issues the certificate once DNS reaches it. Make sure
   nothing on the VPS (a dynDNS updater) rewrites the record.
5. **Retire the VPS stack** once the domain serves from Vercel:
   `cd /opt/stack/kb && docker compose down`. The VPS deploy workflow and `deploy/` are
   already gone from the repo.

Optional: tracing. Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` to the
Render service. Empty means tracing is off.

## Day to day

- **Deploys.** Push to `main`. Vercel rebuilds both Next apps. Render rebuilds the API only
  when `apps/api/**` or `render.yaml` changed (`buildFilter`). Migrations run on boot.
- **Logs.** Render dashboard → `saga-api` → Logs (API and worker together). Vercel →
  project → Deployments for the Next apps.
- **SQL.** Supabase → SQL editor, or `psql` with the session-pooler URI.
- **Secrets.** Change them in Render → `saga-api` → Environment. Changing `APP_DB_PASSWORD`
  is safe because the next boot re-syncs the role.

## Free-tier behaviour

| Service | Limit | What it means here |
|---|---|---|
| Render free | 512 MB RAM, 0.1 CPU, sleeps after 15 min idle, 750 instance-hours/month per workspace (shared with your other free services) | The first request after a quiet spell takes **30–60s**. Queued ingestion jobs wait in Postgres and run when it wakes. Very large PDFs can hit the memory cap. |
| Supabase free | 500 MB database, pauses after 7 days idle | `keepalive.yml` wakes the API every 3 days, and its boot touches the database. GitHub disables scheduled workflows after 60 days with no commits; re-enable it in the Actions tab. If the project does pause, click *Restore* in Supabase (data is kept). |
| Vercel Hobby | Non-commercial use | Fine for a personal project. |

Deployment Protection on both Vercel projects is set to **previews only**. The account
default (`all_except_custom_domains`) would put a Vercel login in front of
`saga-kb-web-…vercel.app`, and the site's `/app` rewrite would then receive a login page
instead of the app.
