"""Strategy: feedback, themes, PRD drafting, devil's advocate and OKR drafts."""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.agents.guardrails import INJECTION_NOTICE, Redactor, clean_answer, fence
from twinpm.core.errors import AppError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.llm.provider import get_chat_model, is_demo
from twinpm.rag import retrieval
from twinpm.rag.embedding import embed
from twinpm.rag.indexer import index_document
from twinpm.services import audit, ml_jobs

SOURCES = {"support", "sales", "survey", "interview"}
MAX_IMPORT_ROWS = 5000


async def import_feedback(session: AsyncSession, ctx: TenantContext, raw: bytes) -> int:
    """CSV columns: text (required), source, customer_segment, sentiment, received_at."""
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise AppError("CSV must be UTF-8") from exc
    rows = []
    for i, r in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            raise AppError(f"At most {MAX_IMPORT_ROWS} rows per import")
        text = (r.get("text") or "").strip()
        if not text:
            continue
        try:
            sentiment = max(-1.0, min(1.0, float(r.get("sentiment") or 0)))
            received = (
                datetime.fromisoformat(r["received_at"])
                if r.get("received_at")
                else (datetime.now(UTC))
            )
        except ValueError as exc:
            raise AppError(f"Row {i + 2}: {exc}") from exc
        if received.tzinfo is None:
            received = received.replace(tzinfo=UTC)
        source = (r.get("source") or "support").lower()
        rows.append(
            {
                "id": uuid.uuid4(),
                "org_id": ctx.org_id,
                "text": text[:4000],
                "source": source if source in SOURCES else "support",
                "customer_segment": (r.get("customer_segment") or "smb")[:32],
                "sentiment": sentiment,
                "received_at": received,
            }
        )
    if not rows:
        raise AppError("No rows with a 'text' column found")
    vecs = embed([str(r["text"]) for r in rows])
    for r, v in zip(rows, vecs, strict=True):
        r["embedding"] = v.tolist()
    await session.execute(insert(m.FeedbackItem), rows)
    await audit.record(
        session,
        ctx,
        action="feedback.imported",
        entity_type="feedback",
        entity_id=None,
        after={"rows": len(rows)},
    )
    return len(rows)


async def _theme(
    session: AsyncSession, ctx: TenantContext, theme_id: uuid.UUID | None
) -> m.Theme | None:
    if theme_id is None:
        return None
    return await Repo(session, ctx, m.Theme).get(theme_id)


def _demo_prd(
    idea: str, theme: m.Theme | None, hits: list[retrieval.Hit], objectives: list[m.Objective]
) -> str:
    quotes = theme.opportunity_score.get("quotes", [])[:3] if theme else []
    size = theme.size if theme else 0
    sent = theme.avg_sentiment if theme else 0.0
    obj = objectives[0].title if objectives else "the program objectives"
    lines = [
        f"# PRD: {idea}",
        "",
        "## Problem",
        (
            f"{size} customer requests in the last six months point to the same gap "
            f"(average sentiment {sent:+.2f})."
            if theme
            else f"Customers need: {idea}."
        ),
        *[f"> {q}" for q in quotes],
        "",
        "## Users",
        "- Merchant finance and operations teams",
        "- NovaPay support agents",
        "",
        "## Goals",
        f"- Remove the top friction behind '{theme.label if theme else idea}'",
        f"- Contribute to: {obj}",
        "",
        "## Non-goals",
        "- Rebuilding reporting end to end",
        "- Changes to settlement timing",
        "",
        "## Success metrics",
        "- 50% fewer support tickets on this topic within 60 days of launch",
        "- Adoption by 30% of active merchants in the first quarter",
        "",
        "## Requirements",
        "1. Self-serve flow reachable from the dashboard in two clicks",
        "2. Works for accounts with over 1M transactions per month",
        "3. Audit trail of who exported or changed what",
        "",
        "## Risks",
        "- Load on the payments database: run asynchronously against a replica",
        "- Data exposure: respect role permissions and retention policy",
        "",
        "## Open questions",
        "- Which formats do enterprise merchants need first?",
        "- Do partners need API access in v1?",
        "",
    ]
    if hits:
        lines += ["## Related documents"] + [
            f"- {h.title} ({h.heading or 'overview'})" for h in hits[:3]
        ]
    return "\n".join(lines)


