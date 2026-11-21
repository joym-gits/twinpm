# TwinPM — Build Specification for Claude Code

> **How to use this file:** put it at the root of an empty repository as `BUILD_SPEC.md`, open Claude Code in that folder, and say:
> *"Read BUILD_SPEC.md completely, then build TwinPM phase by phase exactly as specified. Follow the Working Rules. Do not skip phases or verification gates."*

---

## 0. Your role and mission

You are a principal engineer and product-minded tech lead. You are building **TwinPM**, an enterprise-grade **AI Digital Twin for Technical Program Managers (TPMs) and Technical Product Managers**.

TwinPM keeps two live models:

1. **A model of the program**: people, teams, skills, work items, dependencies, risks, decisions, documents and delivery history, held in a program knowledge graph.
2. **A model of the TPM**: their priorities, writing style, risk tolerance, escalation rules and decision history, learned from how they accept, edit or reject the twin's suggestions.

On top of these, TwinPM **watches** delivery signals, **predicts** problems (ML), **simulates** options (Monte Carlo and what-if), **recommends and delegates** work, **communicates** with stakeholders, and **acts** within a TPM-controlled autonomy policy. Every action is explained and audited.

The first release will be demoed at a hackathon, but it must be **architected, coded, tested and documented like a real enterprise SaaS product**: multi-tenant, secure, observable, tested, containerised and extensible. Use realistic mock connectors and a synthetic dataset for the demo. Integrations must sit behind real interfaces so live Jira, GitHub and Slack adapters can be plugged in later without refactoring.

**Positioning line (used in the UI and README):** *"TwinPM doesn't just answer questions about your program. It runs it the way you would, and shows its reasoning every time."*

---

## 1. Working rules (follow these throughout)

1. **Plan first.** Before writing code, create `docs/PLAN.md` with the phase checklist from Section 14. Update it as you complete each item.
2. **Build in phases** (Section 14). At the end of each phase, run the verification gate (build, lint, type-check, tests, and the app actually starting). Fix every failure before moving on.
3. **No placeholders in delivered code.** No `TODO: implement`, no stub functions returning fake constants (except inside the explicitly named `mock` connectors and `demo` fallbacks). If something is out of scope, leave it out cleanly and record it in `docs/ROADMAP.md`.
4. **Type everything.** TypeScript in `strict` mode on the frontend. Python type hints everywhere with `mypy --strict` passing on the backend. Pydantic v2 models for every API schema.
5. **Single source of truth for API contracts:** FastAPI generates OpenAPI; the frontend client is **generated** from it (`openapi-typescript` + a thin fetch wrapper). Never hand-write duplicate types.
6. **Configuration from environment only** (12-factor). Provide `.env.example`. Never commit secrets. The app must run **without** an `ANTHROPIC_API_KEY` by falling back to deterministic "demo mode" responses (Section 8.8).
7. **Every AI output must be grounded and explainable.** Agent answers cite entity IDs (tickets, docs, decisions). ML predictions return top contributing factors.
8. **Write tests as you go**, not at the end. Coverage targets are in Section 12.
9. **Keep commits logical** (one per completed sub-step) with conventional commit messages, if git is initialised.
10. If a library choice in this spec fails to install or is incompatible, choose the closest well-maintained alternative, record the decision in `docs/adr/`, and continue. Do not stop to ask unless a decision is irreversible.
11. When the build is complete, run the full demo flow (Section 13) end to end yourself, and fix anything that breaks.

---

## 2. Tech stack (use these unless a rule in Section 1.10 applies)

| Layer | Choice |
|---|---|
| Monorepo | `pnpm` workspaces + `turbo` for JS; `uv` for Python |
| Frontend | **Next.js 15 (App Router)**, React 19, TypeScript strict, **Tailwind CSS**, **shadcn/ui** (Radix), **TanStack Query**, **Zustand** (UI state only), **Recharts** (charts), **React Flow / @xyflow/react** (dependency graph), **react-hook-form + zod**, `lucide-react` icons, `next-themes` (dark/light) |
| Backend API | **Python 3.12, FastAPI**, Pydantic v2, **SQLAlchemy 2.0 (async)** + **Alembic**, `asyncpg`, `httpx`, **SSE** for streaming (`sse-starlette`) |
| Background jobs | **ARQ** (Redis-based async jobs) for scheduled scoring, briefings, retraining and connector syncs |
| Database | **PostgreSQL 16** with **pgvector** (embeddings) |
| Cache / queue / pub-sub | **Redis 7** |
| Graph analytics | Relational graph tables in Postgres + **NetworkX** in-process for critical path and impact analysis (Neo4j is a documented future option, not built) |
| ML | **scikit-learn**, **XGBoost** (or LightGBM), **SHAP**, NumPy, pandas, `hdbscan` (fallback: KMeans), `sentence-transformers` (`all-MiniLM-L6-v2`) for local embeddings |
| **Agentic framework** | **LangGraph** (Python, latest stable 1.x: check PyPI and pin the exact version) for multi-agent orchestration, durable state, human-in-the-loop approvals and streaming. Use `langchain-anthropic` (`ChatAnthropic`) as the model binding, **`langgraph-checkpoint-postgres`** (`AsyncPostgresSaver`) for persistence, and **`langchain-mcp-adapters`** for MCP. Optional tracing: **LangSmith** (env-toggled) alongside OpenTelemetry. See Section 8 |
| LLM | **Anthropic Claude** through LangGraph/`ChatAnthropic`, with tool use, structured outputs and streaming. Model from env `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`; allow `claude-opus-5-5` for the supervisor via `ANTHROPIC_MODEL_ORCHESTRATOR`). Use the raw `anthropic` SDK only for simple one-shot generation endpoints that don't need a graph |
| Auth | Email/password + JWT (access + refresh, httpOnly cookies) for the demo; **OIDC-ready** abstraction (`AuthProvider` interface) for SSO later. **RBAC** with roles: `org_admin`, `tpm`, `eng_manager`, `executive`, `member`, `viewer` |
| Observability | **OpenTelemetry** traces (FastAPI + SQLAlchemy + httpx instrumentation), **structlog** JSON logs with request IDs, **Prometheus** `/metrics`, LLM call telemetry (tokens, latency, cost estimate) |
| Testing | Backend: `pytest`, `pytest-asyncio`, `httpx` test client, `testcontainers` (Postgres). Frontend: **Vitest** + React Testing Library. E2E: **Playwright** |
| Quality | `ruff` (lint + format), `mypy --strict`, ESLint, Prettier, `pre-commit` hooks |
| Containers | Multi-stage **Dockerfiles**, **docker-compose** for local (web, api, worker, postgres, redis, otel-collector optional) |
| CI | **GitHub Actions**: lint, type-check, test (backend, frontend), build images, Playwright smoke |
| Deploy (documented, scaffolded) | **Helm chart** under `deploy/helm/twinpm` with values for dev/prod, plus K8s probes and resource limits |

