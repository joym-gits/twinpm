"""Generate docs/DATA_DICTIONARY.md from the SQLAlchemy metadata.

`python -m twinpm.data_dictionary ../../docs/DATA_DICTIONARY.md`
"""

from __future__ import annotations

import sys
from pathlib import Path

from twinpm.db import models  # noqa: F401
from twinpm.db.base import Base

TABLES = {
    "organizations": "Tenants. Every other table is scoped to one organisation.",
    "users": "People who sign in to TwinPM, with an RBAC role.",
    "refresh_tokens": "Hashed refresh tokens grouped in rotation families for reuse detection.",
    "api_tokens": "Hashed per-user API tokens for the MCP server and automation.",
    "teams": "Engineering teams the twin reasons about.",
    "people": "The workforce (may link to a user). Capacity drives utilisation.",
    "skills": "Skill catalogue per tenant.",
    "person_skills": "Person to skill with level 1-5 and evidence count.",
    "time_off": "PTO windows used for sprint capacity and delegation penalties.",
    "programs": "A program owned by a TPM, with configurable health weights.",
    "objectives": "OKRs: objective title and key results with progress.",
    "initiatives": "Roadmap items with RICE and WSJF scores and a now/next/later bucket.",
    "epics": "Deliverable chunks of an initiative owned by one team.",
    "work_items": "Tickets (story/task/bug/spike) with lifecycle timestamps and review data.",
    "work_item_events": "Lifecycle events (status changes, PRs, reopens, comments).",
    "dependencies": "Polymorphic `from blocks to` edges between initiatives, epics and items.",
    "sprints": "Two-week team sprints with committed and completed points.",
    "milestones": "Program milestones with scope (epic IDs) and latest forecast.",
    "risks": "Risk register. severity = probability x impact (generated column).",
    "decisions": "Decision log with options, rationale and participants (full-text indexed).",
    "documents": "Design docs, meeting notes, transcripts, PRDs and status reports.",
    "document_chunks": "Heading-aware chunks with 384-dim embeddings (HNSW) and tsvector (GIN).",
    "feedback_items": "Customer feedback with sentiment and embedding, clustered into themes.",
    "themes": "Feedback clusters with label, size, sentiment and opportunity breakdown.",
    "team_signals": "Team-level chat aggregates only (never per person; min group size 5).",
    "metrics_daily": "Daily team delivery metrics derived from work items.",
    "ml_predictions": "Model outputs per entity with version and SHAP drivers.",
    "forecasts": "Monte Carlo milestone forecasts (P50/P80/P95, histogram, assumptions).",
    "anomalies": "Detected metric anomalies with method and explanation.",
    "health_snapshots": "Daily program health score and sub-scores for the trend line.",
    "suggestions": "Twin-proposed actions awaiting or past a decision; the Action Executor "
    "runs them according to the autonomy policy.",
    "scenarios": "Saved what-if scenarios with changes and simulated results.",
    "persona_profiles": "The TPM model: priorities, tone, risk tolerance, escalation rules, "
    "style examples and learned delegation weights.",
    "autonomy_policies": "Per-user (optionally per-program) autonomy level 1-4 per action type.",
    "preference_events": "Every suggestion response with context features (learning signal).",
    "audit_log": "Append-only record of every state change and twin action. UPDATE, DELETE "
    "and TRUNCATE are rejected by a trigger (tenant purge is the only exception).",
    "notifications": "In-app notifications per user.",
    "conversations": "Ask the Twin threads (also the LangGraph thread id).",
    "messages": "Chat messages with tool calls, citations and the agent trace.",
    "integrations": "Connector configuration (mock/live); secrets Fernet-encrypted.",
    "llm_calls": "LLM call telemetry: tokens, latency, cost estimate, prompt version.",
}

FIELDS = {
    "org_id": "Tenant. Indexed; enforced by the repository layer.",
    "deleted_at": "Soft delete timestamp; rows with a value are hidden.",
    "created_at_src": "Creation time in the source tracker (Jira).",
    "external_ref": "Source system reference, the idempotency key for connector upserts.",
    "pr_review_hours": "Hours PRs for this item waited for review (to date).",
    "reopen_count": "Times the item was sent back after review.",
    "autonomy_level_required": "Level needed to act without asking (1 observe .. 4 autonomous).",
    "drivers": "Top contributing factors [{feature, value, contribution, label}].",
    "citations": "Grounding references [{type, id, label}].",
    "payload": "Action-specific body validated by the Action Executor.",
    "result": "Executor output, including what is needed to undo.",
    "thread_id": "LangGraph thread awaiting this approval, if any.",
    "health_weights": "Per-program weights for schedule/scope/quality/dependencies/team.",
    "delegation_weights": "Learned per-TPM delegation weights (bounded +-30% of defaults).",
    "embedding": "384-dim vector (pgvector).",
    "tsv": "Generated tsvector for full-text search.",
    "severity": "Generated: probability x impact.",
}


def render() -> str:
    out = [
        "# Data dictionary",
        "",
        "Generated from the SQLAlchemy models by `python -m twinpm.data_dictionary`. Every "
        "tenant table carries `id`, `org_id`, `created_at` and `updated_at`.",
        "",
    ]
    for name, table in sorted(Base.metadata.tables.items()):
        out += [
            f"## `{name}`",
            "",
            TABLES.get(name, ""),
            "",
            "| Column | Type | Null | Notes |",
            "|---|---|---|---|",
        ]
        for col in table.columns:
            notes = []
            if col.primary_key:
                notes.append("PK")
            notes += [f"FK -> `{fk.column.table.name}`" for fk in col.foreign_keys]
            if col.name in FIELDS:
                notes.append(FIELDS[col.name])
            null = "yes" if col.nullable else "no"
            out.append(f"| `{col.name}` | {col.type} | {null} | {'; '.join(notes)} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    Path(sys.argv[1] if len(sys.argv) > 1 else "DATA_DICTIONARY.md").write_text(render())
