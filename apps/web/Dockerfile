# Production image for the product app (@kb/web). Build context is the REPO ROOT, because
# this is a pnpm workspace and the app depends on packages/ui via `workspace:*`.
FROM node:22-slim AS deps

RUN corepack enable
WORKDIR /repo

# Manifests only, so the install layer is cached until a dependency actually changes.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
COPY packages/ui/package.json ./packages/ui/
COPY packages/config/package.json ./packages/config/
COPY packages/sdk/package.json ./packages/sdk/
COPY packages/shared/package.json ./packages/shared/
COPY apps/web/package.json ./apps/web/
RUN pnpm install --filter @kb/web... --frozen-lockfile=false


FROM node:22-slim AS builder

RUN corepack enable
WORKDIR /repo

COPY --from=deps /repo ./
COPY packages ./packages
COPY apps/web ./apps/web

# Next inlines NEXT_PUBLIC_* at BUILD time, so these must be set here, not at runtime.
# The defaults are the production shape: one origin, Caddy routing /api/* to the API and
# /* to the marketing site.
ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_WEBSITE_URL=/
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WEBSITE_URL=$NEXT_PUBLIC_WEBSITE_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm --filter @kb/web run build


FROM node:22-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN useradd --create-home --uid 10001 app
WORKDIR /app

# `output: "standalone"` emits a self-contained server plus only the files it needs.
# (No public/ directory in this app — add a COPY for it here if one is ever introduced.)
COPY --from=builder --chown=app:app /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=app:app /repo/apps/web/.next/static ./apps/web/.next/static

USER app
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
