SHELL := /bin/bash
API := cd apps/api &&
WEB := cd apps/web &&
export COREPACK_ENABLE_DOWNLOAD_PROMPT := 0

.PHONY: install dev up down migrate seed train openapi test test-api test-web lint typecheck e2e eval demo reset

install:            ## Install Python and JS dependencies
	$(API) uv sync && uv run python -m twinpm.rag.embedding
	pnpm install

dev:                ## Infra in Docker + api, worker, web locally with reload
	./scripts/dev.sh

up:                 ## Full stack in Docker
	docker compose up -d --build --wait

down:
	docker compose down

migrate:
	$(API) uv run alembic upgrade head

seed:               ## Reset and seed the NovaPay demo org (deterministic, --seed 42)
	$(API) uv run python -m twinpm.seed --seed 42

train:              ## Train every model into the registry
	$(API) uv run python -m twinpm.ml.train_all

openapi:            ## Export OpenAPI and regenerate the TypeScript client
	$(API) uv run python -m twinpm.export_openapi ../../packages/api-client/openapi.json
	cd packages/api-client && pnpm generate

test: test-api test-web

test-api:
	$(API) uv run pytest --cov=twinpm --cov-report=term-missing:skip-covered

test-web:
	$(WEB) pnpm test

lint:
	$(API) uv run ruff check twinpm && uv run ruff format --check twinpm
	$(API) uv run mypy twinpm
	$(WEB) pnpm lint && pnpm typecheck

e2e:                ## Playwright demo flow against a running stack (demo mode)
	$(WEB) pnpm e2e

eval:               ## Agent evals (uses Claude when ANTHROPIC_API_KEY is set)
	$(API) uv run python -m twinpm.agents.evals.run

demo:               ## One command: stack up, seed, train, print login
	docker compose up -d --build --wait
	docker compose exec -T api python -m twinpm.seed --seed 42
	docker compose exec -T api python -m twinpm.ml.train_all
	@echo ""
	@echo "TwinPM is ready: http://localhost:$${WEB_PORT:-3100}/login"
	@echo "Login: priya@novapay.example / $${SEED_DEMO_PASSWORD:-TwinPM-demo-2026!}"
