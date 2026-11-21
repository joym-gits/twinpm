"""7.8 Program health score with transparent sub-scores and drivers.

health = 0.30*schedule + 0.20*scope + 0.20*quality + 0.15*dependencies + 0.15*team
(weights per program, configurable in `programs.health_weights`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from twinpm.domain import OVERLOAD_THRESHOLD
from twinpm.ml.data import ProgramData
from twinpm.ml.features import FeatureBuilder

DEFAULT_WEIGHTS = {
    "schedule": 0.30,
    "scope": 0.20,
    "quality": 0.20,
    "dependencies": 0.15,
    "team": 0.15,
}


@dataclass
class Health:
    score: float
    subscores: dict[str, float]
    drivers: list[dict[str, Any]]


def _clip(v: float) -> float:
    return round(float(np.clip(v, 0, 100)), 1)


def compute(
    data: ProgramData,
    p80: date,
    target: date,
    risks: dict[Any, float],
    weights: dict[str, float] | None = None,
) -> Health:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    now = pd.Timestamp(data.now)
    it = data.items
    ms = data.milestones.iloc[0]
    scope_epics = {uuid.UUID(str(e)) for e in ms["scope"]}
    in_scope = it[it["epic_id"].isin(scope_epics)]
    drivers: list[dict[str, Any]] = []

    late_days = (p80 - target).days
    schedule = _clip(100 - max(0, late_days) * 100 / 30)
    drivers.append(
        {
            "subscore": "schedule",
            "label": (
                f"Launch P80 {p80:%b %d} is {late_days} days after the {target:%b %d} target"
                if late_days > 0
                else f"Launch P80 {p80:%b %d} is on or before target"
            ),
            "value": late_days,
        }
    )

    window = now - timedelta(days=28)
    added = float(in_scope.loc[in_scope["created_at_src"] > window, "story_points"].sum())
    existing = float(in_scope.loc[in_scope["created_at_src"] <= window, "story_points"].sum())
    creep = added / existing if existing else 0.0
    scope = _clip(100 - max(0.0, creep - 0.10) * 200)
    drivers.append(
        {
            "subscore": "scope",
            "label": f"Scope grew {creep:.0%} in the last 2 sprints",
            "value": round(creep, 3),
        }
    )

    def rate(lo: pd.Timestamp, hi: pd.Timestamp) -> tuple[float, float]:
        bugs = it[
            (it["type"] == "bug") & (it["created_at_src"] > lo) & (it["created_at_src"] <= hi)
        ]
        done = it[(it["done_at"] > lo) & (it["done_at"] <= hi)]
        days = max((hi - lo).days, 1)
        reopen = float(done["reopen_count"].gt(0).mean()) if len(done) else 0.0
        return len(bugs) / days, reopen

    bug_now, reopen_now = rate(now - timedelta(days=28), now)
    bug_base, reopen_base = rate(now - timedelta(days=118), now - timedelta(days=28))
    open_reopen = float(
        in_scope.loc[in_scope["status"] != "done", "reopen_count"].gt(0).mean() or 0
    )
    bug_ratio = bug_now / bug_base if bug_base else 1.0
    reopen_ratio = max(reopen_now, open_reopen) / reopen_base if reopen_base else 1.0
    quality = _clip(100 - 15 * max(0.0, bug_ratio - 1) - 15 * max(0.0, reopen_ratio - 1))
    drivers.append(
        {
            "subscore": "quality",
            "label": (
                f"Bug inflow {bug_ratio:.1f}x and reopen rate {reopen_ratio:.1f}x "
                "the 90-day baseline"
            ),
            "value": round(reopen_ratio, 2),
        }
    )

    deps = data.deps
    edges = deps[
        (deps["from_type"] == "work_item")
        & (deps["to_type"] == "work_item")
        & deps["to_id"].isin(in_scope["id"])
    ]
    status = dict(zip(it["id"], it["status"], strict=True))
    open_blockers = edges[edges["from_id"].map(lambda b: status.get(b) != "done")]
    blocker_risk = [risks.get(b, 0.3) for b in set(open_blockers["from_id"])]
    mean_risk = float(np.mean(blocker_risk)) if blocker_risk else 0.0
    dependencies = _clip(100 - 2 * len(open_blockers) - 30 * mean_risk)
    drivers.append(
        {
            "subscore": "dependencies",
            "label": (
                f"{len(open_blockers)} open upstream blockers on launch scope, mean delay risk "
                f"{mean_risk:.0%}"
            ),
            "value": len(open_blockers),
        }
    )

    fb = FeatureBuilder(data)
    team_people = data.people[data.people["team_id"].notna()]
    utils = np.array([fb.utilisation(p, now) for p in team_people["id"]])
    overloaded = int((utils > OVERLOAD_THRESHOLD).sum())
    sig = data.signals
    recent = sig[sig["date"] > (now - timedelta(days=7)).date()]
    sentiment = float(recent["sentiment_index"].mean()) if len(recent) else 0.35
    team = _clip(100 - 120 * float(utils.std()) - 80 * max(0.0, 0.35 - sentiment) - 6 * overloaded)
    drivers.append(
        {
            "subscore": "team",
            "label": (
                f"Utilisation spread {utils.std():.0%}; {overloaded} people above 85%; team "
                f"sentiment {sentiment:.2f}"
            ),
            "value": round(float(utils.std()), 3),
        }
    )

    subs = {
        "schedule": schedule,
        "scope": scope,
        "quality": quality,
        "dependencies": dependencies,
        "team": team,
    }
    score = round(sum(w[k] * subs[k] for k in subs), 1)
    drivers.sort(key=lambda d: subs[d["subscore"]])
    return Health(score, subs, drivers)