---

## 3. Repository structure

```
twinpm/
├── BUILD_SPEC.md
├── README.md
├── .env.example
├── docker-compose.yml
├── Makefile                     # make dev | seed | train | test | lint | e2e | demo
├── turbo.json  pnpm-workspace.yaml  package.json
├── .github/workflows/ci.yml
├── deploy/helm/twinpm/...
├── docs/
│   ├── PLAN.md  ROADMAP.md  ARCHITECTURE.md  API.md  ML.md  AGENTS.md
│   ├── SECURITY.md  DEMO_SCRIPT.md  DATA_DICTIONARY.md
│   └── adr/0001-*.md ...
├── apps/
│   ├── web/                     # Next.js frontend
│   │   ├── app/(auth)/login/...
│   │   ├── app/(app)/[org]/command-center/...
│   │   ├── app/(app)/[org]/strategy/...
│   │   ├── app/(app)/[org]/roadmap/...
│   │   ├── app/(app)/[org]/delegation/...
│   │   ├── app/(app)/[org]/risk/...
│   │   ├── app/(app)/[org]/comms/...
│   │   ├── app/(app)/[org]/insights/...
│   │   ├── app/(app)/[org]/settings/{persona,autonomy,integrations,members}/...
│   │   ├── components/{ui,charts,graph,twin,layout}/...
│   │   ├── lib/{api,auth,hooks,utils}/...
│   │   └── tests/ (vitest) e2e/ (playwright)
│   └── api/                     # FastAPI backend
│       ├── pyproject.toml
│       ├── alembic/
│       └── twinpm/
│           ├── main.py  config.py  deps.py
│           ├── core/        # security, rbac, tenancy, logging, telemetry, errors, pagination, rate_limit
│           ├── db/          # session, base, models/*.py
│           ├── schemas/     # pydantic request/response models
│           ├── api/v1/      # routers per domain
│           ├── services/    # business logic per domain (no FastAPI imports)
│           ├── graph/       # knowledge-graph queries, networkx builders, critical path
│           ├── ml/          # features, training, registry, inference, explain (SHAP), forecasting, anomaly, clustering, delegation, preference
│           ├── agents/      # orchestrator, specialist agents, tools, prompts/, policy engine, memory
│           ├── llm/         # provider interface, anthropic client, demo-mode provider, telemetry
│           ├── rag/         # chunking, embedding, retrieval (hybrid), citation formatting
│           ├── connectors/  # base interfaces + mock/{jira,github,slack,calendar,docs} + jira/ github/ slack/ (real adapter skeletons behind feature flags)
│           ├── workers/     # ARQ worker settings + jobs
│           ├── seed/        # synthetic data generator (deterministic, seeded)
│           └── tests/
└── packages/
    └── api-client/              # generated TS client from OpenAPI
```

---

## 4. Domain and data model

Every table has: `id UUID PK`, `org_id UUID` (tenant, indexed, enforced, except `organizations`), `created_at`, `updated_at`. Use soft delete (`deleted_at`) where noted. Enforce tenant isolation in a **repository layer** that always filters by `org_id` from the authenticated context. Add a test that proves cross-tenant reads are impossible.

### 4.1 Core entities

| Entity | Key fields |
|---|---|
| `organizations` | name, slug, plan, settings JSONB |
| `users` | email (unique per org), name, password_hash, role, is_active, last_login_at |
| `people` | (the workforce the twin reasons about; may link to `users`) name, title, team_id, capacity_hours_per_week, timezone, growth_goals TEXT[], avatar_url, user_id NULL |
| `skills` / `person_skills` | skill name, category; person_id, skill_id, level 1–5, evidence_count |
| `teams` | name, description, manager_person_id |
| `programs` | name, objective, status, target_date, owner_user_id (TPM), health_weights JSONB |
| `objectives` (OKRs) | program_id, title, key_results JSONB, quarter |
| `initiatives` | program_id, objective_id, title, description, roadmap_bucket (`now`/`next`/`later`), rice JSONB {reach, impact, confidence, effort, score}, wsjf JSONB, target_date, status |
| `epics` | initiative_id, team_id, title, description, status, target_date |
| `work_items` | epic_id, team_id, key (e.g. `PAY-142`), title, description, type (`story`/`task`/`bug`/`spike`), status (`todo`/`in_progress`/`in_review`/`blocked`/`done`), story_points, estimate_days, assignee_person_id, created_at_src, started_at, done_at, due_date, reopen_count, pr_review_hours, comments_count, labels TEXT[], external_ref JSONB |
| `work_item_events` | work_item_id, event_type (status_change, reassigned, reopened, comment, pr_opened, pr_reviewed, pr_merged), from_value, to_value, actor_person_id, occurred_at |
| `dependencies` | from_type/from_id → to_type/to_id (polymorphic among initiative/epic/work_item), kind (`blocks`/`relates`), owning_team_id, status |
| `sprints` | team_id, name, start_date, end_date, goal, committed_points, completed_points |
| `milestones` | program_id, name, target_date, scope (epic IDs), latest_forecast JSONB |
| `risks` | program_id, title, description, probability 0–1, impact 1–5, severity (computed), owner_person_id, mitigation, status (`open`/`mitigating`/`closed`), source (`model`/`manual`/`agent`), linked_entities JSONB |
| `decisions` | program_id, title, context, options JSONB, chosen_option, rationale, participants UUID[], decided_at, source_document_id |
| `documents` | program_id, type (`design_doc`/`meeting_notes`/`prd`/`transcript`/`other`), title, body (markdown), author_person_id, source_url |
| `document_chunks` | document_id, chunk_index, content, embedding VECTOR(384), token_count |
| `feedback_items` | source (`support`/`sales`/`survey`/`interview`), customer_segment, text, sentiment, theme_id, received_at, embedding VECTOR(384) |
| `themes` | label, summary, size, avg_sentiment, opportunity_score JSONB |
| `team_signals` | team_id, date, sentiment_index, message_volume, after_hours_ratio (team-level aggregates only; **never per person**) |
| `metrics_daily` | team_id, date, velocity, throughput, cycle_time_p50, bug_inflow, review_latency_p50, wip |
| `ml_predictions` | entity_type, entity_id, model_name, model_version, score, drivers JSONB [{feature, value, contribution}], predicted_at |
| `forecasts` | milestone_id, p50_date, p80_date, p95_date, distribution JSONB (histogram), assumptions JSONB, run_at |
| `anomalies` | team_id, metric, date, value, expected, z_score, method, explanation, status |
| `suggestions` | program_id, agent, type (`reassign`/`create_task`/`status_report`/`risk_update`/`nudge`/`roadmap_change`/`scenario`), title, payload JSONB, explanation, drivers JSONB, citations JSONB, autonomy_level_required, status (`pending`/`accepted`/`edited`/`rejected`/`auto_executed`/`expired`), responded_by, responded_at, feedback_reason |
| `scenarios` | program_id, name, changes JSONB, result JSONB (forecast deltas, risk deltas, capacity), created_by |
| `persona_profiles` | user_id, priorities JSONB (ordered), style_examples TEXT[], tone (`concise`/`detailed`/`formal`/`friendly`), risk_tolerance (`low`/`medium`/`high`), escalation_rules JSONB, working_hours |
| `autonomy_policies` | user_id, program_id NULL, action_type, level (1–4) |
| `preference_events` | user_id, suggestion_id, suggestion_type, context_features JSONB, outcome, edit_diff TEXT |
| `audit_log` (append-only) | actor_type (`user`/`twin`/`system`), actor_id, action, entity_type, entity_id, before JSONB, after JSONB, reason, suggestion_id NULL, request_id, ip, occurred_at. **No updates or deletes allowed** (enforce via DB trigger + repository) |
| `notifications` | user_id, kind, title, body, link, read_at |
| `conversations` / `messages` | Ask the Twin threads; message role, content, tool_calls JSONB, citations JSONB, agent_trace JSONB |
| `integrations` | provider (`jira`/`github`/`slack`/`gcal`/`confluence`), mode (`mock`/`live`), config JSONB (encrypted secrets via Fernet with key from env), last_sync_at, status |
| `llm_calls` | purpose, model, input_tokens, output_tokens, latency_ms, cost_estimate_usd, status, prompt_version, request_id |

