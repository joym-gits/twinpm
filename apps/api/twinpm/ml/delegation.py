"""7.6 Delegation Ranker and rebalance planner.

score = w1*skill_match + w2*availability + w3*throughput_on_similar + w4*growth_alignment
        + w5*context_continuity - penalty(over_allocation, pto_overlap)

Inputs are work signals only. Protected attributes (name, gender, age, nationality, timezone,
...) are never features; `FEATURE_NAMES` is asserted against `PROTECTED` in the tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from twinpm.domain import OVERLOAD_THRESHOLD, capacity_points
from twinpm.ml.data import ProgramData
from twinpm.ml.features import FeatureBuilder

DEFAULT_WEIGHTS: dict[str, float] = {
    "skill_match": 0.35,
    "availability": 0.25,
    "throughput_similar": 0.15,
    "growth_alignment": 0.10,
    "context_continuity": 0.15,
}
FEATURE_NAMES = (*DEFAULT_WEIGHTS, "over_allocation", "pto_overlap")
WEIGHT_BOUND = 0.30
SPREAD_SPRINTS = 4.0
MIN_SCORE = 0.35  # preference learning may move each weight by at most +-30%

# Keyword -> skills, used to infer a task's required skills from labels and text.
SKILL_KEYWORDS: dict[str, dict[str, float]] = {
    "payments-api": {"api-design": 0.7, "go": 0.6, "payments-compliance": 0.5},
    "payments": {"payments-compliance": 1.0, "go": 0.4},
    "backend": {"go": 0.8, "postgres": 0.6},
    "api": {"api-design": 0.8},
    "endpoint": {"api-design": 0.6, "go": 0.5},
    "schema": {"api-design": 0.5, "postgres": 0.5},
    "idempot": {"postgres": 1.0, "go": 0.5},
    "ledger": {"postgres": 0.8, "payments-compliance": 0.6},
    "refund": {"payments-compliance": 0.6, "api-design": 0.4},
    "mobile": {"react-native": 1.0},
    "checkout": {"react-native": 0.5},
    "ios": {"ios": 1.0},
    "apple": {"ios": 0.8},
    "android": {"android": 1.0},
    "google pay": {"android": 0.8},
    "kafka": {"kafka": 1.0},
    "consumer": {"kafka": 0.6},
    "observability": {"observability": 1.0},
    "trace": {"observability": 0.8},
    "slo": {"observability": 0.6},
    "alert": {"observability": 0.5},
    "rate": {"go": 0.6, "k8s": 0.4},
    "redis": {"k8s": 0.4},
    "platform": {"k8s": 0.5, "go": 0.4},
    "fraud": {"kafka": 0.5, "go": 0.5},
    "auth": {"oauth": 0.8},
    "token": {"oauth": 0.5},
    "export": {"python": 0.7, "postgres": 0.5},
    "data": {"postgres": 0.6, "python": 0.4},
    "postgres": {"postgres": 1.0},
    "migration": {"postgres": 0.7},
}


def required_skills(text: str, labels: list[str]) -> dict[str, float]:
    hay = f"{' '.join(labels)} {text}".lower()
    req: dict[str, float] = {}
    for kw, skills in SKILL_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}", hay):
            for s, w in skills.items():
                req[s] = max(req.get(s, 0.0), w)
    return req


def bounded_weights(learned: dict[str, float] | None) -> dict[str, float]:
    out = dict(DEFAULT_WEIGHTS)
    for k, base in DEFAULT_WEIGHTS.items():
        if learned and k in learned:
            out[k] = float(
                np.clip(learned[k], base * (1 - WEIGHT_BOUND), base * (1 + WEIGHT_BOUND))
            )
    return out


@dataclass
class Candidate:
    person_id: Any
    name: str
    team_id: Any
    score: float
    factors: dict[str, float]
    explanation: str
    utilisation: float


@dataclass
class Ranker:
    data: ProgramData
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    extra_load: dict[Any, float] = field(default_factory=dict)  # planned points per person

    def __post_init__(self) -> None:
        d = self.data
        self.fb = FeatureBuilder(d)
        self.now = pd.Timestamp(d.now)
        skills = d.skills.set_index("id")["name"]
        self.skill_vec: dict[Any, dict[str, float]] = {}
        for r in d.person_skills.itertuples():
            self.skill_vec.setdefault(r.person_id, {})[skills[r.skill_id]] = r.level / 5.0
        self.people = d.people[d.people["team_id"].notna()].set_index("id", drop=False)
        self.epic_title = d.epics.set_index("id")["title"].to_dict()
        self.team_name = d.teams.set_index("id")["name"].to_dict()
        horizon = self.now.date() + timedelta(days=14)
        self.pto = {
            r.person_id
            for r in d.time_off.itertuples()
            if r.start_date <= horizon and r.end_date >= self.now.date()
        }
        self.util = {pid: self.fb.utilisation(pid, self.now) for pid in self.people.index}

    def utilisation(self, pid: Any) -> float:
        cap = capacity_points(float(self.people.at[pid, "capacity_hours_per_week"]))
        return self.util.get(pid, 0.0) + self.extra_load.get(pid, 0.0) / cap

    def _cycle(self, pid: Any, epic_id: Any) -> tuple[float | None, float | None]:
        it = self.data.items
        done = it[it["done_at"].notna() & (it["epic_id"] == epic_id)]
        if done.empty:
            return None, None
        ct = (
            (done["done_at"] - done["started_at"]).dt.total_seconds()
            / 86400
            / done["story_points"].clip(lower=1)
        )
        mine = ct[done["assignee_person_id"] == pid]
        return (float(mine.median()) if len(mine) else None), float(ct.median())

    def factors(self, item: pd.Series, pid: Any) -> dict[str, float]:
        labels = (
            list(item["labels"]) if isinstance(item["labels"], list | tuple | np.ndarray) else []
        )
        epic = self.epic_title.get(item["epic_id"], "")
        req = required_skills(f"{item['title']} {epic}", labels)
        have = self.skill_vec.get(pid, {})
        keys = sorted(set(req) | set(have))
        a = np.array([req.get(k, 0.0) for k in keys])
        b = np.array([have.get(k, 0.0) for k in keys])
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        skill = float(a @ b / denom) if denom else 0.0
        util = self.utilisation(pid)
        mine, team = self._cycle(pid, item["epic_id"])
        throughput = 0.5 if mine is None or team is None else float(np.clip(team / mine, 0, 2) / 2)
        goals = " ".join(self.people.at[pid, "growth_goals"] or []).lower()
        domain = f"{' '.join(labels)} {epic} {self.team_name.get(item['team_id'], '')}".lower()
        growth = float(
            any(g in domain for g in goals.split() if len(g) > 3)
            or any(g in req for g in goals.split())
        )
        it = self.data.items
        recent = it[
            (it["assignee_person_id"] == pid)
            & (it["created_at_src"] > self.now - pd.Timedelta(days=60))
        ]
        context = float((recent["epic_id"] == item["epic_id"]).any())
        cap = capacity_points(float(self.people.at[pid, "capacity_hours_per_week"]))
        # In-flight work is about half done; unstarted work spreads over the sprints ahead.
        horizon = 2.0 if pd.notna(item.get("started_at")) else SPREAD_SPRINTS
        over = max(0.0, util + float(item["story_points"]) / (cap * horizon) - 1.0)
        return {
            "skill_match": round(skill, 3),
            "availability": round(float(np.clip(1 - util, 0, 1)), 3),
            "throughput_similar": round(throughput, 3),
            "growth_alignment": growth,
            "context_continuity": context,
            "over_allocation": round(over, 3),
            "pto_overlap": float(pid in self.pto),
        }

    def score(self, f: dict[str, float]) -> float:
        s = sum(self.weights[k] * f[k] for k in DEFAULT_WEIGHTS)
        return round(s - 0.5 * f["over_allocation"] - 0.2 * f["pto_overlap"], 4)

    @staticmethod
    def explain(name: str, f: dict[str, float]) -> str:
        parts = []
        if f["skill_match"] >= 0.6:
            parts.append(f"strong skill match ({f['skill_match']:.0%})")
        parts.append(f"{f['availability']:.0%} spare capacity")
        if f["growth_alignment"]:
            parts.append("it fits their growth goals")
        if f["context_continuity"]:
            parts.append("already works on this epic")
        if f["over_allocation"] > 0:
            parts.append(f"but would be {f['over_allocation']:.0%} over capacity")
        if f["pto_overlap"]:
            parts.append("has PTO in the next two weeks")
        return f"{name}: " + ", ".join(parts) + "."

    def rank(self, item: pd.Series, top: int = 5) -> list[Candidate]:
        out = []
        for pid in self.people.index:
            if pid == item["assignee_person_id"]:
                continue
            f = self.factors(item, pid)
            name = str(self.people.at[pid, "name"])
            out.append(
                Candidate(
                    pid,
                    name,
                    self.people.at[pid, "team_id"],
                    self.score(f),
                    f,
                    self.explain(name, f),
                    round(self.utilisation(pid), 3),
                )
            )
        out.sort(key=lambda c: -c.score)
        return out[:top]


@dataclass
class Move:
    work_item_id: Any
    key: str
    title: str
    from_person_id: Any
    to_person_id: Any
    to_name: str
    to_team_id: Any
    points: float
    risk: float
    candidate: Candidate


def plan_rebalance(
    data: ProgramData,
    risks: dict[Any, float],
    critical_epics: set[Any] | None = None,
    weights: dict[str, float] | None = None,
    min_risk: float = 0.35,
    max_moves: int = 8,
    headroom: float = 0.85,
) -> list[Move]:
    """Move critical-path and overloaded-owner work to people with headroom.

    Pool: open, not-in-review items on the critical epics, plus anything owned by someone
    above the overload threshold, ordered by delay risk. Each item goes to the best-ranked
    person below `headroom` utilisation who stays within capacity over the next two sprints.
    """
    ranker = Ranker(data, bounded_weights(weights))
    it = data.items[data.items["status"].isin(["todo", "in_progress", "blocked"])]
    overloaded = {p for p, u in ranker.util.items() if u > OVERLOAD_THRESHOLD}
    critical = it["epic_id"].isin(critical_epics or set())
    pool = it[critical | it["assignee_person_id"].isin(overloaded)]
    pool = pool.assign(risk=pool["id"].map(lambda w: risks.get(w, 0.0)))
    pool = pool[(pool["risk"] >= min_risk) | pool["assignee_person_id"].isin(overloaded)]
    epic_team = data.epics.set_index("id")["team_id"].to_dict()
    bottleneck = {epic_team.get(e) for e in critical_epics or set()}
    pool = pool.assign(critical=pool["epic_id"].isin(critical_epics or set()))
    pool = pool.sort_values(["critical", "risk", "story_points"], ascending=[False, False, False])
    moves: list[Move] = []
    for _, item in pool.iterrows():
        if len(moves) >= max_moves:
            break
        owner = item["assignee_person_id"]
        pts = float(item["story_points"])
        # In-flight work lands in this sprint; backlog spreads over the sprints before launch.
        spread = 2.0 if pd.notna(item["started_at"]) else SPREAD_SPRINTS  # in-flight: ~half left
        cands = []
        on_critical = bool(critical_epics) and item["epic_id"] in (critical_epics or set())
        for c in ranker.rank(item, top=len(ranker.people)):
            if c.person_id in overloaded:
                continue
            # Moving critical work within the bottleneck team adds no capacity to it.
            if on_critical and c.team_id == item["team_id"]:
                continue
            # Never push extra work into the bottleneck team from elsewhere.
            if c.team_id in bottleneck and c.team_id != item["team_id"]:
                continue
            cap = capacity_points(float(ranker.people.at[c.person_id, "capacity_hours_per_week"]))
            if (
                c.utilisation < headroom
                and c.factors["pto_overlap"] == 0
                and c.factors["skill_match"] >= 0.4
                and ranker.utilisation(c.person_id) + pts / (spread * cap) <= 1.0
            ):
                cands.append(c)
        if not cands or cands[0].score < MIN_SCORE:
            continue
        best = cands[0]
        ranker.extra_load[best.person_id] = (
            ranker.extra_load.get(best.person_id, 0.0) + pts / spread
        )
        if pd.notna(owner) and owner in ranker.people.index:
            ranker.extra_load[owner] = ranker.extra_load.get(owner, 0.0) - pts
        moves.append(
            Move(
                item["id"],
                str(item["key"]),
                str(item["title"]),
                owner,
                best.person_id,
                best.name,
                best.team_id,
                pts,
                float(item["risk"]),
                best,
            )
        )
    return moves
