FROM node:22-slim

WORKDIR /repo

RUN corepack enable

COPY package.json pnpm-workspace.yaml turbo.json ./
COPY packages ./packages
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --filter @kb/web... --frozen-lockfile=false

COPY apps/web ./apps/web

WORKDIR /repo/apps/web
EXPOSE 3000
CMD ["pnpm", "dev"]
