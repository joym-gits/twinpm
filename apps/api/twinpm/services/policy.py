"""Autonomy policy engine. Deterministic code; the LLM never decides permissions.

Levels:
  L1 Observe  - notify only
  L2 Suggest  - create a pending suggestion
  L3 Approve  - approval card; one click executes
  L4 Auto     - execute immediately, log, notify, undo available
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.db.models import AutonomyPolicy

ActionType = Literal[
    "alert",
    "briefing",
    "nudge",
    "status_report",
    "reassign",
    "create_task",
    "risk_update",
    "roadmap_change",
    "scenario",
]
ACTION_TYPES: tuple[str, ...] = (
    "alert",
    "briefing",
    "nudge",
    "status_report",
    "reassign",
    "create_task",
    "risk_update",
    "roadmap_change",
    "scenario",
)


class Level(IntEnum):
    OBSERVE = 1
    SUGGEST = 2
    APPROVE = 3
    AUTONOMOUS = 4


DEFAULTS: dict[str, Level] = {
    "alert": Level.AUTONOMOUS,
    "briefing": Level.AUTONOMOUS,
    "nudge": Level.APPROVE,  # L4 is opt-in
    "status_report": Level.APPROVE,
    "reassign": Level.APPROVE,
    "create_task": Level.APPROVE,
    "risk_update": Level.APPROVE,
    "roadmap_change": Level.SUGGEST,
    "scenario": Level.SUGGEST,
}
# Hard ceilings no policy can exceed (sending external comms needs a human).
CEILINGS: dict[str, Level] = {"status_report": Level.APPROVE, "roadmap_change": Level.APPROVE}
DESCRIPTIONS = {
    Level.OBSERVE: "Observe: the twin notifies you and takes no action.",
    Level.SUGGEST: "Suggest: the twin drafts a suggestion for you to review.",
    Level.APPROVE: "Act with approval: one click from you executes the twin's action.",
    Level.AUTONOMOUS: "Autonomous: the twin acts, logs it, notifies you and lets you undo.",
}


@dataclass(frozen=True)
class Decision:
    action_type: str
    level: Level
    execute_now: bool
    create_suggestion: bool
    notify_only: bool


def ceiling(action_type: str) -> Level:
    return CEILINGS.get(action_type, Level.AUTONOMOUS)


async def level_for(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action_type: str,
    program_id: uuid.UUID | None = None,
) -> Level:
    if action_type not in DEFAULTS:
        raise ValueError(f"Unknown action type {action_type!r}")
    level = DEFAULTS[action_type]
    if user_id is not None:
        rows = (
            (
                await session.execute(
                    select(AutonomyPolicy).where(
                        AutonomyPolicy.org_id == org_id,
                        AutonomyPolicy.user_id == user_id,
                        AutonomyPolicy.action_type == action_type,
                        (AutonomyPolicy.program_id == program_id)
                        | AutonomyPolicy.program_id.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        # A program-specific policy beats the user's global one.
        specific = [r for r in rows if r.program_id is not None]
        chosen = specific or [r for r in rows if r.program_id is None]
        if chosen:
            level = Level(chosen[0].level)
    return min(level, ceiling(action_type))


def decide(action_type: str, level: Level) -> Decision:
    """Pure mapping from level to behaviour. `requested` levels from an LLM are ignored."""
    return Decision(
        action_type=action_type,
        level=level,
        execute_now=level == Level.AUTONOMOUS,
        create_suggestion=level in (Level.SUGGEST, Level.APPROVE),
        notify_only=level == Level.OBSERVE,
    )


async def decide_for(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action_type: str,
    program_id: uuid.UUID | None = None,
) -> Decision:
    return decide(action_type, await level_for(session, org_id, user_id, action_type, program_id))
