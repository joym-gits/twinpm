"""Insights: metric series, anomalies, team health and safe natural-language metric questions.

The metric tool is parameterised (team, metric, date range from fixed allow-lists). No SQL is
ever built from model or user text.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import AppError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.ml.anomaly import LABEL, METRICS
from twinpm.ml.features import FeatureBuilder
from twinpm.schemas.risk import AskOut, MetricPoint, MetricSeries, TeamHealthOut
from twinpm.services.data_cache import get_program_data

MIN_GROUP_SIZE = 5
METRIC_ALIASES = {
    "velocity": "velocity",
    "throughput": "throughput",
    "cycle": "cycle_time_p50",
    "cycle time": "cycle_time_p50",
    "lead time": "cycle_time_p50",
    "bug": "bug_inflow",
    "bugs": "bug_inflow",
    "review": "review_latency_p50",
    "review latency": "review_latency_p50",
    "pr review": "review_latency_p50",
    "wip": "wip",
    "work in progress": "wip",
}


async def query_metric(
    session: AsyncSession,
    ctx: TenantContext,
    team_ids: list[uuid.UUID],
    metric: str,
    start: date,
    end: date,
) -> list[MetricSeries]:
    if metric not in METRICS:
        raise AppError(f"Unknown metric {metric!r}", {"allowed": list(METRICS)})
    if (end - start).days > 400:
        raise AppError("Date range is limited to 400 days")
    teams = {t.id: t.name for t in await Repo(session, ctx, m.Team).all()}
    team_ids = [t for t in team_ids if t in teams] or list(teams)
    column = getattr(m.MetricDaily, metric)
    rows = (
        await session.execute(
            select(m.MetricDaily.team_id, m.MetricDaily.date, column)
            .where(
                m.MetricDaily.org_id == ctx.org_id,
                m.MetricDaily.team_id.in_(team_ids),
                m.MetricDaily.date >= start,
                m.MetricDaily.date <= end,
            )
            .order_by(m.MetricDaily.date)
        )
    ).all()
    anomalies = {
        (a.team_id, a.date)
        for a in (
            await session.execute(
                select(m.Anomaly).where(m.Anomaly.org_id == ctx.org_id, m.Anomaly.metric == metric)
            )
        ).scalars()
    }
    out: dict[uuid.UUID, MetricSeries] = {}
    for team_id, d, value in rows:
        s = out.setdefault(
            team_id, MetricSeries(team_id=team_id, team=teams[team_id], metric=metric, points=[])
        )
        s.points.append(MetricPoint(date=d, value=float(value), anomaly=(team_id, d) in anomalies))
    return list(out.values())


async def team_health(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> list[TeamHealthOut]:
    data = await get_program_data(session, ctx.org_id, program_id)
    fb = FeatureBuilder(data)
    import pandas as pd

    now = pd.Timestamp(data.now)
    out = []
    for t in data.teams.itertuples():
        members = data.people[data.people["team_id"] == t.id]
        if len(members) < MIN_GROUP_SIZE:
            out.append(
                TeamHealthOut(
                    team_id=t.id,
                    team=t.name,
                    size=len(members),
                    suppressed=True,
                    sentiment_index=None,
                    sentiment_trend=None,
                    after_hours_ratio=None,
                    message_volume=None,
                    utilisation_mean=None,
                    series=[],
                )
            )
            continue
        sig = data.signals[data.signals["team_id"] == t.id].sort_values("date")
        last7, prev = sig.tail(7), sig.iloc[-35:-7]
        out.append(
            TeamHealthOut(
                team_id=t.id,
                team=t.name,
                size=len(members),
                suppressed=False,
                sentiment_index=round(float(last7["sentiment_index"].mean()), 3),
                sentiment_trend=round(
                    float(last7["sentiment_index"].mean() - prev["sentiment_index"].mean()), 3
                ),
                after_hours_ratio=round(float(last7["after_hours_ratio"].mean()), 3),
                message_volume=round(float(last7["message_volume"].mean()), 1),
                utilisation_mean=round(
                    float(np.mean([fb.utilisation(p, now) for p in members["id"]])), 3
                ),
                series=[
                    {
                        "date": r.date.isoformat(),
                        "sentiment": r.sentiment_index,
                        "after_hours": r.after_hours_ratio,
                    }
                    for r in sig.tail(60).itertuples()
                ],
            )
        )
    return out


def parse_question(question: str, team_names: dict[str, uuid.UUID], today: date) -> dict[str, Any]:
    """Map a question onto query_metric parameters using fixed allow-lists only."""
    q = question.lower()
    metric = next(
        (v for k, v in sorted(METRIC_ALIASES.items(), key=lambda kv: -len(kv[0])) if k in q),
        "velocity",
    )
    teams = [tid for name, tid in team_names.items() if name.lower() in q]
    days = 56
    mm = re.search(r"(?:last|past)\s+(\d{1,3})\s*(day|week|month)s?", q)
    if mm:
        n = int(mm.group(1))
        days = n * {"day": 1, "week": 7, "month": 30}[mm.group(2)]
    elif "quarter" in q:
        days = 90
    days = min(max(days, 7), 365)
    return {
        "metric": metric,
        "team_ids": teams,
        "start": today - timedelta(days=days),
        "end": today,
    }


async def ask(session: AsyncSession, ctx: TenantContext, question: str) -> AskOut:
    teams = {t.name: t.id for t in await Repo(session, ctx, m.Team).all()}
    params = parse_question(question, teams, date.today())
    series = await query_metric(
        session, ctx, params["team_ids"], params["metric"], params["start"], params["end"]
    )
    name, unit = LABEL[params["metric"]]
    lines = []
    for s in series:
        vals = [p.value for p in s.points]
        if not vals:
            continue
        half = len(vals) // 2
        first, last = float(np.mean(vals[:half] or vals)), float(np.mean(vals[half:]))
        change = (last - first) / first if first else 0.0
        flagged = sum(p.anomaly for p in s.points)
        lines.append(
            f"{s.team} {name} averaged {last:.1f}{unit} recently vs {first:.1f}{unit} "
            f"earlier in the window ({change:+.0%})"
            + (f"; {flagged} anomalous day(s) flagged" if flagged else "")
            + "."
        )
    narrative = " ".join(lines) or "No data for that question in the selected range."
    chart = {
        "type": "line",
        "metric": params["metric"],
        "unit": unit,
        "title": name.title(),
        "series": [
            {
                "name": s.team,
                "data": [
                    {"date": p.date.isoformat(), "value": p.value, "anomaly": p.anomaly}
                    for p in s.points
                ],
            }
            for s in series
        ],
    }
    return AskOut(
        question=question,
        narrative=narrative,
        chart=chart,
        citations=[
            {"type": "metric", "id": f"{s.team_id}:{params['metric']}", "label": f"{s.team} {name}"}
            for s in series
        ],
        tool_calls=[
            {
                "tool": "query_metric",
                "args": {
                    "metric": params["metric"],
                    "team_ids": [str(t) for t in params["team_ids"]],
                    "start": params["start"].isoformat(),
                    "end": params["end"].isoformat(),
                },
            }
        ],
    )
