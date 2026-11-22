# TwinPM Build Plan

Tracks Section 14 of `BUILD_SPEC.md`. A phase is checked only after its gate ran and passed.

## Phase 1: Foundations
- [x] Monorepo (pnpm workspaces + turbo, uv for Python)
- [x] Tooling: ruff, mypy --strict, ESLint, Prettier, pre-commit
- [x] docker-compose: Postgres 16 + pgvector, Redis 7, api, worker, web
- [x] FastAPI skeleton: config, structlog, OpenTelemetry, error envelope, request IDs
- [x] `/healthz`, `/readyz`, `/metrics`
- [x] Next.js shell: design system, theme, layout
- [x] CI pipeline (workflow YAML validated locally; runs on first push)
- [x] **Gate:** `make dev` starts everything; `/readyz` green; shell renders; CI config valid

## Phase 2: Data and auth
- [x] SQLAlchemy models for Section 4 + Alembic migrations
- [x] Repository layer with tenancy
- [x] Auth (Argon2, JWT access/refresh rotation, cookies, CSRF) + RBAC
- [x] Append-only audit log (trigger + repository)
- [x] OpenAPI → generated TS client
- [x] Login flow
- [x] **Gate:** migrations apply; tenant isolation test passes; login works end to end

## Phase 3: Synthetic data
- [x] Deterministic generator (Section 5), `make seed`, summary table
- [x] `docs/DATA_DICTIONARY.md`
- [x] **Gate:** two runs produce identical hashes; storyline assertions pass

## Phase 4: ML platform
- [x] Features, registry, inference, SHAP
- [x] 7.1 delay classifier, 7.2 effort, 7.3 Monte Carlo + backtest, 7.4 anomaly, 7.5 themes, 7.6 delegation, 7.7 preference, 7.8 health
- [x] `make train`, `docs/ML.md`
- [x] **Gate:** Section 12 ML tests pass

## Phase 5: Core APIs
- [x] Program/health/briefing, roadmap, scenarios, delegation, risk, dependencies, forecasts, insights
- [x] Suggestions + Action Executor + policy engine + undo, SSE events
- [x] **Gate:** router integration tests pass; OpenAPI complete

## Phase 6: LLM, agents, RAG
- [x] Model factory (ChatAnthropic / DemoChatModel), tools, specialist subgraphs, supervisor + policy_gate + interrupt()
- [x] AsyncPostgresSaver checkpointing, background graphs, SSE mapping
- [x] Citation validator, guardrails, PII redaction, injection defence
- [x] RAG indexing + hybrid retrieval; chat SSE; comms/strategy endpoints
- [x] MCP server (P1) + client seam; evals; ADR 0002; `docs/AGENTS.md`
- [x] **Gate:** graph tests + evals pass in demo mode; interrupt survives restart (Claude-key smoke test not run: no API key in this environment)

## Phase 7: Frontend screens
- [x] All Section 9.3 screens, live updates, command palette, Ask the Twin drawer, approvals
- [x] **Gate:** screens load with seed data, no console errors; Vitest passes; Lighthouse a11y ≥ 90

## Phase 8: Workers and connectors
- [x] ARQ jobs + schedules; mock connectors with live ticks; live adapter skeletons + respx tests
- [x] **Gate:** worker runs jobs; dashboard updates on ticks

## Phase 9: Hardening
- [x] Security headers, rate limits, perf checks, Helm chart, SECURITY.md, ARCHITECTURE.md, ADRs
- [x] **Gate:** all tests pass; `docker compose up` from clean clone works

## Phase 10: Demo polish
- [x] Playwright demo E2E, DEMO_SCRIPT.md, Reset Demo, README
- [x] **Gate:** E2E passes; fresh clone + `make demo` to login < 5 min

## Gate evidence (2026-11-22)
- Backend: 85 pytest tests pass (testcontainers Postgres + Redis); ruff and mypy --strict clean.
  Coverage: services 87%, ml 93%, services/policy 98%, total 88%.
- Agent evals (demo model): 26/26, tool-selection accuracy 1.0, citation validity 1.0,
  0 policy violations. Interrupt survives a checkpointer restart (test).
- ML: delay ROC-AUC 0.83 (seed 42), storyline items > 0.65, launch P80 moves >= 7 days with the
  Payments slip, rebalance recovers ~73% of it.
- Frontend: ESLint + tsc clean; Vitest 11/11; Lighthouse accessibility 100 on Command Center;
  no console errors on any screen (checked in Chrome).
- Playwright demo E2E passes against `make dev` and against the Docker Compose stack.
- Fresh `git clone` + `make demo` reached a working login in 105 s (warm Docker layer cache).
- Dashboard API p95 <= 77 ms on seed data; Monte Carlo 10k runs ~0.25 s; demo reset 3.4 s.
- Not verified: GitHub Actions run (no remote configured); chat/status report with a real
  Anthropic key (none in this environment).
