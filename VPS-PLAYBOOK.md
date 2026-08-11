# VPS Deployment Playbook

How to put any project on the AIC Cloud VPS with its own domain, HTTPS, and push-to-deploy CI/CD.

This is written to be reused. Sniplink is the worked example, but nothing here is specific to it — substitute your project name, port, and domain throughout. Placeholders look like `<project>`, `<PORT>`, `<domain>`.

---

## 0. Read this first — what this VPS actually is

Several obvious approaches **do not work here**, and the reasons are structural rather than fixable.

| Property | Value | What it means for you |
|---|---|---|
| Virtualisation | **LXC container** (not a VM) | No swap files, no custom kernel modules, some `sysctl` writes fail |
| Network | **NAT'd**, private IP `10.10.10.91/24` | The VPS has **no public IPv4 of its own** |
| Public IPv4 | `37.187.159.43`, **shared** with other tenants | You cannot bind ports 80 or 443 — AIC's own Caddy owns them |
| Public IPv6 | `2001:41d0:a:5f2b::2416` — real, not NAT'd | Unused, but a genuine fallback if you ever need direct binding |
| SSH | Port **20086** externally → **22** internally | Firewall rules must reference **22**, not 20086 |
| Resources | 2 vCPU, 4 GB RAM, 40 GB disk | Cap container memory or one JVM will crowd out everything |

### The consequence

**You do not run your own TLS terminator.** Do not deploy Caddy, Traefik, or nginx-with-certbot expecting to own :443 — it cannot bind. Instead, AIC's shared proxy terminates TLS and forwards to a plain-HTTP port on your VPS:

```
   client
     │  https://<domain>
     ▼
  AIC Cloud shared proxy        TLS terminated here (their auto-SSL)
     │  http, Host: <domain>
     ▼
  10.10.10.91:<PORT>            published by your container
     │
  your app (plain HTTP, no certs)
```

Your job is to make **one container listen on one port** and register that port with AIC.

---

## 1. Port registry

Every project needs a unique host port. Ports collide silently and painfully — keep this table current.

| Port | Project | Domain |
|---|---|---|
| 3000 | sniplink | sniplink.dedyn.io |
| 3001 | *free* | |
| 3002 | saga | saga.dev |
| 3003 | *free* | |

Before starting, confirm your chosen port is actually free:

```bash
ssh -p 20086 deploy@37.187.159.43 "ss -lnt | grep :<PORT> || echo 'port <PORT> is free'"
```

---

## 2. One-time VPS setup (already done — for reference or rebuild)

Skip this section unless you are rebuilding the box. It is recorded so the setup is reproducible.

```bash
# Base packages
apt-get update && apt-get install -y ca-certificates curl gnupg rsync

# Docker from the official repo (Ubuntu's docker.io has no Compose v2)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Non-root deploy user — CI logs in as this, never root
adduser --disabled-password --gecos '' deploy
usermod -aG sudo,docker deploy
mkdir -p /home/deploy/.ssh && chmod 700 /home/deploy/.ssh
echo "<ci-public-key>" >> /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Unattended security updates
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
  > /etc/apt/apt.conf.d/20auto-upgrades

# GHCR login — once per VPS user, covers every repo under that GitHub account
echo "<pat-with-read:packages>" | docker login ghcr.io -u <github-username> --password-stdin
```

**Shared across all projects**, so you do not repeat them: Docker, the `deploy` user, and the GHCR login.

### Deliberately not done

- **No swap.** `swapon` is not permitted inside LXC. The 512 MB in `free` comes from the host cgroup. Cap container memory instead.
- **No `ufw`.** It would be theatre: NAT already blocks everything except the forwarded SSH port, and **Docker's published ports bypass ufw's INPUT chain entirely**. See §8 for the exposure that is real.

---

## 3. Per-project checklist

### Step 1 — Choose a name and port

```
project:  <project>          e.g. myapp
port:     <PORT>             next free from §1
domain:   <domain>           e.g. myapp.dedyn.io
```

Add your row to the port registry now, before you forget.

### Step 2 — DNS

Using deSEC (free, no ads, DNSSEC signed):

