"""The Action Executor: the single path for every write that changes program state.

execute() validates the payload, checks RBAC, checks the autonomy policy when the actor is the
twin, applies the change in the caller's transaction, writes the audit log (before/after) and
emits a domain event. Every handler returns what `undo()` needs to reverse it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import AppError, ConflictError, NotFoundError, PolicyViolationError
from twinpm.core.rbac import Perm, ensure
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.services import audit, events, policy

UNDO_WINDOW = timedelta(hours=24)


# --------------------------------------------------------------------------- payloads
class ReassignPayload(BaseModel):
    work_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    to_person_id: uuid.UUID
    reason: str | None = None


class CreateTaskPayload(BaseModel):
    epic_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str = ""
    type: Literal["story", "task", "bug", "spike"] = "story"
    story_points: float = Field(default=3, ge=0, le=40)
    estimate_days: float | None = None
    assignee_person_id: uuid.UUID | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    due_date: str | None = None


class StatusReportPayload(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=1)
    audience: Literal["executive", "engineering", "customer"] = "executive"
    channel: str = "#checkout-2-0"


class RiskUpdatePayload(BaseModel):
    risk_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation: str | None = None
    status: Literal["open", "mitigating", "closed"] | None = None
    owner_person_id: uuid.UUID | None = None
    linked_entities: list[dict[str, Any]] | None = None


class NudgePayload(BaseModel):
    work_item_id: uuid.UUID
    person_id: uuid.UUID
    message: str = Field(min_length=1, max_length=1000)


class RoadmapChangePayload(BaseModel):
    initiative_id: uuid.UUID
    roadmap_bucket: Literal["now", "next", "later"] | None = None
    rice: dict[str, float] | None = None
    wsjf: dict[str, float] | None = None


class ScenarioPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    changes: list[dict[str, Any]]
    result: dict[str, Any] = Field(default_factory=dict)
    options: list[dict[str, Any]] = Field(default_factory=list)


class AlertPayload(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    link: str | None = None


PAYLOADS: dict[str, type[BaseModel]] = {
    "reassign": ReassignPayload,
    "create_task": CreateTaskPayload,
    "status_report": StatusReportPayload,
    "risk_update": RiskUpdatePayload,
    "nudge": NudgePayload,
    "roadmap_change": RoadmapChangePayload,
    "scenario": ScenarioPayload,
    "alert": AlertPayload,
}
PERMISSIONS: dict[str, Perm] = {
    "reassign": Perm.PROGRAM_WRITE,
    "create_task": Perm.PROGRAM_WRITE,
    "status_report": Perm.COMMS_APPROVE,
    "risk_update": Perm.RISK_WRITE,
    "nudge": Perm.PROGRAM_WRITE,
    "roadmap_change": Perm.PROGRAM_WRITE,
    "scenario": Perm.PROGRAM_WRITE,
    "alert": Perm.READ,
}
REVERSIBLE = {
    "reassign",
    "create_task",
    "status_report",
    "risk_update",
    "roadmap_change",
    "scenario",
}


def validate(action_type: str, payload: dict[str, Any]) -> BaseModel:
    if action_type not in PAYLOADS:
        raise AppError(f"Unknown action type {action_type!r}")
    return PAYLOADS[action_type].model_validate(payload)


def _snap(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = str(v) if isinstance(v, uuid.UUID) else v
    return out


async def _notify(
    session: AsyncSession,
    ctx: TenantContext,
    user_id: uuid.UUID | None,
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
) -> None:
    if user_id is None:
        return
    session.add(
        m.Notification(
            org_id=ctx.org_id, user_id=user_id, kind=kind, title=title, body=body, link=link
        )
    )


# --------------------------------------------------------------------------- handlers
async def _reassign(
    s: AsyncSession, ctx: TenantContext, p: ReassignPayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    person = await Repo(s, ctx, m.Person).get(p.to_person_id)
    repo = Repo(s, ctx, m.WorkItem)
    previous: dict[str, str | None] = {}
    for wid in p.work_item_ids:
        item = await repo.get(wid)
        if item.status == "done":
            raise ConflictError(f"{item.key} is already done")
        before = _snap(item, ("assignee_person_id", "team_id"))
        previous[str(wid)] = before["assignee_person_id"]
        item.assignee_person_id = person.id
        if person.team_id is not None:
            item.team_id = person.team_id
        s.add(
            m.WorkItemEvent(
                org_id=ctx.org_id,
                work_item_id=item.id,
                event_type="reassigned",
                from_value=before["assignee_person_id"],
                to_value=str(person.id),
                occurred_at=datetime.now(UTC),
            )
        )
        await audit.record(
            s,
            ctx,
            action="work_item.reassigned",
            entity_type="work_item",
            entity_id=item.id,
            before=before,
            after=_snap(item, ("assignee_person_id", "team_id")),
            reason=p.reason,
            suggestion_id=sid,
        )
        if person.user_id:
            await _notify(
                s, ctx, person.user_id, "assignment", f"{item.key} assigned to you", item.title
            )
    return {"previous_assignees": previous, "to_person_id": str(person.id)}


async def _create_task(
    s: AsyncSession, ctx: TenantContext, p: CreateTaskPayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    epic = await Repo(s, ctx, m.Epic).get(p.epic_id)
    team = await s.get(m.Team, epic.team_id) if epic.team_id else None
    prefix = epic.key.split("-")[0] if epic.key else "TASK"
    count = len(
        (
            await s.execute(
                select(m.WorkItem.id).where(
                    m.WorkItem.org_id == ctx.org_id, m.WorkItem.key.like(f"{prefix}-%")
                )
            )
        ).all()
    )
    body = p.description
    if p.acceptance_criteria:
        body += "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in p.acceptance_criteria)
    now = datetime.now(UTC)
    item = Repo(s, ctx, m.WorkItem).add(
        m.WorkItem(
            epic_id=epic.id,
            team_id=team.id if team else None,
            key=f"{prefix}-{500 + count}",
            title=p.title,
            description=body,
            type=p.type,
            status="todo",
            story_points=p.story_points,
            estimate_days=p.estimate_days,
            assignee_person_id=p.assignee_person_id,
            created_at_src=now,
            labels=[],
            external_ref={"provider": "twinpm"},
            due_date=datetime.fromisoformat(p.due_date).date() if p.due_date else None,
        )
    )
    await s.flush()
    s.add(
        m.WorkItemEvent(
            org_id=ctx.org_id,
            work_item_id=item.id,
            event_type="status_change",
            from_value=None,
            to_value="todo",
            occurred_at=now,
        )
    )
    await audit.record(
        s,
        ctx,
        action="work_item.created",
        entity_type="work_item",
        entity_id=item.id,
        after={"key": item.key, "title": item.title},
        suggestion_id=sid,
    )
    return {"work_item_id": str(item.id), "key": item.key}


async def _status_report(
    s: AsyncSession, ctx: TenantContext, p: StatusReportPayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    program = (
        await s.execute(
            select(m.Program.id)
            .where(m.Program.org_id == ctx.org_id, m.Program.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar()
    doc = Repo(s, ctx, m.Document).add(
        m.Document(
            program_id=program,
            type="status_report",
            title=p.title,
            body=p.body,
            occurred_at=datetime.now(UTC),
            source_url=None,
        )
    )
    await s.flush()
    from twinpm.connectors.registry import chat_connector

    posted = await chat_connector(ctx.org_id).post_message(p.channel, f"*{p.title}*\n\n{p.body}")
    await audit.record(
        s,
        ctx,
        action="status_report.sent",
        entity_type="document",
        entity_id=doc.id,
        after={
            "title": p.title,
            "audience": p.audience,
            "channel": p.channel,
            "message_ts": posted,
        },
        suggestion_id=sid,
    )
    return {"document_id": str(doc.id), "channel": p.channel, "message_ts": posted}


RISK_FIELDS = (
    "title",
    "description",
    "probability",
    "impact",
    "mitigation",
    "status",
    "owner_person_id",
    "linked_entities",
)


async def _risk_update(
    s: AsyncSession, ctx: TenantContext, p: RiskUpdatePayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    repo = Repo(s, ctx, m.Risk)
    changes = p.model_dump(exclude_none=True, exclude={"risk_id"})
    if p.risk_id is None:
        if not p.title or p.probability is None or p.impact is None:
            raise AppError("New risks need title, probability and impact")
        program = (
            await s.execute(select(m.Program.id).where(m.Program.org_id == ctx.org_id).limit(1))
        ).scalar_one()
        risk = repo.add(
            m.Risk(
                program_id=program,
                source="agent" if ctx.actor_type == "twin" else "manual",
                **{
                    "status": "open",
                    "description": "",
                    "mitigation": "",
                    "linked_entities": [],
                    **changes,
                },
            )
        )
        await s.flush()
        await audit.record(
            s,
            ctx,
            action="risk.created",
            entity_type="risk",
            entity_id=risk.id,
            after=_snap(risk, RISK_FIELDS),
            suggestion_id=sid,
        )
        return {"risk_id": str(risk.id), "created": True}
    risk = await repo.get(p.risk_id)
    before = _snap(risk, RISK_FIELDS)
    for k, v in changes.items():
        setattr(risk, k, v)
    await audit.record(
        s,
        ctx,
        action="risk.updated",
        entity_type="risk",
        entity_id=risk.id,
        before=before,
        after=_snap(risk, RISK_FIELDS),
        suggestion_id=sid,
    )
    return {"risk_id": str(risk.id), "created": False, "before": before}


async def _nudge(
    s: AsyncSession, ctx: TenantContext, p: NudgePayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    item = await Repo(s, ctx, m.WorkItem).get(p.work_item_id)
    person = await Repo(s, ctx, m.Person).get(p.person_id)
    from twinpm.connectors.registry import chat_connector

    ts = await chat_connector(ctx.org_id).post_message(f"@{person.name}", p.message)
    await _notify(s, ctx, person.user_id, "nudge", f"Follow-up on {item.key}", p.message)
    s.add(
        m.WorkItemEvent(
            org_id=ctx.org_id,
            work_item_id=item.id,
            event_type="comment",
            from_value=None,
            to_value="nudge",
            occurred_at=datetime.now(UTC),
        )
    )
    item.comments_count += 1
    await audit.record(
        s,
        ctx,
        action="nudge.sent",
        entity_type="work_item",
        entity_id=item.id,
        after={"to": person.name, "message": p.message, "message_ts": ts},
        suggestion_id=sid,
    )
    return {"message_ts": ts, "to": str(person.id)}


async def _roadmap_change(
    s: AsyncSession, ctx: TenantContext, p: RoadmapChangePayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    ini = await Repo(s, ctx, m.Initiative).get(p.initiative_id)
    before = _snap(ini, ("roadmap_bucket", "rice", "wsjf"))
    if p.roadmap_bucket:
        ini.roadmap_bucket = p.roadmap_bucket
    if p.rice is not None:
        rice = {**ini.rice, **p.rice}
        if rice.get("effort"):
            rice["score"] = round(
                rice.get("reach", 0)
                * rice.get("impact", 0)
                * rice.get("confidence", 0)
                / rice["effort"],
                1,
            )
        ini.rice = rice
    if p.wsjf is not None:
        w = {**ini.wsjf, **p.wsjf}
        if w.get("job_size"):
            w["score"] = round(
                (
                    w.get("business_value", 0)
                    + w.get("time_criticality", 0)
                    + w.get("risk_reduction", 0)
                )
                / w["job_size"],
                2,
            )
        ini.wsjf = w
    await audit.record(
        s,
        ctx,
        action="initiative.updated",
        entity_type="initiative",
        entity_id=ini.id,
        before=before,
        after=_snap(ini, ("roadmap_bucket", "rice", "wsjf")),
        suggestion_id=sid,
    )
    return {"initiative_id": str(ini.id), "before": before}


async def _scenario(
    s: AsyncSession, ctx: TenantContext, p: ScenarioPayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    program = (
        await s.execute(select(m.Program.id).where(m.Program.org_id == ctx.org_id).limit(1))
    ).scalar_one()
    row = Repo(s, ctx, m.Scenario).add(
        m.Scenario(
            program_id=program,
            name=p.name,
            changes=p.changes,
            result=p.result,
            created_by=ctx.user_id,
        )
    )
    await s.flush()
    await audit.record(
        s,
        ctx,
        action="scenario.saved",
        entity_type="scenario",
        entity_id=row.id,
        after={"name": p.name},
        suggestion_id=sid,
    )
    return {"scenario_id": str(row.id)}


async def _alert(
    s: AsyncSession, ctx: TenantContext, p: AlertPayload, sid: uuid.UUID | None
) -> dict[str, Any]:
    await _notify(s, ctx, ctx.user_id, "alert", p.title, p.body, p.link)
    await audit.record(
        s,
        ctx,
        action="alert.sent",
        entity_type="notification",
        entity_id=None,
        after={"title": p.title},
        suggestion_id=sid,
    )
    return {}


HANDLERS: dict[str, Any] = {
    "reassign": _reassign,
    "create_task": _create_task,
    "status_report": _status_report,
    "risk_update": _risk_update,
    "nudge": _nudge,
    "roadmap_change": _roadmap_change,
    "scenario": _scenario,
    "alert": _alert,
}


async def execute(
    session: AsyncSession,
    ctx: TenantContext,
    action_type: str,
    payload: dict[str, Any],
    *,
    suggestion_id: uuid.UUID | None = None,
    approved: bool = False,
    program_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Run one action. `approved` is True only when a human accepted a suggestion."""
    parsed = validate(action_type, payload)
    ensure(ctx, PERMISSIONS[action_type])
    if ctx.actor_type == "twin" and not approved:
        level = await policy.level_for(session, ctx.org_id, ctx.user_id, action_type, program_id)
        if level < policy.Level.AUTONOMOUS:
            raise PolicyViolationError(
                f"The twin may not execute '{action_type}' at level L{int(level)} without approval"
            )
    result: dict[str, Any] = await HANDLERS[action_type](session, ctx, parsed, suggestion_id)
    await session.flush()
    await events.publish(
        ctx.org_id,
        f"action.{action_type}",
        {"suggestion_id": str(suggestion_id) if suggestion_id else None, **result},
    )
    return result


