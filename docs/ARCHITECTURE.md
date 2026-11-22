# Architecture

```mermaid
flowchart LR
    subgraph Browser
      UI[Next.js app<br/>TanStack Query, SSE]
    end
    subgraph Web[web: Next.js 15]
      RW[/api rewrites/]
    end
    subgraph API[api: FastAPI]
      R[Routers /api/v1] --> S[Services]
      S --> AE[Action Executor<br/>+ policy engine]
      S --> ML[ML: delay, effort,<br/>Monte Carlo, anomalies,<br/>themes, delegation, health]
      S --> AG[LangGraph agents<br/>supervisor + specialists]
      AG --> T[Tools] --> S
      AG --> LLM{{ChatAnthropic /<br/>DemoChatModel}}
      MCP[/MCP server /mcp/] --> T
      EV[SSE /events/stream]
    end
    subgraph Worker[worker: ARQ]
      J[Jobs: sync, hourly review,<br/>briefing, nightly retrain]
    end
    PG[(Postgres 16<br/>+ pgvector<br/>+ langgraph schema)]
    RD[(Redis 7)]
    EXT[Jira / GitHub / Slack<br/>mock or live]
    ANT[Anthropic API]

    UI --> RW --> R
    UI -. SSE .-> EV
    S --> PG
    AG --> PG
    AE --> RD
    EV --> RD
    J --> S
    J --> EXT
    J --> RD
    LLM -. when key set .-> ANT
```

## Layers

- **Routers** (`api/v1`) are thin: parse, check RBAC through dependencies, call a service.
- **Services** (`services/`) hold business logic and never import FastAPI. All program-state
  writes go through `services/actions.py` (the Action Executor), which validates, checks RBAC
  and the autonomy policy, applies the change, audits it and publishes a domain event.
- **Repository** (`db/repository.py`) scopes every query to the tenant.
- **ML** (`ml/`) is pure functions over `ProgramData` frames; `services/ml_jobs.py` persists.
- **Agents** (`agents/`) are LangGraph graphs (see `docs/AGENTS.md`).
- **Connectors** (`connectors/`) implement typed interfaces with mock and live adapters.

## Request lifecycle: approving a rebalance

```mermaid
sequenceDiagram
    participant U as TPM (browser)
    participant A as FastAPI
    participant X as Action Executor
    participant P as Postgres
    participant R as Redis
    participant G as LangGraph runtime
    U->>A: POST /suggestions/{id}/respond {accept}
    A->>X: execute(reassign, approved=True)
    X->>P: update work item, insert audit row, notification
    X->>R: publish action.reassign
    A->>P: preference_event (learning signal)
    A-->>U: 200 SuggestionOut
    R-->>U: SSE domain event → refetch
    A->>G: resume thread when no approvals pending
    G->>P: confirm message in conversation
```

## Deployment

- Local: `make dev` (infra in Docker, processes with reload) or `make up` / `make demo`
  (everything in Docker Compose).
- Kubernetes: `deploy/helm/twinpm` (API with migration init container, worker, web, shared
  ReadWriteMany volume for the model registry, ingress with SSE buffering off, probes and
  resource limits; `values-prod.yaml` for production).

## Observability

OpenTelemetry traces (FastAPI, SQLAlchemy, httpx) export when `OTEL_EXPORTER_OTLP_ENDPOINT` is
set; structlog JSON logs carry request IDs; Prometheus metrics at `/metrics`
(`twinpm_http_*`, `twinpm_llm_*`); LLM telemetry in `llm_calls` with an admin view.
