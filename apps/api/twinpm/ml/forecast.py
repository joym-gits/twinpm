"""7.3 Delivery Forecaster: vectorised Monte Carlo over remaining milestone scope.

Model, per simulation (10,000 by default, vectorised with NumPy):

- Remaining scope = open work items in the milestone's epics, grouped into *packets* by
  (team, epic, gate). A packet is gated when its items have an open work-item dependency on
  another epic; it can start only when that whole epic is done.
- Each team's throughput per sprint is bootstrapped from its last N completed sprints, scaled
  by the program allocation and any capacity change, and spent day by day on the team's ready
  packets in priority order (work that gates other epics first).
- Each item adds overrun work with probability equal to its delay risk.
- The milestone completes when every packet is done. P50/P80/P95 are taken over simulations.

The same engine powers the what-if simulator: scenarios change item ownership, team
capacity, scope or the target date and re-run with the same random seed (common random
numbers), so deltas reflect the change, not sampling noise.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from twinpm.domain import PROGRAM_ALLOCATION, SPRINT_DAYS
from twinpm.ml.data import ProgramData
from twinpm.ml.features import FeatureBuilder

MAX_DAYS = 400
DEFAULT_SIMS = 10_000
REASSIGN_EFFICIENCY = 0.85  # ramp-up cost when work moves to another team


@dataclass
class ForecastInput:
    """Remaining work and per-team capacity, ready for simulation."""

    items: pd.DataFrame  # id, key, team_id, epic_id, points, risk, gate_epic
    throughput: dict[Any, list[float]]  # team -> completed points per recent sprint
    capacity_factor: dict[Any, float] = field(default_factory=dict)
    gating_epics: set[Any] = field(default_factory=set)
    start: date = field(default_factory=date.today)
    target: date | None = None
    efficiency: dict[Any, float] = field(default_factory=dict)  # item id -> work multiplier


@dataclass
class ForecastResult:
    p50: date
    p80: date
    p95: date
    histogram: list[dict[str, Any]]
    epic_p80: dict[str, date]
    on_time_probability: float | None
    assumptions: dict[str, Any]
    days: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))

    def as_dict(self) -> dict[str, Any]:
        return {
            "p50": self.p50.isoformat(),
            "p80": self.p80.isoformat(),
            "p95": self.p95.isoformat(),
            "histogram": self.histogram,
            "epic_p80": {k: v.isoformat() for k, v in self.epic_p80.items()},
            "on_time_probability": self.on_time_probability,
            "assumptions": self.assumptions,
        }


def gating(data: ProgramData) -> tuple[dict[Any, Any], set[Any]]:
    """Map open items to the epic their open blockers belong to; return the gating epics."""
    deps, items = data.deps, data.items
    item_edges = deps[(deps["from_type"] == "work_item") & (deps["to_type"] == "work_item")]
    epic_of = dict(zip(items["id"], items["epic_id"], strict=True))
    status = dict(zip(items["id"], items["status"], strict=True))
    gate: dict[Any, Any] = {}
    for f, t in zip(item_edges["from_id"], item_edges["to_id"], strict=True):
        if status.get(f) != "done" and status.get(t) != "done" and f in epic_of:
            gate[t] = epic_of[f]
    return gate, set(gate.values())


def build_input(
    data: ProgramData,
    milestone_id: Any,
    risks: dict[Any, float],
    n_sprints: int = 6,
    scope: set[Any] | None = None,
    target: date | None = None,
) -> ForecastInput:
    """Remaining work for a milestone (or an explicit epic scope, e.g. for backtests)."""
    if scope is None:
        ms = data.milestones.set_index("id").loc[milestone_id]
        scope = {uuid.UUID(str(e)) for e in ms["scope"]}
        target = ms["target_date"]
    items = data.items[(data.items["status"] != "done") & data.items["epic_id"].isin(scope)]
    gate, gating_epics = gating(data)
    df = pd.DataFrame(
        {
            "id": items["id"].values,
            "key": items["key"].values,
            "team_id": items["team_id"].values,
            "epic_id": items["epic_id"].values,
            "assignee": items["assignee_person_id"].values,
            "points": items["story_points"].astype(float).values,
            "risk": [risks.get(w, 0.25) for w in items["id"]],
            "gate_epic": [gate.get(w) for w in items["id"]],
        }
    )
    fb = FeatureBuilder(data)
    now = pd.Timestamp(data.now)
    throughput = {t: fb.sprint_velocities(t, now, n_sprints) or [20.0] for t in data.teams["id"]}
    return ForecastInput(
        df,
        throughput,
        gating_epics=gating_epics & set(df["epic_id"]),
        start=data.today,
        target=target,
    )


def simulate(inp: ForecastInput, n_sims: int = DEFAULT_SIMS, seed: int = 7) -> ForecastResult:
    rng = np.random.default_rng(seed)
    items = inp.items.reset_index(drop=True)
    teams = sorted({*inp.throughput} | set(items["team_id"]), key=str)
    if items.empty:
        d = inp.start
        return ForecastResult(d, d, d, [], {}, 1.0, {"remaining_items": 0}, np.zeros(n_sims))
    # Work per item: points, plus overrun with probability = delay risk.
    eff = np.array([inp.efficiency.get(w, 1.0) for w in items["id"]])
    pts = items["points"].to_numpy() / eff
    late = rng.random((n_sims, len(items))) < items["risk"].to_numpy()
    overrun = late * pts * rng.uniform(0.5, 1.0, (n_sims, len(items)))
    work = pts + overrun
    # Packets: (team, epic, gate) with priority: gating epics first, then ungated, then gated.
    keys = list(zip(items["team_id"], items["epic_id"], items["gate_epic"], strict=True))
    packets = sorted(
        set(keys), key=lambda k: (k[2] is not None, k[1] not in inp.gating_epics, str(k[1]))
    )
    pidx = {k: i for i, k in enumerate(packets)}
    rem = np.zeros((n_sims, len(packets)))
    for j, k in enumerate(keys):
        rem[:, pidx[k]] += work[:, j]
    done_day = np.full((n_sims, len(packets)), np.inf)
    done_day[rem <= 0] = 0
    epic_packets: dict[Any, list[int]] = {}
    for k, i in pidx.items():
        epic_packets.setdefault(k[1], []).append(i)
    team_packets = {t: [pidx[k] for k in packets if k[0] == t] for t in teams}
    # Throughput: bootstrap one historical sprint per simulated sprint.
    n_sp = MAX_DAYS // SPRINT_DAYS + 1
    daily: dict[Any, np.ndarray] = {}
    for t in teams:
        history = np.array(inp.throughput.get(t) or [20.0], dtype=float)
        draws = rng.choice(history, size=(n_sims, n_sp))
        factor = PROGRAM_ALLOCATION * inp.capacity_factor.get(t, 1.0)
        daily[t] = np.repeat(draws * factor / SPRINT_DAYS, SPRINT_DAYS, axis=1)
    gate_open_day = {e: np.zeros(n_sims) for e in {k[2] for k in packets if k[2] is not None}}
    for day in range(MAX_DAYS):
        for e in gate_open_day:
            ps = epic_packets.get(e)
            gate_open_day[e] = done_day[:, ps].max(axis=1) if ps else np.zeros(n_sims)
        for t in teams:
            cap = daily[t][:, day].copy()
            for i in team_packets[t]:
                g = packets[i][2]
                active = rem[:, i] > 0
                if g is not None:
                    active &= gate_open_day[g] <= day
                take = np.where(active, np.minimum(rem[:, i], cap), 0.0)
                rem[:, i] -= take
                cap -= take
                finished = active & (rem[:, i] <= 1e-9) & np.isinf(done_day[:, i])
                done_day[finished, i] = day + 1
        if not np.isinf(done_day).any():
            break
    done_day[np.isinf(done_day)] = MAX_DAYS
    finish = done_day.max(axis=1)
    p50, p80, p95 = (int(np.ceil(np.percentile(finish, q))) for q in (50, 80, 95))
    start = inp.start
    counts, edges = np.histogram(finish, bins=min(30, max(5, int(finish.max() - finish.min()))))
    hist = [
        {"date": (start + timedelta(days=int(edges[i]))).isoformat(), "count": int(c)}
        for i, c in enumerate(counts)
    ]
    epic_p80 = {
        str(e): start + timedelta(days=int(np.ceil(np.percentile(done_day[:, ps].max(axis=1), 80))))
        for e, ps in epic_packets.items()
    }
    on_time = None
    if inp.target is not None:
        on_time = round(float((finish <= (inp.target - start).days).mean()), 3)
    return ForecastResult(
        start + timedelta(days=p50),
        start + timedelta(days=p80),
        start + timedelta(days=p95),
        hist,
        epic_p80,
        on_time,
        {
            "simulations": n_sims,
            "remaining_items": len(items),
            "remaining_points": round(float(pts.sum()), 1),
            "expected_overrun_points": round(float(overrun.mean(axis=0).sum()), 1),
            "program_allocation": PROGRAM_ALLOCATION,
            "throughput_sprints": {
                str(t): [round(v, 1) for v in inp.throughput.get(t, [])] for t in teams
            },
            "capacity_factor": {str(t): v for t, v in inp.capacity_factor.items()},
            "gated_items": int(items["gate_epic"].notna().sum()),
        },
        finish,
    )


def critical_epics(data: ProgramData, inp: ForecastInput) -> set[Any]:
    """Epics other launch work waits on: gating epics plus open epic-level blockers of them."""
    deps = data.deps
    edges = deps[
        (deps["from_type"] == "epic") & (deps["to_type"] == "epic") & (deps["status"] == "open")
    ]
    open_epics = set(inp.items["epic_id"])
    crit = set(inp.gating_epics)
    for f, t in zip(edges["from_id"], edges["to_id"], strict=True):
        if t in inp.gating_epics and f in open_epics:
            crit.add(f)
    return crit
