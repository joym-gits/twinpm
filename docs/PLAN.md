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
- [ ] SQLAlchemy models for Section 4 + Alembic migrations
- [ ] Repository layer with tenancy
- [ ] Auth (Argon2, JWT access/refresh rotation, cookies, CSRF) + RBAC
- [ ] Append-only audit log (trigger + repository)
- [ ] OpenAPI → generated TS client
- [ ] Login flow
- [ ] **Gate:** migrations apply; tenant isolation test passes; login works end to end

## Phase 3: Synthetic data
- [ ] Deterministic generator (Section 5), `make seed`, summary table
- [ ] `docs/DATA_DICTIONARY.md`
- [ ] **Gate:** two runs produce identical hashes; storyline assertions pass

## Phase 4: ML platform
- [ ] Features, registry, inference, SHAP
- [ ] 7.1 delay classifier, 7.2 effort, 7.3 Monte Carlo + backtest, 7.4 anomaly, 7.5 themes, 7.6 delegation, 7.7 preference, 7.8 health
- [ ] `make train`, `docs/ML.md`
- [ ] **Gate:** Section 12 ML tests pass

## Phase 5: Core APIs
- [ ] Program/health/briefing, roadmap, scenarios, delegation, risk, dependencies, forecasts, insights
- [ ] Suggestions + Action Executor + policy engine + undo, SSE events
- [ ] **Gate:** router integration tests pass; OpenAPI complete

## Phase 6: LLM, agents, RAG
- [ ] Model factory (ChatAnthropic / DemoChatModel), tools, specialist subgraphs, supervisor + policy_gate + interrupt()
- [ ] AsyncPostgresSaver checkpointing, background graphs, SSE mapping
- [ ] Citation validator, guardrails, PII redaction, injection defence
- [ ] RAG indexing + hybrid retrieval; chat SSE; comms/strategy endpoints
- [ ] MCP server (P1) + client seam; evals; ADR 0002; `docs/AGENTS.md`
- [ ] **Gate:** graph tests + evals pass in demo mode; interrupt survives restart

## Phase 7: Frontend screens
- [ ] All Section 9.3 screens, live updates, command palette, Ask the Twin drawer, approvals
- [ ] **Gate:** screens load with seed data, no console errors; Vitest passes; Lighthouse a11y ≥ 90

## Phase 8: Workers and connectors
- [ ] ARQ jobs + schedules; mock connectors with live ticks; live adapter skeletons + respx tests
- [ ] **Gate:** worker runs jobs; dashboard updates on ticks

## Phase 9: Hardening
- [ ] Security headers, rate limits, perf checks, Helm chart, SECURITY.md, ARCHITECTURE.md, ADRs
- [ ] **Gate:** all tests pass; `docker compose up` from clean clone works

## Phase 10: Demo polish
- [ ] Playwright demo E2E, DEMO_SCRIPT.md, Reset Demo, README
- [ ] **Gate:** E2E passes; fresh clone + `make demo` to login < 5 min
