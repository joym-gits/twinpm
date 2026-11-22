# Security

## Threat model (STRIDE summary)

| Threat | Where | Controls |
|---|---|---|
| **Spoofing** | Login, API tokens, MCP | Argon2id password hashes; 15-minute JWT access tokens and 7-day refresh tokens in httpOnly, SameSite=Lax cookies (Secure in prod); refresh rotation with reuse detection that revokes the whole token family; constant-time-ish failure path for unknown users; per-user API tokens stored as SHA-256 digests, shown once, revocable; login rate limit per IP+email. |
| **Tampering** | State changes, audit trail | All program writes go through one Action Executor with Pydantic payload validation; CSRF double-submit cookie for cookie-authenticated mutations; the audit log is append-only at the database level (trigger rejects UPDATE/DELETE/TRUNCATE; only a flagged whole-tenant purge may delete). |
| **Repudiation** | Twin and user actions | Every state change and twin action is audited with actor type (user/twin/system), before/after, reason, suggestion ID, request ID and IP. |
| **Information disclosure** | Multi-tenancy, LLM calls, logs | Repository layer always filters by the authenticated `org_id` (tested); team signals are aggregates only with a minimum group size of 5; emails and phone numbers are redacted before any LLM call; integration secrets are Fernet-encrypted at rest and never returned by the API; structured logs carry IDs, not payloads; security headers (CSP, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy). |
| **Denial of service** | AI endpoints, auth | Redis rate limits on auth and AI routes; LLM timeouts, retries with backoff, recursion limits and per-specialist timeouts; request body limits on uploads (5 MB CSV). |
| **Elevation of privilege** | RBAC, autonomy, prompt injection | RBAC dependencies on every route and inside the Action Executor; the autonomy policy is deterministic code and the twin can never raise its own level (tested); status reports and roadmap changes are capped at L3; document, feedback and decision text is fenced as untrusted with an explicit instruction never to follow it (tested with injected documents); tools receive tenant context from the server, never from model arguments; metric questions only use parameterised tools, never model-written SQL. |

## Data flows

1. Browser → Next.js (same origin) → FastAPI `/api/v1/*`. Cookies are first-party; the API never
   needs third-party cookies.
2. FastAPI ↔ Postgres (app data, pgvector, LangGraph checkpoints in schema `langgraph`) and
   Redis (rate limits, pub/sub events, briefing cache, mock Slack feed, ARQ queue).
3. FastAPI/worker → Anthropic API (only when `ANTHROPIC_API_KEY` is set): redacted prompts and
   fenced tool results. Every call is recorded in `llm_calls` without prompt text.
4. Worker → Jira/GitHub/Slack (only in `live` mode) with decrypted per-integration credentials.
5. MCP clients → `/mcp` with a per-user bearer token; DNS-rebinding protection limits hosts.

## Secrets handling

- Configuration comes only from the environment; `.env` files are git-ignored and
  `.env.example` holds no real secrets.
- Production secrets live in a Kubernetes Secret (`secretName` in the Helm chart), not in values.
- `FERNET_KEY` encrypts integration secrets. Rotating it requires re-entering integration
  credentials (decryption fails loudly).
- `JWT_SECRET` rotation invalidates all sessions; users sign in again.

## Privacy

- No individual productivity scores. Utilisation is a planning signal (committed points vs
  capacity) used for load balancing, shown to people with program access.
- Team health is team-level only and suppressed below 5 people.
- The delegation ranker uses work signals only; a test asserts protected attributes are never
  features. A distribution monitor shows assignment counts per person.
- Data retention: `organizations.settings.data_retention_days` (demo: 730); agent checkpoints
  are pruned after 30 days.
- AI-generated content is labelled ("Drafted by Priya's twin") throughout the UI.

## Incident process

1. **Detect**: alerts on 5xx rate, auth failures, refresh-token reuse warnings
   (`refresh_token_reuse_detected` log event), LLM error rate (`twinpm_llm_calls_total`).
2. **Contain**: revoke affected refresh-token families and API tokens; switch integrations to
   `mock`; set `DEMO_MODE=true` to cut off LLM traffic; rotate `JWT_SECRET` to force sign-out.
3. **Investigate**: the audit log (append-only) and request IDs correlate actions across logs
   and traces.
4. **Recover and review**: restore from Postgres backups if needed; write a blameless review
   within five working days; add a regression test.

Report vulnerabilities privately to the security contact for your deployment.
