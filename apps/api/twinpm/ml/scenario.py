"""What-if scenarios on top of the Monte Carlo forecaster.

Change types (all validated by the API schema):
  add_scope        {team_id, epic_id, points, items=1, risk?}
  remove_scope     {work_item_ids}
  capacity_change  {team_id, factor}                 e.g. 0.8 = 20% less capacity
  reassign         {work_item_ids, to_person_id}
  date_shift       {days}                            moves the target date
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from twinpm.domain import capacity_points
from twinpm.ml.data import ProgramData
from twinpm.ml.delay import DelayModel
from twinpm.ml.delegation import SPREAD_SPRINTS
from twinpm.ml.features import FeatureBuilder
from twinpm.ml.forecast import (
    DEFAULT_SIMS,
    REASSIGN_EFFICIENCY,
    ForecastInput,
    ForecastResult,
    simulate,
)


@dataclass
class ScenarioResult:
    baseline: ForecastResult
    scenario: ForecastResult
    delta_days: int
    risk_delta: float
    capacity_delta: dict[str, float]
    affected_epics: list[Any]
    narrative: str


def _rescore(
    data: ProgramData,
    model: DelayModel | None,
    fb: FeatureBuilder,
    wid: Any,
    person: Any,
    extra_points: float,
) -> float | None:
    if model is None:
        return None
    now = pd.Timestamp(data.now)
    x = fb.matrix([(wid, now)])
    people = data.people.set_index("id")
    cap = capacity_points(float(people.at[person, "capacity_hours_per_week"]))
    x.loc[0, "assignee_utilisation"] = fb.utilisation(person, now) + extra_points / cap
    x.loc[0, "assignee_on_time_rate_90d"] = fb.on_time_rate(person, now)
    return float(model.predict(x)[0])


def apply_changes(
    data: ProgramData,
    base: ForecastInput,
    changes: list[dict[str, Any]],
    model: DelayModel | None = None,
) -> ForecastInput:
    inp = copy.deepcopy(base)
    items = inp.items
    fb = FeatureBuilder(data)
    people = data.people.set_index("id")
    added: dict[Any, float] = {}
    started_ids = set(data.items.loc[data.items["started_at"].notna(), "id"])
    for ch in changes:
        kind = ch["type"]
        if kind == "capacity_change":
            t = uuid.UUID(str(ch["team_id"]))
            inp.capacity_factor[t] = inp.capacity_factor.get(t, 1.0) * float(ch["factor"])
        elif kind == "date_shift" and inp.target is not None:
            inp.target = inp.target + timedelta(days=int(ch["days"]))
        elif kind == "remove_scope":
            ids = {uuid.UUID(str(w)) for w in ch["work_item_ids"]}
            items = items[~items["id"].isin(ids)]
        elif kind == "add_scope":
            n = max(1, int(ch.get("items", 1)))
            pts = float(ch["points"]) / n
            rows = pd.DataFrame(
                {
                    "id": [uuid.uuid4() for _ in range(n)],
                    "key": [f"NEW-{i + 1}" for i in range(n)],
                    "team_id": [uuid.UUID(str(ch["team_id"]))] * n,
                    "epic_id": [uuid.UUID(str(ch["epic_id"]))] * n,
                    "assignee": [None] * n,
                    "points": [pts] * n,
                    "risk": [float(ch.get("risk", 0.35))] * n,
                    "gate_epic": [None] * n,
                }
            )
            items = pd.concat([items, rows], ignore_index=True)
        elif kind == "reassign":
            to = uuid.UUID(str(ch["to_person_id"]))
            team = people.at[to, "team_id"]
            for w in (uuid.UUID(str(x)) for x in ch["work_item_ids"]):
                mask = items["id"] == w
                if not mask.any():
                    continue
                row = items[mask].iloc[0]
                pts = float(row["points"])
                # Same horizon as the rebalance planner: in-flight work is about half done,
                # backlog spreads over the sprints before launch.
                started = w in started_ids
                load = pts / (2.0 if started else SPREAD_SPRINTS)
                new_risk = _rescore(data, model, fb, w, to, added.get(to, 0.0) + load)
                if row["team_id"] != team:
                    inp.efficiency[w] = REASSIGN_EFFICIENCY
                items.loc[mask, "team_id"] = team
                items.loc[mask, "assignee"] = to
                if new_risk is not None:
                    items.loc[mask, "risk"] = new_risk
                added[to] = added.get(to, 0.0) + load
    inp.items = items.reset_index(drop=True)
    return inp


def run(
    data: ProgramData,
    base: ForecastInput,
    changes: list[dict[str, Any]],
    model: DelayModel | None = None,
    n_sims: int = DEFAULT_SIMS,
    baseline: ForecastResult | None = None,
) -> ScenarioResult:
    baseline = baseline or simulate(base, n_sims)
    inp = apply_changes(data, base, changes, model)
    scen = simulate(inp, n_sims)  # same seed: common random numbers
    delta = (scen.p80 - baseline.p80).days
    if base.target is not None and inp.target is not None:
        delta -= 0  # date_shift moves the target, not the forecast
    b_risk = float(base.items["risk"].mean()) if len(base.items) else 0.0
    s_risk = float(inp.items["risk"].mean()) if len(inp.items) else 0.0
    team_name = data.teams.set_index("id")["name"].to_dict()

    def pts_by_team(df: pd.DataFrame) -> dict[Any, float]:
        return df.groupby("team_id")["points"].sum().to_dict() if len(df) else {}

    bp, sp = pts_by_team(base.items), pts_by_team(inp.items)
    cap_delta = {
        str(team_name.get(t, t)): round(float(sp.get(t, 0) - bp.get(t, 0)), 1)
        for t in set(bp) | set(sp)
        if abs(sp.get(t, 0) - bp.get(t, 0)) > 1e-9
    }
    for t, f in inp.capacity_factor.items():
        if f != base.capacity_factor.get(t, 1.0):
            cap_delta[f"{team_name.get(t, t)} capacity"] = round(f - 1.0, 2)
    affected = sorted(e for e, d in scen.epic_p80.items() if d != baseline.epic_p80.get(e))
    direction = "earlier" if delta < 0 else "later"
    narrative = (
        f"Launch P80 moves {abs(delta)} day{'s' if abs(delta) != 1 else ''} {direction} "
        f"({baseline.p80.isoformat()} to {scen.p80.isoformat()}). Mean delay risk of remaining "
        f"work {'falls' if s_risk < b_risk else 'rises'} from {b_risk:.0%} to {s_risk:.0%}."
    )
    if delta == 0:
        narrative = f"Launch P80 is unchanged at {scen.p80.isoformat()}."
    if scen.on_time_probability is not None:
        narrative += f" On-time probability: {scen.on_time_probability:.0%}."
    return ScenarioResult(
        baseline, scen, delta, round(s_risk - b_risk, 4), cap_delta, affected, narrative
    )


def mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0