Create `docs/DATA_DICTIONARY.md` describing every table and field. Add sensible indexes (org_id + FKs, `work_items(status, due_date)`, ivfflat/hnsw on embeddings).

---

## 5. Synthetic data generator (critical for the demo)

Implement `apps/api/twinpm/seed/` as a **deterministic** generator (`--seed 42`), run with `make seed`. It must produce data with **realistic causal structure**, so the ML models learn real signal rather than noise.

### 5.1 Company and program

- Organisation: **NovaPay** (fictional fintech). Program: **"Checkout 2.0"**. Launch milestone **"Public Launch"** with target date = *today + ~16 weeks* (compute relative to the current date so the demo never goes stale).
- Teams (5 people each, 15 total): **Platform**, **Payments**, **Mobile**. Give each person a realistic name (diverse, include Indian names), title, 3–6 skills with levels (e.g. `go`, `python`, `react-native`, `kafka`, `postgres`, `oauth`, `payments-compliance`, `k8s`, `observability`, `ios`, `android`, `api-design`), capacity of 32–40 hrs/week, and growth goals.
- Users: 1 org admin, **Priya Sharma (TPM, the twin owner)**, Arjun Mehta (Technical Product Manager), 3 engineering managers, 1 executive (Rahul Verma, VP Engineering). Demo password for every user, from `.env` `SEED_DEMO_PASSWORD`.

### 5.2 History (about 6 months)

- About **400 completed work items** and **about 120 open items** across 4 objectives, 8 initiatives and about 18 epics, with 2-week sprints.
- Generate durations from a model: `base_days ~ lognormal(by type and points)`, inflated by owner utilisation, number of blockers, review latency and reopen count. Mark an item **late** if `done_at > due_date`. This gives the delay classifier real signal to learn.
- Generate `work_item_events` consistent with each item's lifecycle.
- About **25 cross-team dependency edges**, with the **Payments API epic on the critical path** of the launch.
- Daily team metrics derived from the work items (not random).

### 5.3 Seeded storyline (the demo hero moment)

Over the **last 2 sprints**:
- **Payments** velocity drops about 30%.
- Payments lead **Vikram Rao** is at **about 110% utilisation**.
- Review latency on Payments PRs rises about **2.3x**.
- Two Payments API items are reopened.
- Three of Priya's launch epics (Mobile checkout UI, Platform rate limiter, Fraud hooks) depend on the Payments API.
- In the Platform team, **Karan** (strong `go` + `api-design`, at 60% load, growth goal: payments) and **Li Wei** (strong `postgres`, 55% load) are the optimal reassignment targets.

Expected result after training: the risk model flags Payments API items at **> 0.65** probability; the forecaster moves launch P80 by about **9–12 days**; the anomaly detector flags Payments velocity and review latency; the briefing ranks this as item #1; the rebalance scenario recovers most of the slip.

### 5.4 Content

- **8 design docs** (markdown, realistic: Payments API v2, Rate limiter, Mobile checkout, Fraud hooks, Observability, Data retention, Idempotency keys, Event streaming with a Kafka vs SQS section).
- **12 meeting notes / transcripts**, including one recent "Architecture sync" transcript with 3 implicit decisions and 6 action items (used in the Comms demo).
- **15 decisions** (including "Use Kafka over SQS for payment events", with rationale and participants).
- **150 customer feedback items** across 5–6 latent themes: bulk export (about 40, negative), saved cards, UPI autopay, refund status visibility, multi-currency, dark mode. Assign `received_at` over 6 months.
- Team-level signals: Payments sentiment declining and after-hours ratio rising over the last 3 weeks.

The generator must be **idempotent** (`make seed` resets the demo org) and must print a summary table at the end.

---

## 6. Backend services and API (v1)

All routes live under `/api/v1`, are org-scoped via the authenticated user, are RBAC-checked, paginated (cursor-based) where they return lists, and return a consistent error envelope `{error: {code, message, details, request_id}}`. Document every route in OpenAPI with examples. Rate limit the expensive AI routes (per user, via Redis).

### 6.1 Auth and organisation
- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- `GET/POST/PATCH /members` (admin), `GET /org`, `PATCH /org/settings`

### 6.2 Program and Command Center
- `GET /programs`, `GET /programs/{id}`
- `GET /programs/{id}/health` → `{score, subscores:{schedule, scope, quality, dependencies, team}, trend:[{date, score}], drivers:[...]}`
- `GET /programs/{id}/briefing` → top 3 attention items `{rank, title, why, severity, evidence:[citations], recommended_action:{suggestion_id, label}}`
- `GET /programs/{id}/activity` → twin and user actions feed (from audit log)

### 6.3 Strategy
- `GET /feedback`, `POST /feedback/import` (CSV)
- `POST /strategy/themes/recompute` (job) and `GET /strategy/themes` (with opportunity scores)
- `POST /strategy/prd` `{idea, theme_id?}` → streamed PRD markdown (problem, users, goals, non-goals, metrics, requirements, risks, open questions), saved as a `document`
- `POST /strategy/devils-advocate` `{document_id | text}` → assumptions, counter-arguments, validation experiments
- `POST /strategy/okrs/draft` `{program_id}`

