# Data dictionary

Generated from the SQLAlchemy models by `python -m twinpm.data_dictionary`. Every tenant table carries `id`, `org_id`, `created_at` and `updated_at`.

## `anomalies`

Detected metric anomalies with method and explanation.

| Column | Type | Null | Notes |
|---|---|---|---|
| `team_id` | UUID | no | FK -> `teams` |
| `metric` | VARCHAR(64) | no |  |
| `date` | DATE | no |  |
| `value` | FLOAT | no |  |
| `expected` | FLOAT | no |  |
| `z_score` | FLOAT | no |  |
| `method` | VARCHAR(32) | no |  |
| `explanation` | TEXT | no |  |
| `status` | VARCHAR(16) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `api_tokens`

Hashed per-user API tokens for the MCP server and automation.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `name` | VARCHAR(120) | no |  |
| `token_hash` | VARCHAR(64) | no |  |
| `prefix` | VARCHAR(12) | no |  |
| `last_used_at` | DATETIME | yes |  |
| `revoked_at` | DATETIME | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `audit_log`

Append-only record of every state change and twin action. UPDATE, DELETE and TRUNCATE are rejected by a trigger (tenant purge is the only exception).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | BIGINT | no | PK |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `actor_type` | VARCHAR(8) | no |  |
| `actor_id` | UUID | yes |  |
| `action` | VARCHAR(64) | no |  |
| `entity_type` | VARCHAR(32) | no |  |
| `entity_id` | UUID | yes |  |
| `before` | JSONB | yes |  |
| `after` | JSONB | yes |  |
| `reason` | TEXT | yes |  |
| `suggestion_id` | UUID | yes |  |
| `request_id` | VARCHAR(64) | yes |  |
| `ip` | INET | yes |  |
| `occurred_at` | DATETIME | no |  |

## `autonomy_policies`

Per-user (optionally per-program) autonomy level 1-4 per action type.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `program_id` | UUID | yes | FK -> `programs` |
| `action_type` | VARCHAR(32) | no |  |
| `level` | INTEGER | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `conversations`

Ask the Twin threads (also the LangGraph thread id).

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `program_id` | UUID | yes | FK -> `programs` |
| `title` | VARCHAR(300) | no |  |
| `summary` | TEXT | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `decisions`

Decision log with options, rationale and participants (full-text indexed).

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `title` | VARCHAR(300) | no |  |
| `context` | TEXT | no |  |
| `options` | JSONB | no |  |
| `chosen_option` | VARCHAR(300) | no |  |
| `rationale` | TEXT | no |  |
| `participants` | ARRAY | no |  |
| `decided_at` | DATETIME | no |  |
| `source_document_id` | UUID | yes | FK -> `documents` |
| `tsv` | TSVECTOR | no | Generated tsvector for full-text search. |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `dependencies`

Polymorphic `from blocks to` edges between initiatives, epics and items.

| Column | Type | Null | Notes |
|---|---|---|---|
| `from_type` | VARCHAR(16) | no |  |
| `from_id` | UUID | no |  |
| `to_type` | VARCHAR(16) | no |  |
| `to_id` | UUID | no |  |
| `kind` | VARCHAR(16) | no |  |
| `owning_team_id` | UUID | yes | FK -> `teams` |
| `status` | VARCHAR(16) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `document_chunks`

