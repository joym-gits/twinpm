"""Comms Studio: status reports, transcript extraction, meeting prep and the decision log."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.agents.guardrails import INJECTION_NOTICE, Redactor, clean_answer, fence
from twinpm.core.errors import AppError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.llm.provider import get_chat_model, is_demo
from twinpm.services import audit, suggestions

Audience = Literal["executive", "engineering", "customer"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DECISION_PHRASES = (
    "let's go with",
    "we're agreed",
    "we'll stick with",
    "we agreed",
    "decided to",
    "we decided",
)
ACTION_ASK = re.compile(
    r"^(?P<speaker>[A-Z][a-z]+):\s*(?P<owner>[A-Z][a-z]+),\s*can you (?P<task>.+?) by "
    r"(?P<day>Monday|Tuesday|Wednesday|Thursday|Friday)\?\s*$"
)
ACTION_SELF = re.compile(
    r"^(?P<speaker>[A-Z][a-z]+):\s*I'll (?P<task>.+?) by "
    r"(?P<day>Monday|Tuesday|Wednesday|Thursday|Friday)\.\s*$"
)
SPEAKER = re.compile(r"^(?P<speaker>[A-Z][a-z]+):\s*(?P<text>.+)$")


class ExtractedDecision(BaseModel):
    title: str
    chosen_option: str
    rationale: str
    quote: str
    confidence: float = Field(ge=0, le=1)


class ExtractedAction(BaseModel):
    title: str
    owner_person_id: uuid.UUID | None
    owner_name: str | None
    due_date: date | None
    confidence: float = Field(ge=0, le=1)
    quote: str


class ExtractOut(BaseModel):
    document_id: uuid.UUID | None
    decisions: list[ExtractedDecision]
    action_items: list[ExtractedAction]
    suggestion_ids: list[uuid.UUID] = Field(default_factory=list)
    method: str


class _LlmExtract(BaseModel):
    decisions: list[ExtractedDecision]
    action_items: list[dict[str, Any]]


def _next_weekday(base: date, name: str) -> date:
    target = WEEKDAYS.index(name.lower())
    days = (target - base.weekday()) % 7 or 7
    return base + timedelta(days=days)


def _decision_title(text: str) -> tuple[str, str]:
    low = text.lower()
    for p in DECISION_PHRASES:
        if p in low:
            rest = text[low.index(p) + len(p) :].strip(" ,.:;")
            chosen = re.split(r"[,.;]| because | since ", rest)[0].strip()
            return chosen[:1].upper() + chosen[1:120], rest
    return text[:120], text


def rule_extract(
    text: str, people: dict[str, m.Person], base: date
) -> tuple[list[ExtractedDecision], list[ExtractedAction]]:
    """Deterministic extraction for speaker-labelled transcripts (demo mode and fallback)."""
    decisions, actions = [], []
    for line in (ln.strip() for ln in text.splitlines() if ln.strip()):
        sm = SPEAKER.match(line)
        if not sm:
            continue
        low = sm.group("text").lower()
        if any(p in low for p in DECISION_PHRASES):
            chosen, rest = _decision_title(sm.group("text"))
            decisions.append(
                ExtractedDecision(
                    title=chosen, chosen_option=chosen, rationale=rest, quote=line, confidence=0.85
                )
            )
        for rx, conf in ((ACTION_ASK, 0.9), (ACTION_SELF, 0.85)):
            am = rx.match(line)
            if am:
                owner = am.groupdict().get("owner") or am.group("speaker")
                person = people.get(owner.lower())
                task = am.group("task").strip()
                actions.append(
                    ExtractedAction(
                        title=task[:1].upper() + task[1:],
                        owner_person_id=person.id if person else None,
                        owner_name=person.name if person else owner,
                        due_date=_next_weekday(base, am.group("day")),
                        confidence=conf,
                        quote=line,
                    )
                )
    return decisions, actions


async def _people_by_first_name(session: AsyncSession, ctx: TenantContext) -> dict[str, m.Person]:
    rows = await Repo(session, ctx, m.Person).all()
    out: dict[str, m.Person] = {}
    for p in rows:
        out.setdefault(p.name.split()[0].lower(), p)
    return out


async def extract(
    session: AsyncSession,
    ctx: TenantContext,
    document_id: uuid.UUID | None,
    text: str | None,
    create_suggestions: bool = True,
) -> ExtractOut:
    if document_id is None and not text:
        raise AppError("Provide document_id or transcript_text")
    doc = await Repo(session, ctx, m.Document).get(document_id) if document_id else None
    body = doc.body if doc else (text or "")
    base = (doc.occurred_at or doc.created_at).date() if doc else date.today()
    people = await _people_by_first_name(session, ctx)
    method = "rules"
    decisions, actions = rule_extract(body, people, base)
    if not is_demo() and not (decisions or actions):
        method = "llm"
        decisions, actions = await _llm_extract(ctx, body, people, base)
    out = ExtractOut(
        document_id=doc.id if doc else None,
        decisions=decisions,
        action_items=actions,
        method=method,
    )
    if create_suggestions:
        program = (
            await session.execute(
                select(m.Program.id).where(m.Program.org_id == ctx.org_id).limit(1)
            )
        ).scalar_one()
        epic = (
            await session.execute(
                Repo(session, ctx, m.Epic).select(m.Epic.title == "Payments API v2")
            )
        ).scalar() or (await session.execute(Repo(session, ctx, m.Epic).select())).scalars().first()
        cites = [{"type": "document", "id": str(doc.id), "label": doc.title}] if doc else []
        for a in actions:
            if epic is None:
                break
            s = await suggestions.create(
                session,
                ctx,
                type="create_task",
                agent="comms",
                title=f"Action item: {a.title}" + (f" ({a.owner_name})" if a.owner_name else ""),
                payload={
                    "epic_id": str(epic.id),
                    "title": a.title,
                    "description": f'From meeting: "{a.quote}"',
                    "type": "task",
                    "story_points": 2,
                    "assignee_person_id": str(a.owner_person_id) if a.owner_person_id else None,
                    "due_date": a.due_date.isoformat() if a.due_date else None,
                },
                explanation=f"Extracted with {a.confidence:.0%} confidence from: {a.quote}",
                citations=cites,
                program_id=program,
            )
            if s is not None:
                out.suggestion_ids.append(s.id)
    return out


async def _llm_extract(
    ctx: TenantContext, body: str, people: dict[str, m.Person], base: date
) -> tuple[list[ExtractedDecision], list[ExtractedAction]]:
    model = get_chat_model("comms.extract", ctx)
    red = Redactor()
    prompt = (
        f"{INJECTION_NOTICE}\nExtract explicit or implicit decisions and action items "
        f"(owner first name, task, due weekday if stated) from this meeting.\n"
        f"{fence(red.redact(body), 'transcript')}"
    )
    res = await model.with_structured_output(_LlmExtract, method="json_schema").ainvoke(prompt)
    parsed = res if isinstance(res, _LlmExtract) else _LlmExtract.model_validate(res)
    actions = []
    for a in parsed.action_items:
        owner = str(a.get("owner") or a.get("owner_name") or "")
        person = people.get(owner.split()[0].lower()) if owner else None
        day = str(a.get("due_weekday") or a.get("due") or "")
        actions.append(
            ExtractedAction(
                title=str(a.get("title") or a.get("task") or "")[:300],
                owner_person_id=person.id if person else None,
                owner_name=person.name if person else owner or None,
                due_date=_next_weekday(base, day) if day.lower() in WEEKDAYS else None,
                confidence=float(a.get("confidence", 0.7)),
                quote=str(a.get("quote", ""))[:300],
            )
        )
    return parsed.decisions, actions


# --------------------------------------------------------------------------- status report
async def _persona(
    session: AsyncSession, ctx: TenantContext
) -> tuple[str, m.PersonaProfile | None]:
    user = await session.get(m.User, ctx.user_id)
    p = (
        await session.execute(
            select(m.PersonaProfile).where(
                m.PersonaProfile.org_id == ctx.org_id, m.PersonaProfile.user_id == ctx.user_id
            )
        )
    ).scalar_one_or_none()
    return (user.name if user else "TPM"), p


def _demo_report(
    audience: Audience,
    snap: dict[str, Any],
    name: str,
    persona: m.PersonaProfile | None,
    period: str,
) -> str:
    fc = snap["forecast"]
    late = int(fc.get("days_late_at_p80") or 0)
    rag = "Red" if late > 14 else "Amber" if late > 0 else "Green"
    first = name.split()[0]
    risks = snap["top_risks"]
    items = snap["at_risk_items"]
    wins = snap["wins_by_epic"]
    concise = not persona or persona.tone in ("concise", "formal")
    style = persona.style_examples[0] if persona and persona.style_examples else ""
    lines = [
        f"# Checkout 2.0: {audience.title()} update ({period})",
        "",
        f"**Status: {rag}.** Health {snap['health']:.0f}"
        + (
            f" ({snap['health_delta_7d']:+.0f} this week)"
            if snap.get("health_delta_7d") is not None
            else ""
        )
        + f". Launch P80 is {fc['p80']} against a {fc['target']} target"
        + (f" ({late} days late)." if late > 0 else " (on track)."),
        "",
    ]
    if style and style.lower().startswith("bottom line"):
        lines += [
            "Bottom line: "
            + (
                "we are at risk on the launch date, and I have a plan."
                if late > 0
                else "we are on track."
            ),
            "",
        ]
    if audience == "executive":
        lines += (
            ["## Wins"]
            + [f"- {k}: {v} items shipped in the last two weeks" for k, v in wins.items()]
            + [""]
        )
        lines += (
            ["## Risks"]
            + [
                f"- **{r['title']}** (severity {r['severity']:.1f}, {r['status']})"
                for r in risks[:3]
            ]
            + [""]
        )
        lines += [
            "## Asks",
            "- Approve two Platform engineers (Karan, Li Wei) pairing on Payments API v2 "
            "for two sprints."
            if late > 0
            else "- None this period.",
            "",
        ]
        lines += [
            "## Next steps",
            "- Rebalance critical-path work and re-forecast Friday.",
            "- Clear the Payments review backlog with a second reviewer rotation.",
            "",
        ]
    elif audience == "engineering":
        lines += ["## Delivery", f"- {snap['completed_last_14d']} items completed in 14 days."]
        lines += (
            ["## At-risk items"]
            + [
                f"- {i['key']} {i['title']} ({i['probability']:.0%}): "
                + "; ".join(i["drivers"][:2])
                for i in items[:5]
            ]
            + [""]
        )
        lines += [
            "## Asks",
            "- Review Payments PRs within one working day.",
            "- Flag blockers in standup, not at sprint review.",
            "",
        ]
    else:
        lines = [
            f"# Checkout 2.0 progress update ({period})",
            "",
            "We continue to build the new checkout. Recent improvements: " + ", ".join(wins) + ".",
            "",
            "We will share launch timing once the next milestone is confirmed.",
            "",
        ]
    if not concise:
        lines.append(f"Questions welcome. {first}")
    else:
        lines.append(f"{first}")
    return "\n".join(lines)


async def status_report_stream(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    audience: Audience,
    period: str,
) -> AsyncIterator[dict[str, Any]]:
    from twinpm.agents.tools import NoArgs, get_program_snapshot

    await Repo(session, ctx, m.Program).get(program_id)
    snap_out = await get_program_snapshot(session, ctx, NoArgs())
    snap, citations = snap_out["data"], snap_out["citations"]
    name, persona = await _persona(session, ctx)
    yield {"event": "agent_started", "data": {"agent": "comms", "task": "status_report"}}
    yield {"event": "tool_call", "data": {"tool": "get_program_snapshot"}}
    yield {
        "event": "tool_result",
        "data": {
            "tool": "get_program_snapshot",
            "summary": f"health {snap['health']}, P80 {snap['forecast']['p80']}",
        },
    }
    text = ""
    if is_demo():
        body = _demo_report(audience, snap, name, persona, period)
        for tok in re.findall(r"\S+\s*", body):
            text += tok
            yield {"event": "token", "data": {"text": tok}}
    else:
        from twinpm.agents.prompts import persona_block, prompt

        model = get_chat_model("comms.status_report", ctx)
        sys = prompt("comms") + "\n" + persona_block(name, persona)
        user = (
            f"Write a {audience} status report for {period} in markdown with: RAG status, "
            f"wins, risks, asks, next steps. Use only these facts:\n"
            f"{fence(str(snap), 'program_snapshot')}"
        )
        async for chunk in model.astream([("system", sys), ("human", user)]):
            tok = (
                chunk.content
                if isinstance(chunk.content, str)
                else "".join(c.get("text", "") for c in chunk.content if isinstance(c, dict))
            )
            if tok:
                text += tok
                yield {"event": "token", "data": {"text": tok}}
    text, valid, warnings = await clean_answer(session, ctx.org_id, text, citations)
    for c in valid:
        yield {"event": "citation", "data": c}
    title = f"Checkout 2.0 {audience} update ({period})"
    s = await suggestions.create(
        session,
        ctx,
        type="status_report",
        agent="comms",
        title=title,
        payload={"title": title, "body": text, "audience": audience},
        explanation=f"Drafted by {name.split()[0]}'s twin from live program data.",
        citations=valid,
        program_id=program_id,
    )
    await session.commit()
    if s is not None:
        yield {
            "event": "suggestion_created",
            "data": {"id": str(s.id), "type": s.type, "status": s.status},
        }
    yield {"event": "done", "data": {"warnings": warnings, "text": text}}


# --------------------------------------------------------------------------- meeting prep
async def meeting_prep(
    session: AsyncSession,
    ctx: TenantContext,
    title: str,
    attendee_ids: list[uuid.UUID],
    program_id: uuid.UUID,
) -> dict[str, Any]:
    from twinpm.agents.tools import NoArgs, Query, get_program_snapshot, search_decisions

    people = [await Repo(session, ctx, m.Person).get(p) for p in attendee_ids]
    snap = await get_program_snapshot(session, ctx, NoArgs())
    decisions = await search_decisions(session, ctx, Query(query=title))
    items = snap["data"]["at_risk_items"]
    talking = []
    for p in people:
        mine = [i for i in items if i["owner"] == p.name]
        if mine:
            talking.append(
                f"{p.name}: {', '.join(i['key'] for i in mine)} at risk "
                f"({mine[0]['drivers'][0] if mine[0]['drivers'] else 'model risk'})."
            )
    fc = snap["data"]["forecast"]
    return {
        "title": title,
        "purpose": f"Align on {title.lower()} and unblock the launch critical path.",
        "context": [
            f"Launch P80 {fc['p80']} vs target {fc['target']}.",
            f"Health {snap['data']['health']:.0f}.",
        ],
        "talking_points": talking or ["No attendee-owned items are flagged at risk."],
        "decisions_needed": ["Confirm the rebalance plan for Payments API v2."]
        if (fc.get("days_late_at_p80") or 0) > 0
        else ["None pending."],
        "related_decisions": decisions["data"][:3],
        "citations": snap["citations"][:4]
        + decisions["citations"][:3]
        + [{"type": "person", "id": str(p.id), "label": p.name} for p in people],
    }


async def create_decision(
    session: AsyncSession, ctx: TenantContext, body: dict[str, Any]
) -> m.Decision:
    d = Repo(session, ctx, m.Decision).add(
        m.Decision(
            program_id=body["program_id"],
            title=body["title"],
            context=body.get("context", ""),
            options=body.get("options", []),
            chosen_option=body.get("chosen_option", ""),
            rationale=body.get("rationale", ""),
            participants=body.get("participants", []),
            decided_at=body.get("decided_at") or datetime.now(UTC),
            source_document_id=body.get("source_document_id"),
        )
    )
    await session.flush()
    await audit.record(
        session,
        ctx,
        action="decision.logged",
        entity_type="decision",
        entity_id=d.id,
        after={"title": d.title},
    )
    return d
