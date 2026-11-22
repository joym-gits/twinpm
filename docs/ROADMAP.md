# Roadmap

Out of scope for this build (Section 16 of the build spec) and known follow-ups.

## Out of scope
- Production SSO (the `AuthProvider` seam is email/password + JWT today; OIDC is next).
- Billing and plans enforcement.
- Mobile apps.
- A Slack bot surface (Slack is used for outbound posts and history only).
- Multi-twin negotiation between TPMs.
- A playbook marketplace.
- Neo4j migration (graph analytics run on Postgres + NetworkX).
- Fine-tuned models.

## Follow-ups found during the build
- **Forecast scope growth**: the backtest shows the forecaster is early on epics whose scope
  grows after the cut-off (P80 hit-rate 0.11). Model expected scope growth from history.
- **Per-tenant models**: the registry holds one global model per type.
- **Delay model robustness**: AUC is 0.83 on seed 42 but lower on other seeds; add more
  observable causes and evaluate across seeds.
- **Response models for loose dicts**: a few endpoints return untyped dicts (meeting prep,
  devil's advocate, OKR draft, channel feed, some nested fields); give them Pydantic models so
  the generated client types them.
- **Program-scoped catalog**: `/teams`, `/people`, `/epics`, `/work-items` are org-scoped.
- **Cache invalidation across processes**: the in-process ProgramData cache relies on a 60-second
  TTL for changes made by the worker; subscribe to domain events instead.
- **Live Slack posting from the Action Executor**: status reports post to the mock channel; route
  through the live adapter when the Slack integration is live.
