"""Read-only catalog: entity lookup (citation panels), teams, people, epics, model cards."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from twinpm.agents.guardrails import CITATION_TABLES
from twinpm.connectors.registry import chat_connector
from twinpm.core.errors import NotFoundError
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.deps import DB, ReadCtx
from twinpm.ml.registry import ModelRegistry

router = APIRouter(tags=["catalog"])
TITLE_FIELDS = ("title", "name", "label", "key", "metric")
HIDDEN = {"org_id", "password_hash", "embedding", "tsv", "deleted_at", "config"}


class EntityOut(BaseModel):
    type: str
    id: uuid.UUID
    title: str
    fields: dict[str, Any]
    link: str | None


LINKS = {
    "work_item": "risk",
    "epic": "risk",
    "risk": "risk",
    "forecast": "risk",
    "milestone": "risk",
    "decision": "comms",
    "document": "comms",
    "theme": "strategy",
    "feedback": "strategy",
    "person": "delegation",
    "team": "insights",
    "anomaly": "insights",
    "initiative": "roadmap",
    "suggestion": "command-center",
    "program": "command-center",
}


@router.get("/entities/{entity_type}/{entity_id}", response_model=EntityOut)
async def entity(entity_type: str, entity_id: uuid.UUID, ctx: ReadCtx, session: DB) -> EntityOut:
    model = CITATION_TABLES.get(entity_type)
    if model is None:
        raise NotFoundError(f"Unknown entity type {entity_type!r}")
    obj = await Repo(session, ctx, model).get(entity_id)
    fields = {}
    for c in model.__table__.columns:
        if c.name in HIDDEN or c.name in ("id",):
            continue
        v = getattr(obj, c.name)
        if isinstance(v, str) and len(v) > 1500:
            v = v[:1500] + "…"
        fields[c.name] = v
    title = next((str(getattr(obj, f)) for f in TITLE_FIELDS if getattr(obj, f, None)), entity_type)
    if entity_type == "work_item":
        pred = (
            await session.execute(
                select(m.MlPrediction).where(
                    m.MlPrediction.org_id == ctx.org_id, m.MlPrediction.entity_id == entity_id
                )
            )
        ).scalar()
        if pred:
            fields["delay_probability"] = pred.score
            fields["drivers"] = pred.drivers
        title = f"{obj.key} {obj.title}"
    return EntityOut(
        type=entity_type, id=entity_id, title=title, fields=fields, link=LINKS.get(entity_type)
    )


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    size: int


@router.get("/teams", response_model=list[TeamOut])
async def teams(ctx: ReadCtx, session: DB) -> list[TeamOut]:
    rows = await Repo(session, ctx, m.Team).all(order_by=m.Team.name)
    people = await Repo(session, ctx, m.Person).all()
    return [
        TeamOut(id=t.id, name=t.name, size=sum(p.team_id == t.id for p in people)) for t in rows
    ]


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    title: str
    team_id: uuid.UUID | None


@router.get("/people", response_model=list[PersonOut])
async def people(ctx: ReadCtx, session: DB) -> list[PersonOut]:
    rows = await Repo(session, ctx, m.Person).all(order_by=m.Person.name)
    return [PersonOut(id=p.id, name=p.name, title=p.title, team_id=p.team_id) for p in rows]


class EpicOut(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    team_id: uuid.UUID | None
    status: str
    initiative_id: uuid.UUID | None


@router.get("/epics", response_model=list[EpicOut])
async def epics(ctx: ReadCtx, session: DB) -> list[EpicOut]:
    rows = await Repo(session, ctx, m.Epic).all(order_by=m.Epic.title)
    return [
        EpicOut(
            id=e.id,
            key=e.key,
            title=e.title,
            team_id=e.team_id,
            status=e.status,
            initiative_id=e.initiative_id,
        )
        for e in rows
    ]


class WorkItemOut(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    status: str
    type: str
    story_points: float
    epic_id: uuid.UUID | None
    team_id: uuid.UUID | None
    assignee_person_id: uuid.UUID | None
    due_date: str | None


@router.get("/work-items", response_model=list[WorkItemOut])
async def work_items(
    ctx: ReadCtx, session: DB, epic_id: uuid.UUID | None = None, open_only: bool = True
) -> list[WorkItemOut]:
    where = []
    if epic_id:
        where.append(m.WorkItem.epic_id == epic_id)
    if open_only:
        where.append(m.WorkItem.status != "done")
    rows = await Repo(session, ctx, m.WorkItem).all(*where, order_by=m.WorkItem.key)
    return [
        WorkItemOut(
            id=w.id,
            key=w.key,
            title=w.title,
            status=w.status,
            type=w.type,
            story_points=w.story_points,
            epic_id=w.epic_id,
            team_id=w.team_id,
            assignee_person_id=w.assignee_person_id,
            due_date=w.due_date.isoformat() if w.due_date else None,
        )
        for w in rows[:500]
    ]


@router.get("/ml/models", response_model=list[dict[str, Any]])
async def model_cards(ctx: ReadCtx) -> list[dict[str, Any]]:
    reg = ModelRegistry.default()
    out = []
    for name in ("delay_risk", "effort"):
        info = reg.latest(name)
        if info:
            out.append({**info.metadata, "versions": reg.versions(name)})
    return out


@router.get("/comms/channel-feed", response_model=list[dict[str, Any]])
async def channel_feed(ctx: ReadCtx, channel: str = "#checkout-2-0") -> list[dict[str, Any]]:
    msgs = await chat_connector(ctx.org_id).history(channel, 30)
    return [{"channel": x.channel, "text": x.text, "ts": x.ts, "user": x.user} for x in msgs]


class MilestoneOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    name: str
    target_date: str
    scope: list[str]


@router.get("/milestones", response_model=list[MilestoneOut])
async def milestones(
    ctx: ReadCtx, session: DB, program_id: uuid.UUID | None = None
) -> list[MilestoneOut]:
    where = [m.Milestone.program_id == program_id] if program_id else []
    rows = await Repo(session, ctx, m.Milestone).all(*where, order_by=m.Milestone.target_date)
    return [
        MilestoneOut(
            id=r.id,
            program_id=r.program_id,
            name=r.name,
            target_date=r.target_date.isoformat(),
            scope=[str(s) for s in r.scope],
        )
        for r in rows
    ]