### 6.4 Roadmap and planning
- `GET /roadmap?program_id=` → initiatives by bucket, with RICE/WSJF and dependencies
- `PATCH /initiatives/{id}` (bucket, scores); every change writes the audit log
- `POST /scenarios/simulate` `{program_id, changes:[{type:"add_scope"|"remove_scope"|"capacity_change"|"reassign"|"date_shift", ...}]}` → `{baseline:{p50,p80,p95}, scenario:{...}, delta_days, risk_delta, capacity_delta, affected_epics:[...], narrative}`
- `POST /scenarios` (save), `GET /scenarios`
- `POST /planning/breakdown` `{epic_id | text}` → proposed stories with acceptance criteria and ML estimates (as `create_task` suggestions)
- `POST /planning/sprint-plan` `{team_id, sprint_id}` → capacity (minus PTO and meetings), recommended commitment, stretch items

### 6.5 Delegation
- `GET /delegation/workload?program_id=` → per-person utilisation, assigned points, overload flags (> 85%)
- `GET /delegation/candidates/{work_item_id}` → ranked people `{person, score, factors:{skill_match, availability, throughput_similar, growth_alignment, context_continuity}, explanation}`
- `POST /delegation/rebalance` `{program_id, scope?}` → plan of reassignments (as suggestions) with forecast impact
- `POST /delegation/nudges/run` (job): finds stalled items and creates `nudge` suggestions or auto-executes them according to policy

### 6.6 Risk and dependencies
- `GET /risk/work-items?program_id=&min_score=` → items with delay probability and SHAP drivers
- `GET /risk/register?program_id=`, `POST /risk/register`, `PATCH /risk/register/{id}`
- `GET /dependencies/graph?program_id=` → nodes and edges with team, status, risk score, **critical path flags** and slack
- `POST /dependencies/impact` `{entity_id, slip_days}` → cascade: affected entities, new forecast
- `GET /forecasts/{milestone_id}` and `POST /forecasts/{milestone_id}/run`

### 6.7 Comms
- `POST /comms/status-report` `{program_id, audience:"executive"|"engineering"|"customer", period}` → streamed markdown with RAG status, wins, risks, asks, next steps, written in the persona's tone with citations; creates a `status_report` suggestion
- `POST /comms/extract` `{document_id | transcript_text}` → `{decisions:[...], action_items:[{title, owner_person_id, due_date, confidence}]}` → suggestions
- `GET /decisions?q=` (hybrid search), `POST /decisions`
- `POST /comms/meeting-prep` `{meeting_title, attendee_ids, program_id}`

### 6.8 Insights
- `GET /insights/metrics?team_id=&metric=&from=&to=`
- `GET /insights/anomalies?program_id=`
- `GET /insights/team-health?program_id=` (team-level only; suppress any team with fewer than 5 people)
- `POST /insights/ask` `{question}` → NL analytics: the agent uses safe, parameterised metric tools (no raw SQL from the LLM) and returns a chart spec plus a narrative

### 6.9 Twin, suggestions, policy and audit
- `GET /suggestions?status=pending`, `POST /suggestions/{id}/respond` `{action:"accept"|"reject"|"edit", edited_payload?, reason?}` → executes via the **Action Executor** if accepted; logs a `preference_event`; writes the audit log
- `POST /suggestions/{id}/undo` (for reversible actions, within 24h)
- `GET/PUT /persona`, `GET/PUT /autonomy-policy`
- `GET /audit?entity_type=&entity_id=&actor_type=`
- `GET /notifications`, `POST /notifications/{id}/read`

### 6.10 Ask the Twin (chat)
- `POST /chat/conversations`, `GET /chat/conversations/{id}`
- `POST /chat/conversations/{id}/messages` → **SSE stream** of events: `agent_started`, `tool_call`, `tool_result` (summarised), `token`, `citation`, `suggestion_created`, `done`, `error`

### 6.11 Platform
- `GET /healthz` (liveness), `GET /readyz` (DB, Redis, model registry), `GET /metrics` (Prometheus)
- `GET /integrations`, `PATCH /integrations/{id}` (mode mock/live), `POST /integrations/{id}/sync`

### 6.12 Service-layer rules
- Routers are thin. All logic lives in `services/` and is unit tested without HTTP.
- All writes that change program state go through **one Action Executor** (`services/actions.py`). It validates the payload, checks RBAC, checks the autonomy policy when the actor is the twin, applies the change in a transaction, writes the audit log (before/after), and emits a domain event to Redis pub/sub (the UI live-refreshes via SSE `/events/stream`).

---

## 7. ML subsystem (`twinpm/ml/`)

Build a small but real ML platform: feature builders, training pipelines, a **versioned model registry** (local filesystem `models/{name}/{version}/model.joblib` + `metadata.json` with metrics, features, training data hash and timestamp), inference services and SHAP explanations. Run `make train` to train all models; the worker retrains nightly. Document every model in `docs/ML.md` (purpose, features, metrics, limitations).

### 7.1 Delay Risk Classifier
- **Target:** work item finishes after its due date.
- **Features:** age_days, days_in_current_status, status, type, story_points, reopen_count, pr_review_hours, open_blocker_count, upstream_dependency_risk (max of parents), assignee_utilisation, assignee_on_time_rate_90d, team_velocity_trend (last 2 sprints vs 6-sprint mean), comments_count, days_to_due.
- **Model:** XGBoost classifier with time-based train/validation split (no leakage). Calibrate with isotonic regression.
- **Explain:** SHAP TreeExplainer, returning the top 3 drivers in human-readable form (e.g. "PR review time 2.3x the team norm").
- **Metrics:** ROC-AUC (target ≥ 0.80 on synthetic data), precision@10 and a Brier score, stored in metadata and shown in the UI's "Model card" drawer.

### 7.2 Effort Estimator
- Gradient-boosted regressor on type, points, team, component labels and text embedding (reduced with PCA to 16 dims). Return the estimate in days plus an 80% interval (quantile regression or residual bootstrap), together with the 3 most similar past items (cosine similarity on embeddings). Metric: MAE.

### 7.3 Delivery Forecaster (Monte Carlo)
- For each milestone: take the remaining work items in scope and sample per-team throughput from the last N sprints (bootstrap), adjusted for capacity changes. Add a delay for each item, sampled using its delay probability, and respect dependency ordering (topological). Run **10,000 simulations** (vectorised NumPy, under 1s).
- Output P50/P80/P95 dates, a histogram and the key assumptions. The same engine powers the **what-if simulator** with modified inputs.
- Include a **backtest** script that replays history at past cut-off dates and reports the P80 hit-rate.

### 7.4 Anomaly Detection
- Per team and metric: rolling z-score (28-day window, |z| > 2.5) **and** Isolation Forest on the multivariate daily vector. Merge the results, deduplicate, and generate an explanation string. Persist to `anomalies`.

