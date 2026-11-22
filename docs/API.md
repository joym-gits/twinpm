# API

The FastAPI app publishes OpenAPI at `/openapi.json` and interactive docs at `/docs`. The
TypeScript client in `packages/api-client` is generated from it (`make openapi`).

Conventions: everything under `/api/v1` is scoped to the signed-in user's organisation and
RBAC-checked. Errors use `{error: {code, message, details, request_id}}`. Cookie-authenticated
mutations need the `x-csrf-token` header (double-submit). API tokens (`Authorization: Bearer
tpm_...`) skip CSRF. AI routes are rate-limited per user. Streaming routes return
`text/event-stream` with events `agent_started`, `tool_call`, `tool_result`, `token`,
`citation`, `approval_required`, `suggestion_created`, `done`, `error`.

## admin

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/admin/ai-usage` | Ai Usage |

## auth

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/auth/demo-users` | Lists the seeded demo users. Empty unless demo mode is active. |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/logout` | Logout |
| GET | `/api/v1/auth/me` | Me |
| POST | `/api/v1/auth/refresh` | Refresh |

## catalog

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/comms/channel-feed` | Channel Feed |
| GET | `/api/v1/entities/{entity_type}/{entity_id}` | Entity |
| GET | `/api/v1/epics` | Epics |
| GET | `/api/v1/milestones` | Milestones |
| GET | `/api/v1/ml/models` | Model Cards |
| GET | `/api/v1/people` | People |
| GET | `/api/v1/teams` | Teams |
| GET | `/api/v1/work-items` | Work Items |

## chat

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/chat/conversations` | List Conversations |
| POST | `/api/v1/chat/conversations` | Create |
| GET | `/api/v1/chat/conversations/{conversation_id}` | Get |
| POST | `/api/v1/chat/conversations/{conversation_id}/messages` | SSE: agent_started, tool_call, tool_result, token, citation, approval_required, |

## comms

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/comms/extract` | Decisions and action items from a document or pasted transcript (as suggestions). |
| POST | `/api/v1/comms/meeting-prep` | Meeting Prep |
| POST | `/api/v1/comms/status-report` | Streamed status report in the persona's tone; ends with a status_report suggestion. |
| GET | `/api/v1/decisions` | Decisions |
| POST | `/api/v1/decisions` | Create Decision |
| GET | `/api/v1/documents` | Documents |
| GET | `/api/v1/documents/{document_id}` | Document |

## delegation

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/delegation/candidates/{work_item_id}` | Candidates |
| POST | `/api/v1/delegation/nudges/run` | Run Nudges |
| POST | `/api/v1/delegation/rebalance` | Plan reassignments off the critical path; each move becomes a suggestion. |
| GET | `/api/v1/delegation/workload` | Per-person utilisation (team-level work signals only), weekly heatmap and overload flags. |

## events

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/events/stream` | `event: domain` messages ({kind, data, at}) for the caller's organisation. |

## insights

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/insights/anomalies` | Anomalies |
| POST | `/api/v1/insights/ask` | Natural-language metric question answered through the parameterised metric tool. |
| GET | `/api/v1/insights/metrics` | Metrics |
| GET | `/api/v1/insights/team-health` | Team-level aggregates only. Teams under 5 people are suppressed. |

## integrations

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/integrations` | List Integrations |
| PATCH | `/api/v1/integrations/{integration_id}` | Switch mock/live and store config. Secrets are Fernet-encrypted at rest. |
| POST | `/api/v1/integrations/{integration_id}/sync` | Sync |

## org

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/members` | List Members |
| POST | `/api/v1/members` | Create Member |
| PATCH | `/api/v1/members/{user_id}` | Update Member |
| GET | `/api/v1/org` | Get Org |
| PATCH | `/api/v1/org/settings` | Update Org Settings |

## planning

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/forecasts/{milestone_id}` | Get Forecast |
| POST | `/api/v1/forecasts/{milestone_id}/run` | Run Forecast |
| PATCH | `/api/v1/initiatives/{initiative_id}` | Move an initiative between buckets or rescore it. Every change is audited. |
| POST | `/api/v1/planning/breakdown` | Propose stories with acceptance criteria and ML estimates (as create_task suggestions). |
| POST | `/api/v1/planning/sprint-plan` | Sprint Plan |
| GET | `/api/v1/roadmap` | Get Roadmap |
| GET | `/api/v1/scenarios` | List Scenarios |
| POST | `/api/v1/scenarios` | Save Scenario |
| POST | `/api/v1/scenarios/simulate` | Run the Monte Carlo forecast with what-if changes (10,000 simulations). |

## platform

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/api-tokens` | List Tokens |
| POST | `/api/v1/api-tokens` | The token is shown once. Only its SHA-256 digest is stored. |
| DELETE | `/api/v1/api-tokens/{token_id}` | Revoke |
| GET | `/healthz` | Healthz |
| GET | `/readyz` | Readyz |

## program

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/programs` | List Programs |
| GET | `/api/v1/programs/{program_id}` | Get Program |
| GET | `/api/v1/programs/{program_id}/activity` | Program Activity |
| GET | `/api/v1/programs/{program_id}/briefing` | Top three attention items, ranked by severity and the TPM's learned preferences. |
| GET | `/api/v1/programs/{program_id}/health` | Health score, five sub-scores, a 30-day trend and the drivers behind it. |

## risk

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/dependencies/graph` | Epics and dependent items with team, status, risk, critical-path flags and slack. |
| POST | `/api/v1/dependencies/impact` | Cascade of an N-day slip on an epic or work item, with the new launch forecast. |
| GET | `/api/v1/risk/register` | Register |
| POST | `/api/v1/risk/register` | Create Risk |
| PATCH | `/api/v1/risk/register/{risk_id}` | Update Risk |
| GET | `/api/v1/risk/work-items` | Open items with delay probability and SHAP drivers, highest risk first. |

## strategy

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/feedback` | Feedback |
| POST | `/api/v1/feedback/import` | Import Feedback |
| POST | `/api/v1/strategy/devils-advocate` | Devils Advocate |
| POST | `/api/v1/strategy/okrs/draft` | Okrs |
| POST | `/api/v1/strategy/prd` | Streamed PRD markdown, saved as a document. |
| GET | `/api/v1/strategy/themes` | Themes |
| POST | `/api/v1/strategy/themes/recompute` | Re-cluster feedback. Enqueued on the worker when available, else run inline. |

## twin

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/audit` | Get Audit |
| GET | `/api/v1/autonomy-policy` | Get Autonomy |
| PUT | `/api/v1/autonomy-policy` | Put Autonomy |
| GET | `/api/v1/notifications` | Notifications |
| POST | `/api/v1/notifications/{notification_id}/read` | Mark Read |
| GET | `/api/v1/persona` | Get Persona |
| PUT | `/api/v1/persona` | Put Persona |
| GET | `/api/v1/suggestions` | List Suggestions |
| GET | `/api/v1/suggestions/{suggestion_id}` | Get Suggestion |
| POST | `/api/v1/suggestions/{suggestion_id}/respond` | Accept, edit or reject. Accepting runs the Action Executor and teaches the twin. |
| POST | `/api/v1/suggestions/{suggestion_id}/undo` | Reverse an executed, reversible action within 24 hours. |
| GET | `/api/v1/twin/learning` | Learning |

## MCP

`/mcp` (streamable HTTP, bearer API token): `program_health`, `briefing`, `risky_items`,
`forecast`, `search_decisions`, `propose_reassignment`. See `docs/AGENTS.md`.