1. Create the zone at [desec.io](https://desec.io) — enter the **full** name, e.g. `myapp.dedyn.io`.
2. Add one record set:

| Field | Value |
|---|---|
| Type | `A` |
| **Subname** | **empty** (the zone apex) |
| IPv4 | `37.187.159.43` |
| TTL | `3600` |

**Do not retype the project name in Subname** — the zone is already `myapp.dedyn.io`, so an empty subname *is* that name. Typing `myapp` yields `myapp.myapp.dedyn.io`.

**Do not add an AAAA record.** The A record must point at AIC's shared IP, not the VPS's IPv6, or their proxy is bypassed.

Or via the API (token from deSEC → Token Management):

```bash
curl -X POST https://desec.io/api/v1/domains/<domain>/rrsets/ \
  -H "Authorization: Token <desec-token>" -H "Content-Type: application/json" \
  -d '{"subname": "", "type": "A", "ttl": 3600, "records": ["37.187.159.43"]}'
```

Verify against an external resolver — your local one may cache a negative answer from before the record existed:

```bash
nslookup <domain> 9.9.9.9
```

Note deSEC's minimum TTL is 3600 s on free accounts, so a wrong value takes an hour to correct. Check before saving.

### Step 3 — Register the domain mapping with AIC

In the AIC Cloud panel: **Domains → Add**, then

```
Domain: <domain>
Port:   <PORT>
```

Their blurb — *"We'll set up a reverse proxy with auto-SSL that routes your domain to the port your app listens on inside the VPS"* — is exactly what you want.

**Confirm it actually saved.** This step failed silently for sniplink and cost real debugging time. Verify:

```bash
curl -s https://<domain>/ | grep -i "domain parked"
```

If that matches, the mapping is **not** active — AIC is still serving its parking page. There is nothing to fix on the VPS; go back to the panel.

### Step 4 — Containerise

One container must listen on a port, speaking **plain HTTP**. No TLS, no certificates.

If your project is a single service, that is all. If it is a SPA plus an API (like sniplink), make the web server the router so only one port is exposed — see §4.4.

### Step 5–7 — Add the deployment files

Copy the templates in §4 into your repo:

```
deploy/docker-compose.yml
deploy/deploy.sh
deploy/.env.example
.github/workflows/ci.yml
.github/workflows/deploy.yml
.gitattributes
```

### Step 8 — Create the server directory

```bash
ssh -p 20086 deploy@37.187.159.43
sudo mkdir -p /opt/<project> && sudo chown deploy:deploy /opt/<project>
```

Two approaches to the `.env` inside it — pick one and know why.

**(a) Hand-written on the server.** Simplest. Generate secrets *on the box* so they never exist in a shell history, a chat log, or a repo:

```bash
cd /opt/<project>
cat > .env <<'EOF'
APP_PORT=<PORT>
APP_BASE_URL=https://<domain>
GHCR_OWNER=<github-username-lowercase>
IMAGE_TAG=latest
POSTGRES_DB=<project>
POSTGRES_USER=<project>
POSTGRES_PASSWORD=REPLACE
EOF
# hex, not base64 — no /, +, = or $ to confuse compose interpolation or a JDBC URL
sed -i "s|REPLACE|$(openssl rand -hex 32)|" .env
chmod 600 .env
```

The catch: that file is then the *only* copy, with no history and no review. Fine for one operator; awkward the moment there are two.

**(b) Rendered from GitHub at deploy time.** GitHub becomes the single source of truth, rotation is a UI change rather than an SSH session, and the server's `.env` is a disposable artifact. This is what saga does — see §4.6.

### Step 9 — GitHub secrets

Per repo, under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `VPS_HOST` | `37.187.159.43` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | private half of the CI keypair (same key works for every project) |
| `VPS_SSH_KNOWN_HOSTS` | `ssh-keyscan -H -p 20086 37.187.159.43` |

And one **variable**:

| Variable | Value |
|---|---|
| `VPS_PORT` | `20086` |

With approach (a) no application secret goes to GitHub. With approach (b) they all do — as **secrets** for credentials and **variables** for everything else, so config stays readable and only real credentials are opaque.

<details>
<summary>Setting them from a script (if <code>gh</code> is not installed)</summary>

```python
# pip install pynacl
import base64, json, urllib.request
from nacl import encoding, public

TOKEN, REPO = "<github-pat>", "<owner>/<repo>"

def req(method, path, body=None):
    r = urllib.request.Request("https://api.github.com" + path,
                               data=json.dumps(body).encode() if body else None, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(r) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)

_, key = req("GET", f"/repos/{REPO}/actions/secrets/public-key")
box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))

for name, value in {
    "VPS_HOST": "37.187.159.43",
    "VPS_USER": "deploy",
    "VPS_SSH_KEY": open("~/.ssh/ci_key").read(),
    "VPS_SSH_KNOWN_HOSTS": open("known_hosts.txt").read(),
}.items():
    st, _ = req("PUT", f"/repos/{REPO}/actions/secrets/{name}", {
        "encrypted_value": base64.b64encode(box.encrypt(value.encode())).decode(),
        "key_id": key["key_id"],
    })
    print(name, st)

req("POST", f"/repos/{REPO}/actions/variables", {"name": "VPS_PORT", "value": "20086"})
```

</details>

### Step 10 — Deploy

Push to `main`. The pipeline builds, pushes to GHCR, rsyncs config, and rolls out behind a health gate.

### Step 11 — Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/          # 200
ssh -p 20086 deploy@37.187.159.43 "cd /opt/<project> && docker compose ps"
```

Then check the client IP actually arriving at your app (see §8) — this is the one thing that cannot be tested before real traffic flows.

---

## 4. Templates

### 4.1 `deploy/docker-compose.yml`

```yaml
name: <project>          # MUST be unique per project — namespaces containers,
                         # networks and volumes so projects cannot collide

services:

  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      # $$ escapes the $ from compose so the container's shell expands it
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    networks: [internal]
    # No published ports — never expose a database to the host

  app:
    image: ghcr.io/${GHCR_OWNER}/<project>:${IMAGE_TAG}
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      APP_BASE_URL: ${APP_BASE_URL}
    # Cap memory or the process sizes itself against the whole 4 GB host
    mem_limit: 1g
    ports:
      # All interfaces: AIC's proxy arrives over the private network, not loopback.
      # Safe because the VPS has no public IPv4 of its own.
      - "${APP_PORT}:8080"
    networks: [internal]

volumes:
  pgdata:

networks:
  internal:
```

Drop the `postgres` service entirely if your project does not need it.

### 4.2 `deploy/deploy.sh`

Generic — set `HEALTH_SERVICE` in `.env` if your health-gated service is not called `app`.

```bash
#!/usr/bin/env bash
# Roll onto a new image tag, gated on health. Restores the previous tag on failure.
#   ./deploy.sh sha-1a2b3c4
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"

HEALTH_TIMEOUT=150
SERVICE="${HEALTH_SERVICE:-app}"

NEW_TAG="${1:-}"
[ -n "$NEW_TAG" ] || { echo "usage: $(basename "$0") <image-tag>" >&2; exit 2; }
[ -f .env ] || { echo "error: no .env in $STACK_DIR" >&2; exit 2; }

PREV_TAG="$(sed -n -E 's/^IMAGE_TAG=(.*)$/\1/p' .env | tail -1)"
PREV_TAG="${PREV_TAG:-latest}"

set_tag() {
	if grep -qE '^IMAGE_TAG=' .env; then
		sed -i -E "s|^IMAGE_TAG=.*|IMAGE_TAG=$1|" .env
	else
		printf 'IMAGE_TAG=%s\n' "$1" >>.env
	fi
}

wait_healthy() {
	local waited=0 cid status
	while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
		cid="$(docker compose ps -q "$SERVICE" || true)"
		if [ -n "$cid" ]; then
			status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)"
			[ "$status" = healthy ] && return 0
			# A service with no HEALTHCHECK reports <no value> — fall back to "running"
			if [ "$status" = "<no value>" ]; then
				[ "$(docker inspect -f '{{.State.Status}}' "$cid")" = running ] && return 0
			fi
		fi
		sleep 5
		waited=$((waited + 5))
		printf '  ... waiting for %s (%ss/%ss)\n' "$SERVICE" "$waited" "$HEALTH_TIMEOUT"
	done
	return 1
}

