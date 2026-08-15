# Build context is the repo root (pnpm workspace) - see deploy compose `build.context`.
FROM node:22-alpine AS base
RUN corepack enable

FROM base AS build
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile
# No NEXT_PUBLIC_* ARG/ENV for the URL vars on purpose: apps/web falls back to relative paths
# (/api, /, and its own basePath /app) when these are genuinely absent from the build
# environment. An ARG with no default, even when never passed via --build-arg, still makes the
# subsequent ENV line set the var to an EMPTY STRING rather than leaving it unset - and
# `"" ?? "/app"` does NOT fall back (only null/undefined do), so declaring those at all
# silently breaks the fallback. Leaving them out entirely is what lets the fallback work.
#
# NEXT_PUBLIC_GOOGLE_CLIENT_ID is the one exception, and safely so: it has no fallback to
# break. GoogleButton reads `?? ""` and then renders nothing when the value is empty, so the
# empty-string-not-unset behaviour above lands on exactly the intended "Google sign-in is
# disabled" state. It must be declared here because Next.js inlines NEXT_PUBLIC_* at BUILD
# time - passing it as a runtime container env would never reach the browser bundle.
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID
RUN pnpm exec turbo run build --filter=@kb/web

FROM node:22-alpine
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
RUN chown -R app:app /app
USER app
ENV PORT=3000 HOSTNAME=0.0.0.0
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/app/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