### 7.5 Theme Clustering and Opportunity Scoring
- Embed feedback, cluster it with HDBSCAN (falling back to KMeans with the silhouette-chosen k), and label each cluster with the LLM (or with keywords via c-TF-IDF in demo mode).
- Opportunity score = f(volume, recency-weighted growth, sentiment severity, segment value, strategic fit with objectives via embedding similarity), with a transparent breakdown.

### 7.6 Delegation Ranker
- Score = w1·skill_match (cosine between the task's required-skill vector, inferred from text and labels, and the person's skill vector, weighted by level) + w2·availability (1 − utilisation, clipped) + w3·throughput_on_similar (historical cycle time on similar items) + w4·growth_alignment + w5·context_continuity (worked on the same epic) − penalty(over-allocation, PTO overlap).
- Default weights live in config. **Preference learning (7.7) adjusts the weights per TPM.** Always return the factor breakdown and a one-sentence explanation. Never use protected attributes; add a test asserting that the feature set excludes them.

### 7.7 Preference Model (the "twin" learning loop)
- Log every suggestion response with its context features.
- Train a per-user logistic re-ranker (with a global prior for cold start) that predicts the acceptance probability of each suggestion type and its features. Use it to (a) rank briefing items and suggestions and (b) nudge delegation weights (bounded ±30% of defaults).
- Show "Twin learning" stats in Settings: suggestions seen, acceptance rate by type, and how the weights have shifted.
- Use edit diffs on status reports to append style examples to the persona (max 10, most recent).

### 7.8 Program Health Score
`health = 0.30·schedule + 0.20·scope + 0.20·quality + 0.15·dependencies + 0.15·team` (weights per program, configurable).
- **schedule:** P80 vs target date (on time = 100, decreasing linearly to 0 at 30 days late)
- **scope:** scope-creep rate over the last 2 sprints
- **quality:** bug inflow and reopen rate vs baseline
- **dependencies:** count and risk of open upstream blockers on the critical path
- **team:** utilisation balance (std dev) and team sentiment index

Persist a daily snapshot for the trend line. Return drivers.

### 7.9 Scheduling (ARQ worker)
- Every 15 minutes: connector sync (mock emits small realistic changes when `DEMO_LIVE_TICKS=true`)
- Hourly: risk scoring, anomaly detection, health snapshot, nudge job
- Daily at 07:30 in the user's timezone: briefing generation + notification
- Nightly: retrain models, backtest forecaster, recompute themes

---

## 8. Agent system (`twinpm/agents/`)

### 8.0 Framework decision: LangGraph (record as `docs/adr/0002-agent-framework-langgraph.md`)

Use **LangGraph** for every multi-step agent workflow. Rationale for the ADR:
- **Human-in-the-loop is built in:** LangGraph's `interrupt()` pauses a graph mid-run and resumes it later from the same point. That maps directly onto TwinPM's L3 "Act with approval" level.
- **Durable state:** checkpoints are stored in our existing PostgreSQL (`AsyncPostgresSaver`), so an approval can arrive hours later, even after a server restart, and the run continues.
- **Explicit control flow:** a supervisor graph with specialist subgraphs gives deterministic routing, retries, per-node timeouts and loops. Enterprises can inspect and test it.
- **Streaming:** `astream_events` / `stream_mode` maps cleanly onto our SSE agent-trace events.
- **Model-agnostic:** it works with Claude through `ChatAnthropic`, and the same graph can run with a fake chat model for demo mode.
- **Alternatives considered:** Google ADK (strong, and it supports Claude, but it fits best with Gemini and Google Cloud Agent Engine, which is not our stack), CrewAI (less control over state and approvals), and the raw Anthropic SDK with a custom loop (more code to build persistence and HITL ourselves). Record these in the ADR.

**Rules for using LangGraph:**
- Pin the exact versions of `langgraph`, `langchain-core`, `langchain-anthropic`, `langgraph-checkpoint-postgres` and `langchain-mcp-adapters` in `pyproject.toml`. Read the installed version's docs and API rather than relying on memory, because LangGraph APIs change between minor versions.
- Agent code lives in `twinpm/agents/graphs/`. Each graph has a typed state (`TypedDict` or Pydantic), lives in its own module, and is unit tested by invoking it with the fake model.
- The **policy engine and Action Executor stay plain, deterministic Python** outside the LLM. Graph nodes call them; the LLM never decides permissions.
- Do not use LangGraph Platform/Cloud. Self-host the graphs inside the FastAPI app and the ARQ worker.

### 8.1 Architecture
- A **Supervisor graph** (LangGraph `StateGraph`) is the Orchestrator. It receives the user request plus context (persona, autonomy policy, current program, conversation memory), plans, routes to specialist agents, loops until the plan is complete, and composes the final, grounded answer.
- **Specialist agents** are compiled LangGraph subgraphs (a ReAct-style agent node + tool node, built with the prebuilt agent helper or a hand-built graph, whichever the installed version recommends). Each has its own system prompt (in `agents/prompts/*.md`, versioned with a `prompt_version` string), its own tool allow-list and a structured output schema.
- **Shared graph state** includes: `messages`, `org_id`, `user_id`, `program_id`, `persona`, `plan`, `agent_trace[]`, `citations[]`, `proposed_actions[]` and `pending_approval`.
- **Graph shape:** `load_context` → `supervisor` → (`strategy` | `planner` | `delegation` | `risk` | `comms` | `insights`)* → `policy_gate` → [`interrupt` for L3 approval | `execute` for L4 | `record_suggestion` for L2] → `compose_answer` → `validate_citations` → END.
- **Approvals via `interrupt()`:** at `policy_gate`, actions needing L3 create a `suggestions` row and call `interrupt({suggestion_id, summary, explanation})`. The SSE stream emits `approval_required`. When the user responds through `POST /suggestions/{id}/respond`, the API resumes the same thread (`thread_id` = conversation ID) with `Command(resume={...})`, and the graph executes, edits or skips the action, then finishes its answer.
- **Background graphs** (run by the ARQ worker, not chat): `briefing_graph` (daily morning briefing), `nudge_graph` (stalled-item follow-ups) and `risk_review_graph` (hourly risk register upkeep). They use the same tools and policy gate.
- **Checkpointing:** `AsyncPostgresSaver` in the main Postgres (separate schema `langgraph`), with a retention job that prunes checkpoints older than 30 days.
- **Streaming:** map LangGraph stream events to the SSE events in Section 6.10 (`agent_started`, `tool_call`, `tool_result`, `token`, `citation`, `approval_required`, `suggestion_created`, `done`, `error`).
- **Reliability:** per-node timeouts, retry policies on LLM/tool nodes, a recursion limit, and an error-handler node that returns a graceful message plus the partial trace.

