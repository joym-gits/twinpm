"""Persona, autonomy policy and twin-learning settings."""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import AppError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.ml import preference
from twinpm.ml.delegation import DEFAULT_WEIGHTS
from twinpm.schemas.twin import (
    AutonomyOut,
    LearningStats,
    PersonaOut,
    PersonaUpdate,
    PolicyEntry,
)
from twinpm.services import audit, policy


async def _persona(session: AsyncSession, ctx: TenantContext) -> m.PersonaProfile:
    p = (
        await session.execute(
            select(m.PersonaProfile).where(
                m.PersonaProfile.org_id == ctx.org_id, m.PersonaProfile.user_id == ctx.user_id
            )
        )
    ).scalar_one_or_none()
    if p is None:
        p = m.PersonaProfile(
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            priorities=[],
            style_examples=[],
            tone="concise",
            risk_tolerance="medium",
            escalation_rules=[],
            working_hours={},
            delegation_weights={},
        )
        session.add(p)
        await session.flush()
    return p


async def get_persona(session: AsyncSession, ctx: TenantContext) -> PersonaOut:
    p = await _persona(session, ctx)
    user = await session.get(m.User, ctx.user_id)
    return PersonaOut(
        user_id=p.user_id,
        name=user.name if user else "",
        priorities=p.priorities,
        style_examples=list(p.style_examples or []),
        tone=p.tone,
        risk_tolerance=p.risk_tolerance,
        escalation_rules=p.escalation_rules,
        working_hours=p.working_hours,
        delegation_weights=p.delegation_weights or {},
    )


async def put_persona(session: AsyncSession, ctx: TenantContext, body: PersonaUpdate) -> PersonaOut:
    p = await _persona(session, ctx)
    fields = (
        "priorities",
        "style_examples",
        "tone",
        "risk_tolerance",
        "escalation_rules",
        "working_hours",
    )
    before = {f: getattr(p, f) for f in fields}
    for f in fields:
        setattr(p, f, getattr(body, f))
    await audit.record(
        session,
        ctx,
        action="persona.updated",
        entity_type="persona",
        entity_id=p.id,
        before=before,
        after=body.model_dump(),
    )
    return await get_persona(session, ctx)


async def get_autonomy(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID | None
) -> AutonomyOut:
    entries = []
    for t in policy.ACTION_TYPES:
        level = await policy.level_for(session, ctx.org_id, ctx.user_id, t, program_id)
        entries.append(
            PolicyEntry(
                action_type=t,
                level=int(level),
                default_level=int(policy.DEFAULTS[t]),
                max_level=int(policy.ceiling(t)),
                description=policy.DESCRIPTIONS[level],
            )
        )
    return AutonomyOut(
        program_id=program_id,
        policies=entries,
        levels={int(k): v for k, v in policy.DESCRIPTIONS.items()},
    )


async def put_autonomy(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID | None, levels: dict[str, int]
) -> AutonomyOut:
    for t, lvl in levels.items():
        if t not in policy.DEFAULTS:
            raise AppError(f"Unknown action type {t!r}")
        if not 1 <= lvl <= int(policy.ceiling(t)):
            raise AppError(f"'{t}' can be set between L1 and L{int(policy.ceiling(t))}")
    before = (await get_autonomy(session, ctx, program_id)).model_dump()
    for t, lvl in levels.items():
        await session.execute(
            delete(m.AutonomyPolicy).where(
                m.AutonomyPolicy.org_id == ctx.org_id,
                m.AutonomyPolicy.user_id == ctx.user_id,
                m.AutonomyPolicy.action_type == t,
                m.AutonomyPolicy.program_id.is_(None)
                if program_id is None
                else m.AutonomyPolicy.program_id == program_id,
            )
        )
        session.add(
            m.AutonomyPolicy(
                org_id=ctx.org_id,
                user_id=ctx.user_id,
                program_id=program_id,
                action_type=t,
                level=lvl,
            )
        )
    await session.flush()
    await audit.record(
        session,
        ctx,
        action="autonomy.updated",
        entity_type="autonomy_policy",
        entity_id=None,
        before={"levels": {p["action_type"]: p["level"] for p in before["policies"]}},
        after={"levels": levels},
    )
    return await get_autonomy(session, ctx, program_id)


async def learning_stats(session: AsyncSession, ctx: TenantContext) -> LearningStats:
    rows = (
        (
            await session.execute(
                select(m.PreferenceEvent).where(
                    m.PreferenceEvent.org_id == ctx.org_id, m.PreferenceEvent.user_id == ctx.user_id
                )
            )
        )
        .scalars()
        .all()
    )
    ev = pd.DataFrame(
        [
            {
                "user_id": r.user_id,
                "suggestion_type": r.suggestion_type,
                "context_features": r.context_features,
                "outcome": r.outcome,
            }
            for r in rows
        ]
    )
    model = preference.fit(ev, ctx.user_id)
    learned = preference.nudge_weights(ev) if not ev.empty else dict(DEFAULT_WEIGHTS)
    persona = await _persona(session, ctx)
    if learned != (persona.delegation_weights or {}):
        persona.delegation_weights = learned
    accepted = ev["outcome"].isin(preference.ACCEPTED).mean() if not ev.empty else None
    return LearningStats(
        suggestions_seen=len(ev),
        acceptance_rate=round(float(accepted), 3) if accepted is not None else None,
        by_type=model.by_type,
        default_weights=DEFAULT_WEIGHTS,
        learned_weights=learned,
        style_examples=len(persona.style_examples or []),
    )