echo "==> deploying $NEW_TAG (current: $PREV_TAG)"
set_tag "$NEW_TAG"
docker compose pull
docker compose up -d --remove-orphans

if wait_healthy; then
	echo "==> healthy on $NEW_TAG"
	docker image prune -f >/dev/null || true
	docker compose ps
	exit 0
fi

echo "!!! $SERVICE unhealthy after ${HEALTH_TIMEOUT}s — rolling back to $PREV_TAG" >&2
docker compose logs --tail=80 "$SERVICE" >&2 || true
set_tag "$PREV_TAG"
docker compose up -d --remove-orphans >&2 || true
exit 1
```

### 4.3 `.github/workflows/deploy.yml`

```yaml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: deploy-production
  cancel-in-progress: false      # never kill a deploy midway

permissions:
  contents: read
  packages: write

jobs:

  prepare:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.v.outputs.tag }}
      owner: ${{ steps.v.outputs.owner }}
    steps:
      - id: v
        run: |
          echo "tag=sha-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          echo "owner=${GITHUB_REPOSITORY_OWNER,,}" >> "$GITHUB_OUTPUT"   # GHCR needs lowercase

  build:
    needs: prepare
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - service: <project>
            context: .
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}    # built-in, no PAT needed to push
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: |
            ghcr.io/${{ needs.prepare.outputs.owner }}/${{ matrix.service }}:${{ needs.prepare.outputs.tag }}
            ghcr.io/${{ needs.prepare.outputs.owner }}/${{ matrix.service }}:latest
          cache-from: type=gha,scope=${{ matrix.service }}
          cache-to: type=gha,scope=${{ matrix.service }},mode=max

  deploy:
    needs: [prepare, build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up SSH
        env:
          SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
          KNOWN_HOSTS: ${{ secrets.VPS_SSH_KNOWN_HOSTS }}
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_PORT: ${{ vars.VPS_PORT || '22' }}
        run: |
          mkdir -p ~/.ssh && chmod 700 ~/.ssh
          printf '%s\n' "$SSH_KEY" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          if [ -n "$KNOWN_HOSTS" ]; then
            printf '%s\n' "$KNOWN_HOSTS" > ~/.ssh/known_hosts
          else
            ssh-keyscan -H -p "$VPS_PORT" "$VPS_HOST" >> ~/.ssh/known_hosts 2>/dev/null
          fi
          chmod 600 ~/.ssh/known_hosts

      - name: Sync deploy files
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_USER: ${{ secrets.VPS_USER }}
          VPS_PORT: ${{ vars.VPS_PORT || '22' }}
        run: |
          rsync -az --delete --exclude '.env' --exclude 'backups/' \
            -e "ssh -p $VPS_PORT -o StrictHostKeyChecking=yes" \
            deploy/ "$VPS_USER@$VPS_HOST:/opt/<project>/"

      - name: Run deploy script
        env:
          VPS_HOST: ${{ secrets.VPS_HOST }}
          VPS_USER: ${{ secrets.VPS_USER }}
          VPS_PORT: ${{ vars.VPS_PORT || '22' }}
          TAG: ${{ needs.prepare.outputs.tag }}
        run: |
          ssh -p "$VPS_PORT" -o StrictHostKeyChecking=yes "$VPS_USER@$VPS_HOST" \
            "chmod +x /opt/<project>/*.sh && /opt/<project>/deploy.sh '$TAG'"
```

`--exclude '.env'` is load-bearing: it is what stops CI overwriting the server's real secrets.

### 4.4 nginx as router (SPA + API in one port)

If you must expose only one port but have a SPA and a separate API, let the web server route. See [sniplink-ui/nginx.conf](sniplink-ui/nginx.conf) for a full working example. The essentials:

```nginx
# Recover the true client IP. real_ip_recursive walks X-Forwarded-For from the
# RIGHT, skipping trusted addresses — so a client that sends its own header
# cannot choose what your app sees.
set_real_ip_from 10.10.10.0/24;
real_ip_header X-Forwarded-For;
real_ip_recursive on;

upstream api { server api:8080; }

proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;   # overwrite, do not append
proxy_set_header X-Forwarded-Proto https;        # AIC terminated TLS

server {
    listen 80;
    root /usr/share/nginx/html;

    location /api/ { proxy_pass http://api; }
    location / { try_files $uri $uri/ /index.html; }
}
```

### 4.5 `.gitattributes`

```
deploy/*.sh        text eol=lf
**/Dockerfile      text eol=lf
.github/workflows/*.yml text eol=lf
```

### 4.6 Rendering `.env` from GitHub at deploy time

Approach (b) from §3 Step 8. Commit a template with `${PLACEHOLDER}`s and no values:

```bash
# deploy/.env.tmpl
APP_PORT=${APP_PORT}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
JWT_SECRET=${JWT_SECRET}
```

Then render it in CI and pipe it over SSH, after the rsync and before `deploy.sh`:

```yaml
- name: Render .env on the server
  env:
    APP_PORT: ${{ vars.APP_PORT }}                    # non-secret -> variable
    POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}  # credential -> secret
    JWT_SECRET: ${{ secrets.JWT_SECRET }}
  run: |
    set -eu
    # Fail loudly rather than render an empty credential: an empty JWT_SECRET silently
    # signs tokens with "", and an empty POSTGRES_PASSWORD locks the app out of its own DB.
    for required in APP_PORT POSTGRES_PASSWORD JWT_SECRET; do
      eval "value=\${$required:-}"
      [ -n "$value" ] || { echo "::error::missing $required"; exit 1; }
    done
    envsubst < deploy/.env.tmpl > /tmp/rendered.env
    ssh -p "$VPS_PORT" -o StrictHostKeyChecking=yes "$VPS_USER@$VPS_HOST" \
      'umask 077 && cat > /opt/<project>/.env.new && mv /opt/<project>/.env.new /opt/<project>/.env' \
      < /tmp/rendered.env
    rm -f /tmp/rendered.env
```

Five things that make this safe rather than merely clever:

- **Pipe over stdin, never as an argument.** Anything on an `ssh` command line is visible in `ps` on the server for the life of the call.
- **`umask 077` + write-then-`mv`.** The file is never briefly world-readable, and a dropped connection cannot leave a half-written `.env`.
- **Validate before rendering.** `envsubst` happily substitutes an unset variable with an empty string, which is how a deploy silently ends up with a blank signing key.
- **Never `cat` the rendered file in a step.** Actions masks *registered* secrets, but not the new one somebody adds next month.
- **Add `--exclude '.env'` to the rsync anyway.** Belt and braces: it stops a mis-ordered workflow from clobbering the file with nothing.

**`IMAGE_TAG` needs care under this model.** It is deploy *state*, not configuration — but CI regenerates `.env` on every rollout, which would erase the rollback target. Keep the truth in a separate `.image-tag` file that CI never touches and `deploy.sh` owns, and have `deploy.sh` `export IMAGE_TAG`: an exported variable beats the `.env` file in compose interpolation, so the two cannot disagree mid-deploy. Rendering the line into `.env` as well is still worth doing, purely so `docker compose ps` shows the right image to a human in that directory.

**Migrating an existing hand-written `.env` to this model:** copy the *existing* `POSTGRES_PASSWORD` into GitHub rather than generating a fresh one. Postgres reads that variable only when it initialises its data directory, so a new value does not change the database — it just locks the app out. If you do need to rotate it, `ALTER USER` inside the running container first, then update the secret.

---

## 5. Pitfalls that have already cost time

Every one of these was hit for real.

**Shell scripts committed from Windows lose their exec bit.** CI dies with `Permission denied` (exit 126). Fix in the index, not the filesystem:

```bash
git update-index --chmod=+x path/to/script.sh
```

**CRLF line endings break shebangs on Linux** — `bad interpreter`. Use the `.gitattributes` above. Windows has `core.autocrlf=true` by default.

**A container healthcheck hitting `localhost` may fail while the service is fine.** Inside a container `localhost` resolves to `::1` first; if your server binds IPv4 only, every probe gets connection refused and the container sits `unhealthy` while serving traffic normally. **Always probe `127.0.0.1`.** This produced 20,274 consecutive false failures on sniplink.

**Spring Boot's default readiness group is only `readinessState`** — it reports UP with the database down, making any deploy health gate meaningless. Add your datastore explicitly:

```yaml
management.endpoint.health.group.readiness.include: readinessState,db
```

Leave out dependencies your app degrades gracefully without (a cache that fails open), or you will restart-loop a container that is still serving correctly.

**`X-Forwarded-For` is attacker-controlled unless you overwrite it.** If your code reads the *left-most* entry and your proxy *appends*, a client can send its own header and pick its own rate-limit key. Overwrite at the edge, or use nginx's `real_ip` module as in §4.4.

**Postgres reads `POSTGRES_PASSWORD` only when it creates the data directory.** Changing it in `.env` later does nothing, and the app then fails to authenticate. Use `ALTER USER` in psql, or destroy the volume — and the data with it. This bites hardest when moving to CI-rendered secrets (§4.6): generating a "fresh" password there breaks a database that is working perfectly.

**A health gate on one service is not a health gate.** Saga's first deploy went green while Caddy — the only publicly reachable container — was crash-looping on a bad config, because the gate only watched the API. Gate on the published port as the outside world sees it, and reject anything stuck `Restarting`.

**Memory: cap it.** `-XX:MaxRAMPercentage` and similar size against the *host's* 4 GB, not the container, so one JVM will starve Postgres. Set `mem_limit`.

**A slim Python image will be missing shared libraries no `pip install` mentions.** Saga's worker took every PDF as far as table extraction and then died with `ImportError: libxcb.so.1: cannot open shared object file` — `docling` → `rapidocr` → `opencv-python`, whose desktop wheel bundles Qt and links `libGL`/`libxcb`/`libX11`. Nothing in the dependency tree says so, and it only surfaces at the first upload, long after the build and the health gate are both green. `apt-get install libgl1` fixes it and costs ~205 MB of Mesa drivers for a library that never renders anything; prefer the headless wheel:

```dockerfile
RUN PYTHONPATH=/install/lib/python3.12/site-packages pip uninstall -y opencv-python \
  && pip install --prefix=/install --no-deps opencv-python-headless \
  && PYTHONPATH=/install/lib/python3.12/site-packages python -c "import cv2"
```

`--no-deps` stops pip restoring the GUI wheel as `rapidocr`'s dependency; `PYTHONPATH` is what lets pip *find* a `--prefix` install to uninstall. The trailing import is the point: it turns a runtime failure into a build failure. Generalise it — for any package whose real work happens deep in a code path, import it at build time.

```bash
# Find every unresolved shared-library dep in an image before your users do
docker run --rm --entrypoint sh IMAGE -c \
  'find / -name "*.so*" 2>/dev/null | xargs -r -n1 ldd 2>/dev/null | grep "not found" | sort -u'
```

**Torch wants a C++ compiler at inference time.** Immediately behind the OpenCV problem, the same worker failed with `InvalidCxxCompiler: No working C++ compiler found in torch._inductor.config.cpp.cxx: (None, 'g++')`. `torch.compile`'s inductor backend *generates C++ and invokes g++ while serving a request*, so a multi-stage build that correctly leaves compilers out of the runtime stage breaks the moment real work arrives. Set `ENV TORCHDYNAMO_DISABLE=1` — `torch.compile` becomes a no-op and the eager path is fine. Shipping a compiler instead costs ~200 MB and a JIT compile on a 4 GB box for no benefit.

**Both of the above share one shape, and it is the real lesson: a green deploy proves the process starts, not that it works.** Health gates check liveness, and liveness only exercises import-time code. Anything lazy — a model loaded on first use, a compiler invoked on first inference, a bucket written to on first upload — is invisible until a user finds it. Where a feature has a heavy lazy path, run one real transaction through the deployed stack as the last deploy step, or accept that your users are your smoke test.

**`docker compose down` removes volumes if you pass `-v`.** Do not. For a proxied stack, `caddy_data`-style volumes hold certificates and losing them burns issuance rate limits.

**The AIC domain mapping can fail silently.** Always confirm with the "Domain Parked" check in Step 3 rather than assuming the form saved.

---

## 6. Operations

From `/opt/<project>` as `deploy`:

```bash
docker compose ps                     # status and health
docker compose logs -f app            # follow one service
docker compose restart app
docker compose up -d                  # apply an edited .env
docker stats --no-stream              # memory pressure across all projects
```

Roll back to any previously built commit — still in GHCR, same health gate:

```bash
./deploy.sh sha-1a2b3c4
```

Change the port: edit `APP_PORT` in `.env`, `docker compose up -d`, **and** update the AIC panel. Both must agree.

### Backups

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
set -a && . ./.env && set +a
mkdir -p backups
OUT="backups/<project>-$(date +%Y%m%d-%H%M%S).sql.gz"
# temp name first, so an interrupted dump never looks complete to the sweep below
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$OUT.partial"
mv "$OUT.partial" "$OUT"
find backups -name '<project>-*.sql.gz' -mtime +7 -delete
```

```cron
15 3 * * * /opt/<project>/backup.sh >> /opt/<project>/backups/backup.log 2>&1
```

Stagger cron times between projects so dumps do not run concurrently on 2 vCPUs. Backups on the same VPS do not survive losing the VPS — pull them off periodically.

---

## 7. Troubleshooting

| Symptom | Cause |
|---|---|
| "Domain Parked · AIC Cloud" | Mapping not active. Panel problem, not a VPS problem |
| 502 / 503 from the domain | AIC cannot reach `10.10.10.91:<PORT>`. Check `docker compose ps` and that `APP_PORT` matches the panel |
| Container `unhealthy`, app works | Healthcheck probing `localhost` instead of `127.0.0.1` |
| App can't authenticate to Postgres | `.env` password changed after the volume was initialised |
| CI: `Permission denied` on a script | Missing exec bit in git |
| Deploy fails pulling from GHCR | Re-run `docker login ghcr.io` as `deploy` |
| Deploy fails at SSH | VPS rebuilt → host key changed. Regenerate `VPS_SSH_KNOWN_HOSTS` |
| All visitors share a rate limit | `set_real_ip_from` does not cover AIC's proxy address |
| Missing `Access-Control-Allow-Origin` | Usually correct — a same-origin request needs none. Only investigate if the UI is on a different host than the API |

Useful one-liners:

```bash
# What is actually listening across all projects
ssh -p 20086 deploy@37.187.159.43 "ss -lntp"

# Disk pressure — find out WHAT is full before deleting anything
ssh -p 20086 deploy@37.187.159.43 "docker system df -v | head -40 && df -h /"

# The two usual culprits, in order:
#   1. superseded image tags   2. unrotated container logs
docker images 'ghcr.io/*/saga-*' --format '{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}'
du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail

# Always safe: build cache and stopped containers.
docker builder prune -af
docker container prune -f

# NOT `docker image prune -a -f`. That deletes every image without a running container —
# including the PREVIOUS tag, which is exactly what deploy.sh rolls back onto. You would be
# reclaiming disk by throwing away your only rollback. deploy.sh now prunes superseded
# saga-* tags itself after a verified deploy, keeping the current tag, the rollback target
# and `latest`; `cat /opt/saga/.image-tag` shows the live one.
```

Both causes are fixed at the source now — `deploy.sh` sweeps old tags, and every service in
`deploy/docker-compose.yml` caps its log at 10 MB × 3 — so this should stop recurring. If the
disk fills again, the interesting question is which of those two regressed.

---

## 8. Known exposure

The VPS shares the private subnet `10.10.10.0/24` with other AIC tenants, and your app's port is published on all interfaces because AIC's proxy reaches it over that network. **A neighbour on the same subnet can hit your app directly, bypassing the TLS edge** and any rate limiting keyed on the real client IP.

`ufw` cannot fix this — Docker's published ports bypass it. Once you know AIC's proxy address (read it from your web server's access log after real traffic), restrict it in the `DOCKER-USER` chain:

```bash
iptables -I DOCKER-USER -p tcp --dport <PORT> ! -s <aic-proxy-ip> -j DROP
apt-get install -y iptables-persistent    # to survive reboot
```

Severity is low for a public app, but do not put anything on this VPS that assumes the TLS edge is the only way in.

---

## 9. Quick reference

```
VPS               37.187.159.43   (shared, NAT'd)
SSH               ssh -p 20086 deploy@37.187.159.43
Private IP        10.10.10.91/24
Stack dirs        /opt/<project>
Registry          ghcr.io/<owner>/<project>
DNS               desec.io  → A @ 37.187.159.43
Edge              AIC shared proxy, TLS terminated upstream
Secrets           VPS_HOST, VPS_USER, VPS_SSH_KEY, VPS_SSH_KNOWN_HOSTS + var VPS_PORT=20086
```