async def prd_stream(
    session: AsyncSession, ctx: TenantContext, idea: str, theme_id: uuid.UUID | None
) -> AsyncIterator[dict[str, Any]]:
    theme = await _theme(session, ctx, theme_id)
    query = f"{idea} {theme.label if theme else ''}".strip()
    hits = await retrieval.search(session, ctx.org_id, query, k=4)
    objectives = list(await Repo(session, ctx, m.Objective).all())
    citations = [{"type": "document", "id": str(h.document_id), "label": h.title} for h in hits]
    if theme:
        citations.append({"type": "theme", "id": str(theme.id), "label": theme.label})
    yield {"event": "agent_started", "data": {"agent": "strategy", "task": "prd"}}
    yield {
        "event": "tool_result",
        "data": {"tool": "rag_search", "summary": f"{len(hits)} related passages"},
    }
    text = ""
    if is_demo():
        for tok in re.findall(r"\S+\s*|\n", _demo_prd(idea, theme, hits, objectives)):
            text += tok
            yield {"event": "token", "data": {"text": tok}}
    else:
        from twinpm.agents.prompts import prompt

        red = Redactor()
        ctx_txt = "\n".join(fence(h.content[:800], h.doc_type) for h in hits)
        quotes = "\n".join(
            fence(q, "customer_feedback")
            for q in (theme.opportunity_score.get("quotes", []) if theme else [])
        )
        model = get_chat_model("strategy.prd", ctx)
        user = (
            f"Draft a PRD in markdown for: {idea}. Sections: Problem, Users, Goals, "
            f"Non-goals, Success metrics, Requirements, Risks, Open questions.\n"
            f"Objectives: {[o.title for o in objectives]}\nCustomer quotes:\n{quotes}\n"
            f"Related docs:\n{red.redact(ctx_txt)}"
        )
        async for chunk in model.astream([("system", prompt("strategy")), ("human", user)]):
            tok = (
                chunk.content
                if isinstance(chunk.content, str)
                else "".join(c.get("text", "") for c in chunk.content if isinstance(c, dict))
            )
            if tok:
                text += tok
                yield {"event": "token", "data": {"text": tok}}
    text, valid, warnings = await clean_answer(session, ctx.org_id, text, citations)
    program = (
        await session.execute(select(m.Program.id).where(m.Program.org_id == ctx.org_id).limit(1))
    ).scalar()
    doc = Repo(session, ctx, m.Document).add(
        m.Document(
            program_id=program,
            type="prd",
            title=f"PRD: {idea}"[:300],
            body=text,
            occurred_at=datetime.now(UTC),
        )
    )
    await session.flush()
    await index_document(
        session,
        {
            "id": doc.id,
            "org_id": ctx.org_id,
            "title": doc.title,
            "body": doc.body,
            "created_at": datetime.now(UTC),
        },
    )
    await audit.record(
        session,
        ctx,
        action="prd.drafted",
        entity_type="document",
        entity_id=doc.id,
        after={"title": doc.title},
        actor_type="twin",
    )
    await session.commit()
    for c in valid:
        yield {"event": "citation", "data": c}
    yield {"event": "done", "data": {"document_id": str(doc.id), "warnings": warnings}}


CLAIM = re.compile(
    r"[^.\n]*(?:\bwill\b|\bshould\b|\bmust\b|\d+%|\bevery\b|\ball\b)[^.\n]*[.\n]", re.I
)


async def devils_advocate(
    session: AsyncSession, ctx: TenantContext, document_id: uuid.UUID | None, text: str | None
) -> dict[str, Any]:
    if document_id is None and not text:
        raise AppError("Provide document_id or text")
    doc = await Repo(session, ctx, m.Document).get(document_id) if document_id else None
    body = doc.body if doc else (text or "")
    if not is_demo():
        from pydantic import BaseModel

        class Critique(BaseModel):
            assumptions: list[str]
            counter_arguments: list[str]
            validation_experiments: list[str]

        model = get_chat_model("strategy.devils_advocate", ctx)
        res = await model.with_structured_output(Critique, method="json_schema").ainvoke(
            f"{INJECTION_NOTICE}\nChallenge this document as a sharp, fair devil's advocate."
            f"\n{fence(Redactor().redact(body)[:12000])}"
        )
        out = res if isinstance(res, Critique) else Critique.model_validate(res)
        result = out.model_dump()
    else:
        claims = [c.strip() for c in CLAIM.findall(body)][:5] or [body.strip()[:200]]
        result = {
            "assumptions": [f"Assumes: {c}" for c in claims],
            "counter_arguments": [
                f'What if this does not hold? "{c[:120]}" may be true for the loudest '
                "customers but not for the median merchant."
                for c in claims[:3]
            ],
            "validation_experiments": [
                "Interview 8 merchants across segments before committing engineering time.",
                "Ship a manual or concierge version to 5 accounts and measure usage for 2 weeks.",
                "Add a fake-door entry point and measure click-through before building.",
            ],
        }
    result["document_id"] = str(doc.id) if doc else None
    result["citations"] = (
        [{"type": "document", "id": str(doc.id), "label": doc.title}] if doc else []
    )
    return result


async def draft_okrs(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> dict[str, Any]:
    prog = await Repo(session, ctx, m.Program).get(program_id)
    themes = sorted(
        await Repo(session, ctx, m.Theme).all(),
        key=lambda t: -float(t.opportunity_score.get("score", 0)),
    )[:3]
    _, ms = await ml_jobs.program_context(session, ctx.org_id)
    objectives = [
        {
            "objective": f"Launch {prog.name} on {ms.target_date:%b %d} "
            "without burning out the team",
            "key_results": [
                "Launch P80 on or before the target date by the next quarter review",
                "No engineer above 100% utilisation for two consecutive sprints",
                "Payments PR review latency back under 10 hours (p50)",
            ],
        }
    ] + [
        {
            "objective": f"Win back merchants frustrated by {t.label.lower()}",
            "key_results": [
                f"Halve support contacts tagged '{t.keywords[0] if t.keywords else t.label}'",
                f"Opportunity score for '{t.label}' below 50 by quarter end",
                "Ship a first version to 20 design-partner merchants",
            ],
        }
        for t in themes[:2]
    ]
    return {
        "program_id": str(prog.id),
        "objectives": objectives,
        "citations": [{"type": "program", "id": str(prog.id), "label": prog.name}]
        + [{"type": "theme", "id": str(t.id), "label": t.label} for t in themes[:2]],
    }