Heading-aware chunks with 384-dim embeddings (HNSW) and tsvector (GIN).

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_id` | UUID | no | FK -> `documents` |
| `chunk_index` | INTEGER | no |  |
| `heading` | VARCHAR(300) | no |  |
| `content` | TEXT | no |  |
| `embedding` | VECTOR(384) | no | 384-dim vector (pgvector). |
| `token_count` | INTEGER | no |  |
| `tsv` | TSVECTOR | no | Generated tsvector for full-text search. |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `documents`

Design docs, meeting notes, transcripts, PRDs and status reports.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | yes | FK -> `programs` |
| `type` | VARCHAR(32) | no |  |
| `title` | VARCHAR(300) | no |  |
| `body` | TEXT | no |  |
| `author_person_id` | UUID | yes | FK -> `people` |
| `source_url` | VARCHAR(500) | yes |  |
| `occurred_at` | DATETIME | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `epics`

Deliverable chunks of an initiative owned by one team.

| Column | Type | Null | Notes |
|---|---|---|---|
| `initiative_id` | UUID | yes | FK -> `initiatives` |
| `team_id` | UUID | yes | FK -> `teams` |
| `key` | VARCHAR(32) | no |  |
| `title` | VARCHAR(300) | no |  |
| `description` | TEXT | no |  |
| `status` | VARCHAR(32) | no |  |
| `target_date` | DATE | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `feedback_items`

Customer feedback with sentiment and embedding, clustered into themes.

| Column | Type | Null | Notes |
|---|---|---|---|
| `source` | VARCHAR(16) | no |  |
| `customer_segment` | VARCHAR(32) | no |  |
| `text` | TEXT | no |  |
| `sentiment` | FLOAT | no |  |
| `theme_id` | UUID | yes | FK -> `themes` |
| `received_at` | DATETIME | no |  |
| `embedding` | VECTOR(384) | yes | 384-dim vector (pgvector). |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `forecasts`

Monte Carlo milestone forecasts (P50/P80/P95, histogram, assumptions).

| Column | Type | Null | Notes |
|---|---|---|---|
| `milestone_id` | UUID | no | FK -> `milestones` |
| `p50_date` | DATE | no |  |
| `p80_date` | DATE | no |  |
| `p95_date` | DATE | no |  |
| `distribution` | JSONB | no |  |
| `assumptions` | JSONB | no |  |
| `run_at` | DATETIME | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `health_snapshots`

Daily program health score and sub-scores for the trend line.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `date` | DATE | no |  |
| `score` | FLOAT | no |  |
| `subscores` | JSONB | no |  |
| `drivers` | JSONB | no | Top contributing factors [{feature, value, contribution, label}]. |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `initiatives`

Roadmap items with RICE and WSJF scores and a now/next/later bucket.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `objective_id` | UUID | yes | FK -> `objectives` |
| `title` | VARCHAR(300) | no |  |
| `description` | TEXT | no |  |
| `roadmap_bucket` | VARCHAR(8) | no |  |
| `rice` | JSONB | no |  |
| `wsjf` | JSONB | no |  |
| `target_date` | DATE | yes |  |
| `status` | VARCHAR(32) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `integrations`

Connector configuration (mock/live); secrets Fernet-encrypted.

| Column | Type | Null | Notes |
|---|---|---|---|
| `provider` | VARCHAR(32) | no |  |
| `mode` | VARCHAR(8) | no |  |
| `config` | JSONB | no |  |
| `last_sync_at` | DATETIME | yes |  |
| `status` | VARCHAR(32) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `llm_calls`

LLM call telemetry: tokens, latency, cost estimate, prompt version.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | yes | FK -> `users` |
| `purpose` | VARCHAR(64) | no |  |
| `model` | VARCHAR(64) | no |  |
| `input_tokens` | INTEGER | no |  |
| `output_tokens` | INTEGER | no |  |
| `latency_ms` | FLOAT | no |  |
| `cost_estimate_usd` | FLOAT | no |  |
| `status` | VARCHAR(16) | no |  |
| `prompt_version` | VARCHAR(32) | yes |  |
| `request_id` | VARCHAR(64) | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `messages`

Chat messages with tool calls, citations and the agent trace.

| Column | Type | Null | Notes |
|---|---|---|---|
| `conversation_id` | UUID | no | FK -> `conversations` |
| `role` | VARCHAR(16) | no |  |
| `content` | TEXT | no |  |
| `tool_calls` | JSONB | no |  |
| `citations` | JSONB | no | Grounding references [{type, id, label}]. |
| `agent_trace` | JSONB | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `metrics_daily`

Daily team delivery metrics derived from work items.

| Column | Type | Null | Notes |
|---|---|---|---|
| `team_id` | UUID | no | FK -> `teams` |
| `date` | DATE | no |  |
| `velocity` | FLOAT | no |  |
| `throughput` | FLOAT | no |  |
| `cycle_time_p50` | FLOAT | no |  |
| `bug_inflow` | FLOAT | no |  |
| `review_latency_p50` | FLOAT | no |  |
| `wip` | FLOAT | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `milestones`

Program milestones with scope (epic IDs) and latest forecast.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `name` | VARCHAR(200) | no |  |
| `target_date` | DATE | no |  |
| `scope` | JSONB | no |  |
| `latest_forecast` | JSONB | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `ml_predictions`

Model outputs per entity with version and SHAP drivers.

| Column | Type | Null | Notes |
|---|---|---|---|
| `entity_type` | VARCHAR(32) | no |  |
| `entity_id` | UUID | no |  |
| `model_name` | VARCHAR(64) | no |  |
| `model_version` | VARCHAR(16) | no |  |
| `score` | FLOAT | no |  |
| `drivers` | JSONB | no | Top contributing factors [{feature, value, contribution, label}]. |
| `predicted_at` | DATETIME | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `notifications`

In-app notifications per user.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `kind` | VARCHAR(32) | no |  |
| `title` | VARCHAR(300) | no |  |
| `body` | TEXT | no |  |
| `link` | VARCHAR(500) | yes |  |
| `read_at` | DATETIME | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `objectives`

OKRs: objective title and key results with progress.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `title` | VARCHAR(300) | no |  |
| `key_results` | JSONB | no |  |
| `quarter` | VARCHAR(16) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `organizations`

Tenants. Every other table is scoped to one organisation.

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(200) | no |  |
| `slug` | VARCHAR(80) | no |  |
| `plan` | VARCHAR(40) | no |  |
| `settings` | JSONB | no |  |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `people`

The workforce (may link to a user). Capacity drives utilisation.

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(200) | no |  |
| `title` | VARCHAR(200) | no |  |
| `team_id` | UUID | yes | FK -> `teams` |
| `capacity_hours_per_week` | FLOAT | no |  |
| `timezone` | VARCHAR(64) | no |  |
| `growth_goals` | ARRAY | no |  |
| `avatar_url` | VARCHAR(500) | yes |  |
| `user_id` | UUID | yes | FK -> `users` |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `person_skills`

Person to skill with level 1-5 and evidence count.

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | FK -> `people` |
| `skill_id` | UUID | no | FK -> `skills` |
| `level` | INTEGER | no |  |
| `evidence_count` | INTEGER | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `persona_profiles`

The TPM model: priorities, tone, risk tolerance, escalation rules, style examples and learned delegation weights.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `priorities` | JSONB | no |  |
| `style_examples` | ARRAY | no |  |
| `tone` | VARCHAR(16) | no |  |
| `risk_tolerance` | VARCHAR(8) | no |  |
| `escalation_rules` | JSONB | no |  |
| `working_hours` | JSONB | no |  |
| `delegation_weights` | JSONB | no | Learned per-TPM delegation weights (bounded +-30% of defaults). |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `preference_events`

Every suggestion response with context features (learning signal).

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `suggestion_id` | UUID | yes | FK -> `suggestions` |
| `suggestion_type` | VARCHAR(32) | no |  |
| `context_features` | JSONB | no |  |
| `outcome` | VARCHAR(16) | no |  |
| `edit_diff` | TEXT | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `programs`

A program owned by a TPM, with configurable health weights.

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(200) | no |  |
| `objective` | TEXT | no |  |
| `status` | VARCHAR(32) | no |  |
| `target_date` | DATE | yes |  |
| `owner_user_id` | UUID | yes | FK -> `users` |
| `health_weights` | JSONB | no | Per-program weights for schedule/scope/quality/dependencies/team. |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `refresh_tokens`

Hashed refresh tokens grouped in rotation families for reuse detection.

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | FK -> `users` |
| `family_id` | UUID | no |  |
| `token_hash` | VARCHAR(64) | no |  |
| `expires_at` | DATETIME | no |  |
| `used_at` | DATETIME | yes |  |
| `revoked_at` | DATETIME | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `risks`

Risk register. severity = probability x impact (generated column).

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `title` | VARCHAR(300) | no |  |
| `description` | TEXT | no |  |
| `probability` | FLOAT | no |  |
| `impact` | INTEGER | no |  |
| `severity` | FLOAT | no | Generated: probability x impact. |
| `owner_person_id` | UUID | yes | FK -> `people` |
| `mitigation` | TEXT | no |  |
| `status` | VARCHAR(16) | no |  |
| `source` | VARCHAR(16) | no |  |
| `linked_entities` | JSONB | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `scenarios`

Saved what-if scenarios with changes and simulated results.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | no | FK -> `programs` |
| `name` | VARCHAR(200) | no |  |
| `changes` | JSONB | no |  |
| `result` | JSONB | no | Executor output, including what is needed to undo. |
| `created_by` | UUID | yes | FK -> `users` |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `skills`

Skill catalogue per tenant.

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(80) | no |  |
| `category` | VARCHAR(80) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `sprints`

Two-week team sprints with committed and completed points.

| Column | Type | Null | Notes |
|---|---|---|---|
| `team_id` | UUID | no | FK -> `teams` |
| `name` | VARCHAR(80) | no |  |
| `start_date` | DATE | no |  |
| `end_date` | DATE | no |  |
| `goal` | TEXT | no |  |
| `committed_points` | FLOAT | no |  |
| `completed_points` | FLOAT | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `suggestions`

Twin-proposed actions awaiting or past a decision; the Action Executor runs them according to the autonomy policy.

| Column | Type | Null | Notes |
|---|---|---|---|
| `program_id` | UUID | yes | FK -> `programs` |
| `user_id` | UUID | yes | FK -> `users` |
| `agent` | VARCHAR(32) | no |  |
| `type` | VARCHAR(32) | no |  |
| `title` | VARCHAR(300) | no |  |
| `payload` | JSONB | no | Action-specific body validated by the Action Executor. |
| `explanation` | TEXT | no |  |
| `drivers` | JSONB | no | Top contributing factors [{feature, value, contribution, label}]. |
| `citations` | JSONB | no | Grounding references [{type, id, label}]. |
| `autonomy_level_required` | INTEGER | no | Level needed to act without asking (1 observe .. 4 autonomous). |
| `status` | VARCHAR(16) | no |  |
| `responded_by` | UUID | yes | FK -> `users` |
| `responded_at` | DATETIME | yes |  |
| `feedback_reason` | TEXT | yes |  |
| `result` | JSONB | no | Executor output, including what is needed to undo. |
| `thread_id` | VARCHAR(100) | yes | LangGraph thread awaiting this approval, if any. |
| `expires_at` | DATETIME | yes |  |
| `undone_at` | DATETIME | yes |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `team_signals`

Team-level chat aggregates only (never per person; min group size 5).

| Column | Type | Null | Notes |
|---|---|---|---|
| `team_id` | UUID | no | FK -> `teams` |
| `date` | DATE | no |  |
| `sentiment_index` | FLOAT | no |  |
| `message_volume` | FLOAT | no |  |
| `after_hours_ratio` | FLOAT | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `teams`

Engineering teams the twin reasons about.

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(120) | no |  |
| `description` | TEXT | no |  |
| `manager_person_id` | UUID | yes | FK -> `people` |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `themes`

Feedback clusters with label, size, sentiment and opportunity breakdown.

| Column | Type | Null | Notes |
|---|---|---|---|
| `label` | VARCHAR(200) | no |  |
| `summary` | TEXT | no |  |
| `size` | INTEGER | no |  |
| `avg_sentiment` | FLOAT | no |  |
| `opportunity_score` | JSONB | no |  |
| `keywords` | ARRAY | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `time_off`

PTO windows used for sprint capacity and delegation penalties.

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | FK -> `people` |
| `start_date` | DATE | no |  |
| `end_date` | DATE | no |  |
| `kind` | VARCHAR(32) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `users`

People who sign in to TwinPM, with an RBAC role.

| Column | Type | Null | Notes |
|---|---|---|---|
| `email` | VARCHAR(320) | no |  |
| `name` | VARCHAR(200) | no |  |
| `password_hash` | VARCHAR(255) | no |  |
| `role` | VARCHAR(32) | no |  |
| `is_active` | BOOLEAN | no |  |
| `last_login_at` | DATETIME | yes |  |
| `timezone` | VARCHAR(64) | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |

## `work_item_events`

Lifecycle events (status changes, PRs, reopens, comments).

| Column | Type | Null | Notes |
|---|---|---|---|
| `work_item_id` | UUID | no | FK -> `work_items` |
| `event_type` | VARCHAR(32) | no |  |
| `from_value` | VARCHAR(200) | yes |  |
| `to_value` | VARCHAR(200) | yes |  |
| `actor_person_id` | UUID | yes | FK -> `people` |
| `occurred_at` | DATETIME | no |  |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

## `work_items`

Tickets (story/task/bug/spike) with lifecycle timestamps and review data.

| Column | Type | Null | Notes |
|---|---|---|---|
| `epic_id` | UUID | yes | FK -> `epics` |
| `team_id` | UUID | yes | FK -> `teams` |
| `sprint_id` | UUID | yes | FK -> `sprints` |
| `key` | VARCHAR(32) | no |  |
| `title` | VARCHAR(300) | no |  |
| `description` | TEXT | no |  |
| `type` | VARCHAR(16) | no |  |
| `status` | VARCHAR(16) | no |  |
| `story_points` | FLOAT | no |  |
| `estimate_days` | FLOAT | yes |  |
| `assignee_person_id` | UUID | yes | FK -> `people` |
| `created_at_src` | DATETIME | no | Creation time in the source tracker (Jira). |
| `started_at` | DATETIME | yes |  |
| `done_at` | DATETIME | yes |  |
| `due_date` | DATE | yes |  |
| `reopen_count` | INTEGER | no | Times the item was sent back after review. |
| `pr_review_hours` | FLOAT | no | Hours PRs for this item waited for review (to date). |
| `comments_count` | INTEGER | no |  |
| `labels` | ARRAY | no |  |
| `external_ref` | JSONB | no | Source system reference, the idempotency key for connector upserts. |
| `org_id` | UUID | no | FK -> `organizations`; Tenant. Indexed; enforced by the repository layer. |
| `id` | UUID | no | PK |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `deleted_at` | DATETIME | yes | Soft delete timestamp; rows with a value are hidden. |
