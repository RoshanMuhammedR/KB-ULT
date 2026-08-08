# Deployment

Push to `main` → GitHub Actions builds three images to GHCR, rsyncs `deploy/` to the VPS, and
rolls the stack forward behind a health gate (rolling back automatically if the API never
becomes healthy). [VPS-PLAYBOOK.md](../VPS-PLAYBOOK.md) explains *why* the box is shaped this
way; this page is what is specific to this project.

## Topology

AIC's shared proxy terminates TLS and forwards plain HTTP to **one** port, so the stack
publishes exactly one: Caddy, which routes by path.

```
https://<domain>  →  AIC proxy  →  10.10.10.91:<APP_PORT>  →  caddy:80
                                                                │
                          /api/*  (prefix stripped)  ───────────┼──→  api:8000      FastAPI
                          /app/*  (prefix kept)      ───────────┼──→  web:3000      product
                          /*                         ───────────┴──→  website:3000  marketing
```

`/api/*` is stripped by `handle_path`, so FastAPI's routes stay unprefixed. `/app/*` is *not*
stripped, because the product app sets `basePath: "/app"` and expects to see it. Everything
else — `postgres`, `api`, `worker`, `web`, `website` — sits on the internal network with no
published ports.

One consequence worth noting: the browser talks to the API same-origin, so CORS is never
exercised in production and `NEXT_PUBLIC_API_URL` is baked as the relative `/api`.

## Images

| Image | Dockerfile | Build context | Serves |
| --- | --- | --- | --- |
| `saga-api` | `apps/api/Dockerfile` | `apps/api` | the `api` **and** `worker` services |
| `saga-web` | `apps/web/Dockerfile` | repo root | product app |
| `saga-website` | `apps/website/Dockerfile` | repo root | marketing site |

The Next images build from the repo root because this is a pnpm workspace and both apps
depend on `packages/ui` via `workspace:*`.

**Migrations run themselves.** `apps/api/docker-entrypoint.sh` runs `alembic upgrade head` and
`procrastinate schema --apply` before starting the server — but only when `RUN_MIGRATIONS=1`,
which is set on the `api` service alone. The worker waits on the api's healthcheck, so the two
can never race the same database.

**`NEXT_PUBLIC_*` is inlined at build time**, not read at runtime. Changing where the apps live
means rebuilding the images with different `--build-arg`s, not editing `.env` on the server.

## First-time setup

These steps cannot be automated from the repo. Follow VPS-PLAYBOOK.md §3 for detail.

1. **Port** — claim a free one from the playbook's registry and record it there.
2. **DNS** — a deSEC `A` record at the zone apex → `37.187.159.43`. No AAAA.
3. **AIC panel** — map `<domain>` → `<APP_PORT>`, then confirm it actually saved:
   `curl -s https://<domain>/ | grep -i "domain parked"` should find **nothing**.
4. **Server directory**:
   ```bash
   ssh -p 20086 deploy@37.187.159.43
   sudo mkdir -p /opt/saga && sudo chown deploy:deploy /opt/saga
   cd /opt/saga
   # copy deploy/.env.example across, then generate the secrets ON THE SERVER:
   sed -i "s|REPLACE_ME|$(openssl rand -hex 32)|g" .env
   chmod 600 .env
   ```
   Set `APP_PORT`, `APP_BASE_URL`, `GHCR_OWNER`, and the AICredits/Filebase keys by hand.
5. **Repo secrets** (Settings → Secrets and variables → Actions): `VPS_HOST`, `VPS_USER`,
   `VPS_SSH_KEY`, `VPS_SSH_KNOWN_HOSTS`, plus the variable `VPS_PORT=20086`. No application
   secret goes to GitHub — those live only in `/opt/saga/.env`.
6. **Exec bit** — git on Windows drops it, and CI then dies with exit 126:
   ```bash
   git update-index --chmod=+x deploy/deploy.sh apps/api/docker-entrypoint.sh
   ```

## Operating it

```bash
cd /opt/saga
docker compose ps                  # status and health
docker compose logs -f api
./deploy.sh sha-1a2b3c4            # roll back to any previously built commit
docker stats --no-stream           # memory pressure across all projects on the box
```

`.env` on the server is never overwritten by a deploy — the rsync step excludes it, which is
the only thing standing between a push and wiping the production secrets.

## Verifying a deploy

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/            # 200  marketing
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/app/login   # 200  product
curl -s https://<domain>/api/health                                    # ok
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/documents # 401 (no token)
```

That last one matters: an unauthenticated request to a tenant-scoped route must be a `401`.
