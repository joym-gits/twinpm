#!/usr/bin/env bash
# Local development: infra in Docker, api/worker/web as local processes with reload.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --wait postgres redis
(cd apps/api && uv run alembic upgrade head)
trap 'kill 0' EXIT INT TERM
(cd apps/api && uv run uvicorn twinpm.main:app --reload --port "${API_PORT:-8000}") &
(cd apps/api && uv run arq twinpm.workers.settings.WorkerSettings --watch twinpm) &
(cd apps/web && pnpm dev) &
wait
