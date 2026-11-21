"""Insights: metrics, anomalies, team health, metric questions."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Query

from twinpm.config import get_settings
from twinpm.core import rate_limit
from twinpm.db.models import Anomaly
from twinpm.db.repository import Repo
from twinpm.deps import DB, AiCtx, ReadCtx
from twinpm.schemas.risk import AnomalyOut, AskOut, AskRequest, MetricSeries, TeamHealthOut
from twinpm.services import insights as svc

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/metrics", response_model=list[MetricSeries])
async def metrics(
    ctx: ReadCtx,
    session: DB,
    metric: str = "velocity",
    team_id: uuid.UUID | None = None,
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
) -> list[MetricSeries]:
    end = to or date.today()
    start = from_ or end - timedelta(days=90)
    return await svc.query_metric(session, ctx, [team_id] if team_id else [], metric, start, end)


@router.get("/anomalies", response_model=list[AnomalyOut])
async def anomalies(
    ctx: ReadCtx, session: DB, program_id: uuid.UUID | None = None
) -> list[AnomalyOut]:
    rows = await Repo(session, ctx, Anomaly).all(
        Anomaly.status == "open", order_by=Anomaly.z_score.desc()
    )
    return [AnomalyOut.model_validate(r) for r in rows]


@router.get("/team-health", response_model=list[TeamHealthOut])
async def team_health(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> list[TeamHealthOut]:
    """Team-level aggregates only. Teams under 5 people are suppressed."""
    return await svc.team_health(session, ctx, program_id)


@router.post("/ask", response_model=AskOut)
async def ask(body: AskRequest, ctx: AiCtx, session: DB) -> AskOut:
    """Natural-language metric question answered through the parameterised metric tool."""
    await rate_limit.hit("ai", str(ctx.user_id), get_settings().rate_limit_ai_per_minute)
    from twinpm.agents.insights import answer

    return await answer(session, ctx, body.question)