| Agent | Responsibilities | Tools |
|---|---|---|
| Strategy | Feedback synthesis, opportunity scoring, PRD/OKR drafts, devil's advocate | `search_feedback`, `get_themes`, `score_opportunity`, `get_objectives`, `rag_search`, `draft_document` |
| Planner | Epic breakdown, estimates, sprint plans, roadmap scenarios | `get_epic`, `estimate_effort`, `get_capacity`, `simulate_scenario`, `get_roadmap` |
| Delegation | Owner ranking, rebalancing, follow-ups | `get_workload`, `rank_candidates`, `propose_reassignment`, `find_stalled_items`, `propose_nudge` |
| Risk | Risk scoring, cascade analysis, register upkeep | `get_risky_items`, `explain_prediction`, `get_dependency_graph`, `impact_analysis`, `run_forecast`, `propose_risk_update` |
| Comms | Status reports, meeting prep, extraction, decision log | `get_program_snapshot`, `get_health`, `rag_search`, `search_decisions`, `extract_actions`, `propose_status_report`, `log_decision` |
| Insights | Metrics Q&A, anomalies, team health | `query_metric` (parameterised), `get_anomalies`, `get_team_health` |

### 8.2 Tools
- Every tool is a Python function with a **Pydantic input schema**, registered as a LangChain/LangGraph tool (`@tool` with `args_schema`). Tools receive tenant context (org_id, user_id) from graph state or injected config, **never from LLM arguments**. Tools **read** freely within the tenant. Tools that **write** never write directly: they create `suggestions`, which the Action Executor runs according to the autonomy policy.
- Each tool result returns `{data, citations:[{type, id, label}]}`.

### 8.3 Autonomy policy engine
- Levels: **L1 Observe** (notify only), **L2 Suggest** (pending suggestion), **L3 Act with approval** (approval card; one click executes), **L4 Autonomous** (execute immediately, log, notify, undo available).
- Defaults by action type: alerts/briefings L4; nudges L4 (opt-in, default L3); status_report L3; reassign L3; create_task L3; risk_update L3; roadmap_change L2.
- The engine is **deterministic code**, not LLM judgement. The LLM can never escalate its own permissions. Test this.

### 8.4 Grounding and guardrails
- System prompts require citing entity IDs for every factual claim. Post-process the output: validate that cited IDs exist in the tenant, strip any that don't, and add a warning if a claim has no citation.
- If data is missing, the agent must say so and must not guess.
- **PII redaction** before LLM calls (emails, phone numbers) via a redaction utility, re-hydrated in the output where safe.
- **Prompt-injection defence:** treat document and feedback content as untrusted data, wrap it in clear delimiters, and tell the model never to follow instructions found inside it. Add tests with injected documents.
- Cap output tokens; set timeouts and retries with exponential backoff; use a circuit breaker for the provider.

### 8.5 Persona injection
Each agent's system prompt includes a compact persona block: the TPM's name, top priorities, tone, risk tolerance, escalation rules, and 2–3 style examples (for Comms).

### 8.6 Memory
- Short-term: the conversation's messages (summarise them when the thread exceeds a token budget).
- Long-term: decisions, persona and preference events, retrieved when relevant.

### 8.7 RAG (`twinpm/rag/`)
- Chunk markdown about every 500 tokens with 80-token overlap, respecting headings. Embed locally with sentence-transformers (384-dim) into pgvector.
- **Hybrid retrieval:** vector top-k + Postgres full-text (`tsvector`) + graph neighbourhood boost (entities mentioned in the query, and their linked docs and decisions), merged with Reciprocal Rank Fusion.
- Return chunks with document IDs for citations.

### 8.8 LLM provider abstraction and demo mode
- A `get_chat_model(purpose)` factory returns either `ChatAnthropic` or **`DemoChatModel`**, a custom LangChain `BaseChatModel` subclass. The LangGraph graphs therefore run unchanged in both modes.
- `DemoChatModel` makes deterministic tool-call decisions based on intent rules, then writes templated answers from the real tool results.
- `DemoProvider` / `DemoChatModel` is used automatically when there is no API key, or when `DEMO_MODE=true`. It produces **deterministic, high-quality, templated outputs** built from real computed data (health, risks, forecasts, candidates) so every screen and the full demo flow work offline. It also simulates streaming and tool-call events.
- Record every LLM call in `llm_calls` with token and cost telemetry (via a LangChain callback handler). Show a small "AI usage" panel in admin settings.

### 8.9 MCP (Model Context Protocol) interoperability
- **TwinPM as an MCP server:** expose read-only tools (program health, briefing, risks, forecast, decision search) and the suggestion-creating tools through an MCP server at `/mcp` (streamable HTTP), authenticated with per-user API tokens and the same RBAC and policy gate. Enterprise users can then ask Claude or other MCP clients about their program. Priority P1.
- **TwinPM as an MCP client:** use `langchain-mcp-adapters` so live connectors can later be swapped for vendor MCP servers (e.g. Jira, GitHub, Slack) without changing agent code. Build the adapter seam and one test with a local mock MCP server.

### 8.10 Agent evaluation
- `apps/api/twinpm/agents/evals/`: a golden set of about 25 scenarios (questions plus the expected tools called, required citations and forbidden behaviours).
- Run the evals against `DemoChatModel` in CI, and against Claude with `make eval` when an API key is present. Report tool-selection accuracy, the citation validity rate and policy-violation count (must be 0).

---

## 9. Frontend (apps/web)

### 9.1 Design system
- Clean, premium enterprise look. Primary: deep navy `#14213D`. Accent: teal `#0F766E`. Warning: amber `#D97706`. Danger: `#DC2626`. Success: `#16A34A`. Neutral grays. Full **dark mode**.
- Font: Inter (via `next/font`). 8px spacing scale, rounded-xl cards, subtle shadows.
- **Consistent components:** `HealthGauge`, `RiskBadge` (0–1 to Low/Med/High/Critical), `ForecastBand` (P50/P80/P95), `DriverList` (SHAP factors as horizontal bars), `CitationChip` (opens a side panel with the source entity), `SuggestionCard` (title, explanation, drivers, citations, autonomy level, Accept / Edit / Reject / Why?), `ApprovalCard`, `ModelCardDrawer`, `EmptyState`, `ErrorState`, `SkeletonLoader`.
- Accessibility: WCAG 2.1 AA, keyboard navigable, focus rings, aria labels, colour never used as the only signal.

### 9.2 App shell
- Left sidebar: Command Center, Strategy, Roadmap, Delegation, Risk Radar, Comms Studio, Insights, Settings.
- Top bar: program switcher, global search (Cmd/Ctrl+K command palette: navigate, search entities, run actions), notifications bell, user menu, theme toggle, and a **"Demo mode"** indicator when active.
- **Ask the Twin**: a persistent right-side drawer, toggled by a floating button or Cmd/Ctrl+J. It is available on every page and context-aware (it knows the current page and the selected entity).
- **Audit log drawer** reachable from every suggestion and entity.
- Live updates via SSE `/events/stream` (TanStack Query invalidation).

