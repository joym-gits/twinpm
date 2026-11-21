# syntax=docker/dockerfile:1.7
# Build context is the repository root (pnpm workspace).
FROM node:24-alpine AS base
RUN corepack enable
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo

FROM base AS builder
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY packages/api-client packages/api-client
# Rewrites are resolved at build time; point them at the compose API service.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN pnpm --filter @twinpm/web build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
RUN adduser -D -u 10001 twinpm
COPY --from=builder --chown=twinpm /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=twinpm /repo/apps/web/.next/static ./apps/web/.next/static
USER twinpm
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
