"""In-memory program data for ML: one DataFrame per table.

`ProgramData` is built either from the database (`load_program_data`) or straight from a seed
`Dataset` (tests and offline experiments), so every model is a pure function of frames.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.db import models as m

TABLES: dict[str, Any] = {
    "items": m.WorkItem,
    "events": m.WorkItemEvent,
    "deps": m.Dependency,
    "sprints": m.Sprint,
    "people": m.Person,
    "person_skills": m.PersonSkill,
    "skills": m.Skill,
    "teams": m.Team,
    "metrics": m.MetricDaily,
    "epics": m.Epic,
    "milestones": m.Milestone,
    "signals": m.TeamSignal,
    "time_off": m.TimeOff,
    "feedback": m.FeedbackItem,
    "objectives": m.Objective,
    "initiatives": m.Initiative,
    "risks": m.Risk,
}
SEED_NAMES = {
    "items": "work_items",
    "events": "work_item_events",
    "deps": "dependencies",
    "sprints": "sprints",
    "people": "people",
    "person_skills": "person_skills",
    "skills": "skills",
    "teams": "teams",
    "metrics": "metrics_daily",
    "epics": "epics",
    "milestones": "milestones",
    "signals": "team_signals",
    "time_off": "time_off",
    "feedback": "feedback_items",
    "objectives": "objectives",
    "initiatives": "initiatives",
    "risks": "risks",
}
TS_COLS = ("created_at_src", "started_at", "done_at", "occurred_at", "received_at")


@dataclass
class ProgramData:
    org_id: uuid.UUID
    program_id: uuid.UUID | None
    now: datetime
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __getattr__(self, name: str) -> pd.DataFrame:
        frames = self.__dict__.get("frames", {})
        if name in frames:
            return frames[name]
        raise AttributeError(name)

    @property
    def today(self) -> date:
        return self.now.date()

    def copy(self) -> ProgramData:
        return ProgramData(
            self.org_id, self.program_id, self.now, {k: v.copy() for k, v in self.frames.items()}
        )


def _frame(rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)
    for c in TS_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True)
    if "deleted_at" in df.columns:
        df = df[df["deleted_at"].isna()].drop(columns=["deleted_at"])
    return df.reset_index(drop=True)


def _columns(model: Any) -> list[str]:
    return [c.name for c in model.__table__.columns if c.name not in ("embedding", "tsv")]


def from_dataset(ds: Any, now: datetime | None = None) -> ProgramData:
    """Build ProgramData from a seed `Dataset` (no database)."""
    frames = {
        key: _frame(
            [{c: r.get(c) for c in _columns(TABLES[key])} for r in ds.tables.get(table, [])],
            _columns(TABLES[key]),
        )
        for key, table in SEED_NAMES.items()
    }
    if "embedding" in (ds.tables.get("feedback_items") or [{}])[0]:
        frames["feedback"]["embedding"] = [r["embedding"] for r in ds.tables["feedback_items"]]
    org = ds.tables["organizations"][0]["id"]
    program = ds.tables["programs"][0]["id"] if ds.tables.get("programs") else None
    anchor_now = now or datetime.combine(ds.anchor, datetime.min.time(), UTC).replace(hour=9)
    return ProgramData(org, program, anchor_now, frames)


async def load_program_data(
    session: AsyncSession,
    org_id: uuid.UUID,
    program_id: uuid.UUID | None,
    now: datetime | None = None,
    with_embeddings: bool = False,
) -> ProgramData:
    frames: dict[str, pd.DataFrame] = {}
    for key, model in TABLES.items():
        cols = _columns(model)
        table_cols = [model.__table__.c[c] for c in cols]
        if with_embeddings and key == "feedback":
            table_cols.append(model.__table__.c["embedding"])
        res = await session.execute(select(*table_cols).where(model.org_id == org_id))
        rows = [dict(r._mapping) for r in res]
        df = _frame(rows, cols + (["embedding"] if with_embeddings and key == "feedback" else []))
        frames[key] = df
    return ProgramData(org_id, program_id, now or datetime.now(UTC), frames)


def as_of(data: ProgramData, t: datetime) -> ProgramData:
    """The program as it looked at `t`: later items, events and outcomes are removed."""
    ts = pd.Timestamp(t)
    out = data.copy()
    out.now = t
    f = out.frames
    items = f["items"]
    items = items[items["created_at_src"] <= ts].copy()
    ev = f["events"]
    ev = ev[(ev["occurred_at"] <= ts) & ev["work_item_id"].isin(items["id"])]
    later_done = items["done_at"] > ts
    items.loc[later_done, "done_at"] = pd.NaT
    items.loc[items["started_at"] > ts, "started_at"] = pd.NaT
    last = (
        ev[ev["event_type"] == "status_change"]
        .sort_values("occurred_at")
        .groupby("work_item_id")["to_value"]
        .last()
    )
    items["status"] = items["id"].map(last).fillna("todo")
    items.loc[items["done_at"].notna(), "status"] = "done"
    items.loc[(items["status"] == "done") & items["done_at"].isna(), "status"] = "in_review"
    f["items"] = items.reset_index(drop=True)
    f["events"] = ev.reset_index(drop=True)
    for key, col in (("metrics", "date"), ("signals", "date")):
        f[key] = f[key][f[key][col] <= ts.date()].reset_index(drop=True)
    if "received_at" in f["feedback"]:
        f["feedback"] = f["feedback"][f["feedback"]["received_at"] <= ts].reset_index(drop=True)
    return out
