"""Persist ML outputs: predictions, forecasts, anomalies, themes, health and model risks.

`refresh_org` is idempotent and runs hourly in the worker (and after `make train`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.logging import get_logger
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.ml import anomaly, delay, effort, forecast, health, themes
from twinpm.ml.data import ProgramData, as_of, load_program_data
from twinpm.ml.registry import ModelRegistry
from twinpm.services import audit

log = get_logger(__name__)
PREVIOUS_FORECAST_DAYS = 14


def get_models(data: ProgramData | None = None) -> tuple[delay.DelayModel, effort.EffortModel]:
    """Latest registered models, training them on `data` when the registry is empty."""
    reg = ModelRegistry.default()
    d, e = reg.load(delay.NAME), reg.load(effort.NAME)
    if (d is None or e is None) and data is None:
        raise RuntimeError("Models are not trained; run `make train`")
    dm = d[0] if d else delay.train(data, reg)[0]  # type: ignore[arg-type]
    em = e[0] if e else effort.train(data, reg)[0]  # type: ignore[arg-type]
    return dm, em


async def program_context(
    session: AsyncSession, org_id: uuid.UUID
) -> tuple[m.Program, m.Milestone]:
    program = (
        await session.execute(
            select(m.Program)
            .where(m.Program.org_id == org_id, m.Program.deleted_at.is_(None))
            .order_by(m.Program.created_at)
            .limit(1)
        )
    ).scalar_one()
    milestone = (
        await session.execute(
            select(m.Milestone)
            .where(m.Milestone.program_id == program.id)
            .order_by(m.Milestone.target_date)
            .limit(1)
        )
    ).scalar_one()
    return program, milestone


async def load_demo_data(slug: str = "novapay") -> ProgramData:
    from twinpm.db.session import get_sessionmaker

    async with get_sessionmaker()() as s:
        org_id = (
            await s.execute(select(m.Organization.id).where(m.Organization.slug == slug))
        ).scalar_one()
        program, _ = await program_context(s, org_id)
        return await load_program_data(s, org_id, program.id)


def predictions_map(rows: list[m.MlPrediction]) -> dict[Any, float]:
    return {r.entity_id: r.score for r in rows}


async def latest_risks(session: AsyncSession, org_id: uuid.UUID) -> dict[Any, float]:
    rows = (
        (
            await session.execute(
                select(m.MlPrediction).where(
                    m.MlPrediction.org_id == org_id, m.MlPrediction.model_name == delay.NAME
                )
            )
        )
        .scalars()
        .all()
    )
    return predictions_map(list(rows))


def _forecast_row(
    org_id: uuid.UUID, milestone_id: uuid.UUID, res: forecast.ForecastResult, run_at: datetime
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "org_id": org_id,
        "milestone_id": milestone_id,
        "p50_date": res.p50,
        "p80_date": res.p80,
        "p95_date": res.p95,
        "distribution": {
            "histogram": res.histogram,
            "epic_p80": {k: v.isoformat() for k, v in res.epic_p80.items()},
            "on_time_probability": res.on_time_probability,
        },
        "assumptions": res.assumptions,
        "run_at": run_at,
    }


async def run_forecast(
    session: AsyncSession,
    data: ProgramData,
    milestone: m.Milestone,
    risks: dict[Any, float],
) -> forecast.ForecastResult:
    res = forecast.simulate(forecast.build_input(data, milestone.id, risks))
    await session.execute(
        pg_insert(m.Forecast), [_forecast_row(data.org_id, milestone.id, res, data.now)]
    )
    milestone.latest_forecast = {**res.as_dict(), "run_at": data.now.isoformat()}
    return res


async def refresh_org(session: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    program, milestone = await program_context(session, org_id)
    data = await load_program_data(session, org_id, program.id)
    dm, _ = get_models(data)
    version = ModelRegistry.default().latest(delay.NAME) or None
    now = data.now
    scored = delay.score_open_items(data, dm)
    await session.execute(
        delete(m.MlPrediction).where(
            m.MlPrediction.org_id == org_id, m.MlPrediction.model_name == delay.NAME
        )
    )
    if scored:
        await session.execute(
            pg_insert(m.MlPrediction),
            [
                {
                    "id": uuid.uuid4(),
                    "org_id": org_id,
                    "entity_type": "work_item",
                    "entity_id": r.work_item_id,
                    "model_name": delay.NAME,
                    "model_version": version.version if version else "v0000",
                    "score": r.score,
                    "drivers": r.drivers,
                    "predicted_at": now,
                }
                for r in scored
            ],
        )
    risks = {r.work_item_id: r.score for r in scored}

    has_previous = await session.scalar(
        select(m.Forecast.id)
        .where(
            m.Forecast.milestone_id == milestone.id,
            m.Forecast.run_at <= now - timedelta(days=PREVIOUS_FORECAST_DAYS - 1),
        )
        .limit(1)
    )
    if not has_previous:
        past = as_of(data, now - timedelta(days=PREVIOUS_FORECAST_DAYS))
        prisks = {r.work_item_id: r.score for r in delay.score_open_items(past, dm)}
        prev = forecast.simulate(forecast.build_input(past, milestone.id, prisks))
        await session.execute(
            pg_insert(m.Forecast), [_forecast_row(org_id, milestone.id, prev, past.now)]
        )
    fc = await run_forecast(session, data, milestone, risks)

    findings = anomaly.detect(data)
    await session.execute(
        delete(m.Anomaly).where(m.Anomaly.org_id == org_id, m.Anomaly.status == "open")
    )
    if findings:
        await session.execute(
            pg_insert(m.Anomaly),
            [
                {
                    "id": uuid.uuid4(),
                    "org_id": org_id,
                    "team_id": f.team_id,
                    "metric": f.metric,
                    "date": f.date,
                    "value": f.value,
                    "expected": f.expected,
                    "z_score": f.z_score,
                    "method": f.method,
                    "explanation": f.explanation,
                    "status": "open",
                }
                for f in findings
            ],
        )

    h = health.compute(data, fc.p80, milestone.target_date, risks, program.health_weights)
    await session.execute(
        pg_insert(m.HealthSnapshot)
        .values(
            id=uuid.uuid4(),
            org_id=org_id,
            program_id=program.id,
            date=now.date(),
            score=h.score,
            subscores=h.subscores,
            drivers=h.drivers,
        )
        .on_conflict_do_update(
            constraint="uq_health_snapshots_prog_date",
            set_={"score": h.score, "subscores": h.subscores, "drivers": h.drivers},
        )
    )
    await upsert_model_risks(session, data, program, risks, fc)
    await session.commit()
    return {
        "predictions": len(scored),
        "p80": fc.p80.isoformat(),
        "anomalies": len(findings),
        "health": h.score,
    }


async def upsert_model_risks(
    session: AsyncSession,
    data: ProgramData,
    program: m.Program,
    risks: dict[Any, float],
    fc: forecast.ForecastResult,
) -> None:
    """Keep one model-sourced register entry per critical epic whose open work is at risk."""
    it = data.items[data.items["status"] != "done"]
    epics = data.epics.set_index("id")
    inp = forecast.build_input(data, None, risks, scope=set(it["epic_id"]))
    for epic_id in forecast.critical_epics(data, inp):
        g = it[it["epic_id"] == epic_id]
        started = g[g["started_at"].notna()]
        if started.empty:
            continue
        p = float(pd.Series([risks.get(w, 0.0) for w in started["id"]]).mean())
        title = f"{epics.at[epic_id, 'title']} likely to slip"
        existing = (
            await session.execute(
                select(m.Risk).where(
                    m.Risk.org_id == data.org_id,
                    m.Risk.program_id == program.id,
                    m.Risk.source == "model",
                    m.Risk.title == title,
                )
            )
        ).scalar_one_or_none()
        owner = started["assignee_person_id"].mode()
        desc = (
            f"Delay model: mean risk {p:.0%} across {len(started)} in-flight items; epic P80 "
            f"{fc.epic_p80.get(str(epic_id), fc.p80)}. Other launch epics wait on it."
        )
        if p < 0.5:
            if existing is not None and existing.status != "closed":
                existing.status = "closed"
            continue
        if existing is None:
            row = m.Risk(
                org_id=data.org_id,
                program_id=program.id,
                title=title,
                description=desc,
                probability=round(min(p, 0.99), 2),
                impact=5,
                owner_person_id=owner.iloc[0] if len(owner) else None,
                mitigation="",
                status="open",
                source="model",
                linked_entities=[{"type": "epic", "id": str(epic_id)}],
            )
            session.add(row)
            await session.flush()
            await audit.record(
                session,
                TenantContext.system(data.org_id),
                action="risk.created",
                entity_type="risk",
                entity_id=row.id,
                after={"title": title, "probability": row.probability},
                reason="Delay model flagged the critical path",
            )
        else:
            existing.probability = round(min(p, 0.99), 2)
            existing.description = desc


async def train_and_refresh(session: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    program, _ = await program_context(session, org_id)
    data = await load_program_data(session, org_id, program.id)
    reg = ModelRegistry.default()
    _, dmetrics = delay.train(data, reg)
    _, emetrics = effort.train(data, reg)
    out = await refresh_org(session, org_id)
    tmetrics = await refresh_themes(session, org_id)
    return {"delay_risk": dmetrics, "effort": emetrics, "themes": tmetrics, **out}


async def refresh_themes(session: AsyncSession, org_id: uuid.UUID) -> dict[str, Any]:
    program, _ = await program_context(session, org_id)
    data = await load_program_data(session, org_id, program.id)
    results, method = themes.compute(data)
    await session.execute(
        update(m.FeedbackItem).where(m.FeedbackItem.org_id == org_id).values(theme_id=None)
    )
    await session.execute(delete(m.Theme).where(m.Theme.org_id == org_id))
    for t in results:
        row = m.Theme(
            org_id=org_id,
            label=t.label,
            summary=t.summary,
            size=len(t.member_ids),
            avg_sentiment=t.avg_sentiment,
            opportunity_score={**t.opportunity, "quotes": t.quotes, "method": method},
            keywords=t.keywords,
        )
        session.add(row)
        await session.flush()
        await session.execute(
            update(m.FeedbackItem)
            .where(m.FeedbackItem.id.in_(t.member_ids))
            .values(theme_id=row.id)
        )
    await session.commit()
    return {"themes": len(results), "method": method}


def utcnow() -> datetime:
    return datetime.now(UTC)
