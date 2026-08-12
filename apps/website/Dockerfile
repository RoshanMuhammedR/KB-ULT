# Build context is the repo root (pnpm workspace) - see deploy compose `build.context`.
FROM node:22-alpine AS base
RUN corepack enable

FROM base AS build
WORKDIR /repo
COPY . .
RUN pnpm install --frozen-lockfile
# See apps/web/Dockerfile for why these are deliberately absent, not just unset via CI.
RUN pnpm exec turbo run build --filter=@kb/website

FROM node:22-alpine
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build /repo/apps/website/.next/standalone ./
COPY --from=build /repo/apps/website/.next/static ./apps/website/.next/static
RUN chown -R app:app /app
USER app
ENV PORT=3000 HOSTNAME=0.0.0.0
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/website/server.js"]