### 9.3 Screens

**Login:** email/password, demo users listed on the login page when `DEMO_MODE=true`.

**Command Center (home):**
- Large Health Gauge (score, trend sparkline, 5 sub-score chips with drivers on hover).
- **Morning Briefing**: 3 ranked cards, each with "Why?" (drivers and citations) and a primary action button (e.g. *See options*).
- Launch forecast card: P50/P80/P95 vs target, with a histogram on expand and a "Run forecast" button.
- Pending suggestions list (approval cards).
- Activity feed (twin vs user actions, with twin actions marked with a twin icon).
- Top risks mini-table, and an anomalies strip.

**Strategy:**
- Theme bubbles/treemap sized by volume and coloured by sentiment, with an opportunity score table (sortable, with breakdown).
- Theme detail: representative quotes, trend over time, linked objectives.
- "Draft PRD from this theme" (streamed into an editor, saved as a document), plus a "Devil's advocate" panel.
- OKR drafting panel.

**Roadmap:**
- Now / Next / Later columns with initiative cards (RICE/WSJF badges, dependency count, risk), drag-and-drop between buckets (creates an audit entry; at L2 it creates a suggestion instead).
- **What-if Simulator** panel: add/remove scope, change team capacity (slider), reassign, shift dates. Shows baseline vs scenario forecast bands side by side, delta days, risk delta and affected epics. Save and compare up to 3 scenarios.
- Epic breakdown dialog: proposed stories with acceptance criteria and estimates, then "Create as suggestions".

**Delegation Board:**
- Workload heatmap (people × weeks, utilisation colour scale), with overload highlighted.
- Team columns with people cards (utilisation ring, skills, growth goals).
- Select an unassigned or at-risk item to see ranked candidates with factor bars and an explanation.
- **"Rebalance"** button: shows a proposed plan (from → to), forecast impact and an approve-all or per-item approval.
- Stalled items list with nudge status.

**Risk Radar:**
- **Dependency graph** (React Flow): nodes coloured by team, sized by scope, bordered by risk; the critical path is highlighted in red with animated edges; click a node for details and drivers. Includes the "Simulate slip" control (N days → cascade highlight + new forecast).
- At-risk items table: probability, drivers, owner and due date, with a filter.
- Risk register table: CRUD, with model-sourced risks marked.
- Model card drawer: metrics, features, version, last trained.

**Comms Studio:**
- Status report generator: audience tabs (Executive / Engineering / Customer), period picker, streamed draft into a rich-text editor with RAG badge, citations and "Approve & send" (in the MVP, sending = saved and posted to the mock Slack channel feed). Edits are captured for style learning.
- Transcript extractor: paste or upload a transcript, see the extracted decisions and action items with owners, then approve to create them.
- Decision log: searchable list, with detail showing context, options, rationale, participants and the source doc.
- Meeting prep generator.

**Insights:**
- Metric explorer (team × metric × date range) with anomaly markers.
- Team health panel (team-level only, with a privacy notice).
- "Ask about your metrics" box (NL to chart + narrative).

**Settings:**
- **Persona**: priorities (drag to order), tone, risk tolerance, escalation rules and style examples.
- **Autonomy**: a table of action types with a 4-step level control and a description of each level.
- **Twin learning**: acceptance stats and weight shifts.
- **Integrations**: provider cards with Mock/Live mode, last sync time and a "Sync now" button.
- **Members & roles** (admin), and **AI usage** (admin).

### 9.4 Frontend engineering
- Server components for layout; client components for interactivity. TanStack Query for all server state, with optimistic updates on suggestion responses.
- A central `apiClient` generated from OpenAPI, with an auth refresh interceptor.
- Error boundaries per route; skeleton loaders everywhere; empty states with helpful CTAs.
- Responsive down to a 1280px laptop (primary), usable on a tablet.

---

## 10. Connectors (`twinpm/connectors/`)

- Define interfaces: `WorkTrackerConnector` (Jira-like), `CodeHostConnector` (GitHub-like), `ChatConnector` (Slack-like), `CalendarConnector` and `DocsConnector`, with typed DTOs and a `sync(since)` method that upserts into the domain tables idempotently (keyed by `external_ref`).
- **Mock implementations** read from the seed fixtures and, when `DEMO_LIVE_TICKS=true`, emit small realistic changes on each sync (status moves, PR reviews, new comments), so the dashboard visibly changes during the demo.
- **Live adapter skeletons** for Jira Cloud (REST v3), GitHub (REST/GraphQL) and Slack (Web API) must be implemented with real request code, pagination and rate-limit handling, behind feature flags. They are unit tested with recorded HTTP fixtures (`respx`). They do not need live credentials to pass tests.
- Encrypt integration secrets at rest.

---

## 11. Security, privacy and compliance

- **Authentication:** Argon2 password hashing; JWT access tokens (15 min) and refresh tokens (7 days, rotation, reuse detection) in httpOnly, Secure, SameSite=Lax cookies; CSRF protection for cookie-auth mutations.
- **Authorisation:** RBAC decorators and dependencies on every route, plus tenant scoping in repositories. Executives get read-only access plus comms approval; members see their own items and team-level views.
- **Input validation** everywhere (Pydantic / zod), output encoding, strict CORS, security headers (CSP, HSTS, X-Frame-Options), and rate limiting on auth and AI endpoints.
- **Audit log** is append-only and covers every state change and every twin action.
- **Privacy:** no individual productivity scores; team signals aggregated with a minimum group size of 5; PII redaction for LLM calls; data retention settings per org (documented).
- **Responsible AI:** AI-generated content is labelled in the UI ("Drafted by Priya's twin"); explanations everywhere; the delegation fairness test excludes protected attributes; a distribution monitor shows assignment counts per person.
- `docs/SECURITY.md` must cover the threat model (STRIDE summary), data flows, secrets handling and an incident process.

---

## 12. Testing and quality gates

- **Backend:** unit tests for services, ML feature builders, the Monte Carlo engine (deterministic with a seed), the policy engine, the Action Executor, RAG retrieval and the citation validator; integration tests for every router (testcontainers Postgres); a multi-tenant isolation test; and prompt-injection tests against the DemoProvider pipeline. Coverage **≥ 80%** for `services/`, `ml/`, `agents/policy`.
- **ML tests:** the trained delay model on seeded data reaches ROC-AUC ≥ 0.80; the storyline items score > 0.65; the forecaster's P80 for launch moves by ≥ 7 days because of the Payments slip; the rebalance scenario recovers ≥ 50% of the slip.
- **Frontend:** Vitest component tests for the core components (SuggestionCard, HealthGauge, DriverList, ForecastBand).
- **E2E (Playwright):** log in as Priya → Command Center shows the Payments briefing item → open "See options" → run scenarios → approve the rebalance → audit log shows the entries → generate an executive status report → approve it. This E2E test **must pass in demo mode** in CI.
- **CI** (`.github/workflows/ci.yml`): install, lint, type-check, backend tests, frontend tests, build the Docker images, and Playwright against docker-compose in demo mode.

