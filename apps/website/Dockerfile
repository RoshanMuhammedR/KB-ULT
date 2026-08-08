# Production image for the marketing site (@kb/website). Build context is the REPO ROOT —
# this is a pnpm workspace and the app depends on packages/ui via `workspace:*`.
FROM node:22-slim AS deps

RUN corepack enable
WORKDIR /repo

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
COPY packages/ui/package.json ./packages/ui/
COPY packages/config/package.json ./packages/config/
COPY packages/sdk/package.json ./packages/sdk/
COPY packages/shared/package.json ./packages/shared/
COPY apps/website/package.json ./apps/website/
RUN pnpm install --filter @kb/website... --frozen-lockfile=false


FROM node:22-slim AS builder

RUN corepack enable
WORKDIR /repo

COPY --from=deps /repo ./
COPY packages ./packages
COPY apps/website ./apps/website

# Inlined at build time. In production the product app is /app on this same origin.
ARG NEXT_PUBLIC_PRODUCT_URL=/app
ENV NEXT_PUBLIC_PRODUCT_URL=$NEXT_PUBLIC_PRODUCT_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm --filter @kb/website run build


FROM node:22-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN useradd --create-home --uid 10001 app
WORKDIR /app

# (No public/ directory in this app — add a COPY for it here if one is ever introduced.)
COPY --from=builder --chown=app:app /repo/apps/website/.next/standalone ./
COPY --from=builder --chown=app:app /repo/apps/website/.next/static ./apps/website/.next/static

USER app
EXPOSE 3000

CMD ["node", "apps/website/server.js"]