async def undo(
    session: AsyncSession, ctx: TenantContext, suggestion: m.Suggestion
) -> dict[str, Any]:
    if suggestion.status not in ("accepted", "edited", "auto_executed"):
        raise ConflictError("Only executed suggestions can be undone")
    if suggestion.undone_at is not None:
        raise ConflictError("Already undone")
    if suggestion.type not in REVERSIBLE:
        raise ConflictError(f"'{suggestion.type}' actions cannot be undone")
    if suggestion.responded_at and datetime.now(UTC) - suggestion.responded_at > UNDO_WINDOW:
        raise ConflictError("The 24-hour undo window has passed")
    ensure(ctx, PERMISSIONS[suggestion.type])
    res = suggestion.result or {}
    t = suggestion.type
    sid = suggestion.id
    if t == "reassign":
        repo = Repo(session, ctx, m.WorkItem)
        for wid, prev in res.get("previous_assignees", {}).items():
            item = await repo.get(uuid.UUID(wid))
            before = _snap(item, ("assignee_person_id", "team_id"))
            item.assignee_person_id = uuid.UUID(prev) if prev else None
            if prev:
                person = await session.get(m.Person, uuid.UUID(prev))
                if person and person.team_id:
                    item.team_id = person.team_id
            await audit.record(
                session,
                ctx,
                action="work_item.reassign_undone",
                entity_type="work_item",
                entity_id=item.id,
                before=before,
                after=_snap(item, ("assignee_person_id", "team_id")),
                suggestion_id=sid,
            )
    elif t in ("create_task", "status_report", "scenario"):
        model, key = {
            "create_task": (m.WorkItem, "work_item_id"),
            "status_report": (m.Document, "document_id"),
            "scenario": (m.Scenario, "scenario_id"),
        }[t]
        doc_repo: Repo[Any] = Repo(session, ctx, model)
        obj = await doc_repo.get(uuid.UUID(res[key]))
        await doc_repo.soft_delete(obj)
        await audit.record(
            session,
            ctx,
            action=f"{t}.undone",
            entity_type=model.__tablename__,
            entity_id=obj.id,
            suggestion_id=sid,
        )
    elif t == "risk_update":
        risk = await Repo(session, ctx, m.Risk).get(uuid.UUID(res["risk_id"]))
        if res.get("created"):
            await Repo(session, ctx, m.Risk).soft_delete(risk)
        else:
            for k, v in (res.get("before") or {}).items():
                setattr(risk, k, uuid.UUID(v) if k == "owner_person_id" and v else v)
        await audit.record(
            session,
            ctx,
            action="risk.update_undone",
            entity_type="risk",
            entity_id=risk.id,
            suggestion_id=sid,
        )
    elif t == "roadmap_change":
        ini = await Repo(session, ctx, m.Initiative).get(uuid.UUID(res["initiative_id"]))
        for k, v in (res.get("before") or {}).items():
            setattr(ini, k, v)
        await audit.record(
            session,
            ctx,
            action="initiative.update_undone",
            entity_type="initiative",
            entity_id=ini.id,
            suggestion_id=sid,
        )
    suggestion.undone_at = datetime.now(UTC)
    await session.flush()
    await events.publish(ctx.org_id, "action.undone", {"suggestion_id": str(sid)})
    return {"undone": True}


async def get_suggestion(session: AsyncSession, ctx: TenantContext, sid: uuid.UUID) -> m.Suggestion:
    s = await Repo(session, ctx, m.Suggestion).get_or_none(sid)
    if s is None:
        raise NotFoundError("Suggestion not found")
    return s