---

## 13. Demo flow (must work end to end, offline in demo mode)

Write this to `docs/DEMO_SCRIPT.md` and make sure the product supports every beat:

1. **0:00 Hook:** log in as Priya. Command Center: health **72 (↓6)**, Dependencies amber.
2. **0:30 Briefing #1:** "Payments API likely to slip ~9 days; 3 launch epics depend on it. Launch P80 moves from *X* to *Y*."
3. **1:00 Why?:** SHAP drivers (review latency 2.3x, owner at 110%, 2 reopens). Open the Risk Radar: the critical path glows red; "Simulate slip 9 days" shows the cascade.
4. **2:00 Ask the Twin:** "What should I do?" A streamed answer shows the agent trace (Risk → Planner → Delegation) and 3 scenarios with forecast deltas.
5. **2:45 Decide:** choose Rebalance. Delegation shows Karan and Li Wei with factor explanations. Approve (L3). Tasks are reassigned, notifications are sent, the risk register is updated, and the forecast refreshes to near target.
6. **3:30 Communicate:** Comms Studio → Executive update drafted in Priya's voice, with citations. Edit one line, then approve. The edit is captured for style learning.
7. **4:15 Trust:** the audit log shows every action; Settings → Autonomy dial; Twin learning stats.
8. **4:45 Close:** the positioning line.

Add a hidden **"Reset demo"** admin action that re-seeds the org in under 10 seconds.

---

## 14. Build phases and verification gates

Track these in `docs/PLAN.md`. **Do not proceed past a gate that fails.**

**Phase 1: Foundations**
Monorepo, tooling, docker-compose (Postgres + pgvector, Redis), FastAPI skeleton with config, logging, telemetry, error envelope, health endpoints; Next.js shell with design system, theme, and layout; CI pipeline.
*Gate:* `make dev` starts everything; `/readyz` is green; the web app renders the shell; CI is green.

**Phase 2: Data and auth**
SQLAlchemy models + Alembic migrations for Section 4, repository layer with tenancy, auth + RBAC, audit log with append-only enforcement, OpenAPI → generated TS client, login flow.
*Gate:* migrations apply cleanly; the tenant isolation test passes; login works end to end.

**Phase 3: Synthetic data**
Full generator per Section 5, `make seed`, summary output, `docs/DATA_DICTIONARY.md`.
*Gate:* the seed is deterministic (two runs produce identical hashes); the storyline conditions are verified by assertions in a test.

**Phase 4: ML platform**
Features, the training pipelines for 7.1–7.8, the registry, inference APIs, SHAP, Monte Carlo + backtest, `make train`, `docs/ML.md`.
*Gate:* the ML tests in Section 12 pass.

**Phase 5: Core APIs**
Program/health/briefing (initial ranking rules before the agents), roadmap, scenarios, delegation, risk, dependencies, forecasts, insights, suggestions + Action Executor + policy engine + undo, SSE events.
*Gate:* router integration tests pass; the OpenAPI docs are complete.

**Phase 6: LLM, agents (LangGraph) and RAG**
Model factory (`ChatAnthropic` / `DemoChatModel`), LangChain tools, specialist subgraphs, the supervisor graph with `policy_gate` and `interrupt()` approvals, `AsyncPostgresSaver` checkpointing, background graphs, stream-to-SSE mapping, citations validator, guardrails, RAG indexing + hybrid retrieval, chat SSE, comms/strategy generation endpoints, MCP server (P1) and client seam, agent evals, ADR 0002, `docs/AGENTS.md` (with a Mermaid diagram of every graph).
*Gate:* graph unit tests and evals pass in demo mode. An approval interrupt survives an API restart and resumes correctly. With an API key, a manual smoke test of chat and the status report works.

**Phase 7: Frontend screens**
All the screens in Section 9.3, with live updates, the command palette, the Ask the Twin drawer and approval flows.
*Gate:* every screen loads with seeded data, with no console errors; Vitest passes; Lighthouse accessibility score ≥ 90 on the Command Center.

**Phase 8: Workers and connectors**
ARQ jobs and schedules, mock connectors with live ticks, live adapter skeletons with fixture tests.
*Gate:* the worker runs jobs; the dashboard updates when ticks arrive.

**Phase 9: Hardening**
Security headers, rate limits, PII redaction, prompt-injection tests, error/empty states, performance checks (dashboard API p95 < 300ms on seed data; Monte Carlo < 1s), Helm chart, `docs/SECURITY.md`, `docs/ARCHITECTURE.md` (with Mermaid diagrams), ADRs.
*Gate:* all tests pass; `docker compose up` from a clean clone works.

**Phase 10: Demo polish**
Run the Playwright demo E2E, rehearse the demo flow, write `docs/DEMO_SCRIPT.md`, and add the Reset Demo action. Polish copy, loading states and micro-interactions. Write a README with a one-command quick start, screenshots placeholders list, architecture overview, and a "how this maps to enterprise needs" section.
*Gate:* the E2E demo test passes in CI; a fresh clone + `make demo` gets to a working login in under 5 minutes.

---

## 15. Definition of done

- [ ] `make demo` brings up the full stack, seeds the data, trains the models and prints the login URL and demo credentials.
- [ ] Every screen in Section 9.3 works with seeded data, in both light and dark mode.
- [ ] The full demo flow in Section 13 works offline (DemoProvider) **and** with a real Claude API key.
- [ ] Every prediction shows its drivers; every AI answer shows citations; every twin action appears in the audit log and respects the autonomy policy.
- [ ] Backend: ruff + mypy strict are clean, and the coverage targets are met. Frontend: ESLint + tsc are clean, and Vitest passes. Playwright E2E passes.
- [ ] Docs are complete: README, ARCHITECTURE, API, ML, AGENTS, SECURITY, DATA_DICTIONARY, DEMO_SCRIPT, ROADMAP and ADRs.
- [ ] No secrets in the repo; `.env.example` is complete and commented.

---

## 16. Out of scope for this build (record in ROADMAP.md)

Production SSO (only the interface is built), billing, mobile apps, a Slack bot surface, multi-twin negotiation between TPMs, a playbook marketplace, a Neo4j migration, fine-tuned models.

**Start now with Phase 1. Create `docs/PLAN.md` first.**
