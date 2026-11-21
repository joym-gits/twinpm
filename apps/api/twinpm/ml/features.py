"""As-of feature builders for the delay-risk classifier.

Every feature is computed from data visible at time `t` (events at or before `t`), so the same
code builds leakage-free training snapshots from history and live features for open items.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from twinpm.domain import SPRINT_DAYS, capacity_points
from twinpm.ml.data import ProgramData

STATUSES = ("todo", "in_progress", "in_review", "blocked")
TYPES = ("story", "task", "bug", "spike")
NUMERIC = (
    "age_days",
    "days_in_current_status",
    "story_points",
    "reopen_count",
    "pr_review_hours",
    "pr_review_ratio",
    "team_review_ratio",
    "open_blocker_count",
    "upstream_dependency_risk",
    "assignee_utilisation",
    "assignee_on_time_rate_90d",
    "team_velocity_trend",
    "comments_count",
    "days_to_due",
    "elapsed_vs_plan",
)
FEATURES: tuple[str, ...] = (
    *NUMERIC,
    *(f"status_{s}" for s in STATUSES),
    *(f"type_{t}" for t in TYPES),
)
# Protected attributes must never be model inputs (see tests/test_ml_fairness.py).
PROTECTED = ("name", "gender", "age", "nationality", "ethnicity", "timezone", "religion")

DAY = 86400.0


def _days(a: datetime | pd.Timestamp, b: datetime | pd.Timestamp) -> float:
    return float((pd.Timestamp(a) - pd.Timestamp(b)).total_seconds() / DAY)


@dataclass(frozen=True)
class _Ev:
    t: pd.Timestamp
    kind: str
    to: str | None


class FeatureBuilder:
    def __init__(self, data: ProgramData) -> None:
        self.data = data
        items = data.items
        self.items = items.set_index("id", drop=False)
        self.events: dict[Any, list[_Ev]] = defaultdict(list)
        ev = data.events.sort_values("occurred_at")
        for wid, t, kind, to in zip(
            ev["work_item_id"], ev["occurred_at"], ev["event_type"], ev["to_value"], strict=True
        ):
            self.events[wid].append(_Ev(t, kind, to))
        deps = data.deps
        wd = deps[(deps["from_type"] == "work_item") & (deps["to_type"] == "work_item")]
        self.blockers: dict[Any, list[Any]] = defaultdict(list)
        for f, to in zip(wd["from_id"], wd["to_id"], strict=True):
            self.blockers[to].append(f)
        self.sprint_start = {
            r.id: pd.Timestamp(r.start_date, tz="UTC") for r in data.sprints.itertuples()
        }
        self.sprint_starts = sorted({*self.sprint_start.values()})
        self.capacity = {
            r.id: capacity_points(float(r.capacity_hours_per_week))
            for r in data.people.itertuples()
        }
        self.by_assignee: dict[Any, pd.DataFrame] = dict(list(items.groupby("assignee_person_id")))
        self.by_team: dict[Any, pd.DataFrame] = dict(list(items.groupby("team_id")))
        self._review_norm: dict[tuple[Any, int], float] = {}

    # ----------------------------------------------------------------- primitives
    def status_at(self, wid: Any, t: pd.Timestamp) -> tuple[str, pd.Timestamp | None]:
        status, since = "todo", None
        for e in self.events.get(wid, ()):
            if e.t > t:
                break
            if e.kind == "status_change" and e.to:
                status, since = e.to, e.t
        return status, since

    def is_done_at(self, wid: Any, t: pd.Timestamp) -> bool:
        done = self.items.at[wid, "done_at"]
        return bool(pd.notna(done) and done <= t)

    def review_hours_at(self, wid: Any, t: pd.Timestamp) -> float:
        hours, opened = 0.0, None
        for e in self.events.get(wid, ()):
            if e.t > t:
                break
            if e.kind == "pr_opened":
                opened = e.t
            elif e.kind == "pr_reviewed":
                hours += float(e.to or 0)
                opened = None
        if opened is not None:
            hours += _days(t, opened) * 24
        return hours

    def count_at(self, wid: Any, kind: str, t: pd.Timestamp, to: str | None = None) -> int:
        return sum(
            1
            for e in self.events.get(wid, ())
            if e.t <= t and e.kind == kind and (to is None or e.to == to)
        )

    def sprint_start_at(self, t: pd.Timestamp) -> pd.Timestamp | None:
        for s in reversed(self.sprint_starts):
            if s <= t < s + timedelta(days=SPRINT_DAYS):
                return s
        return None

    def utilisation(self, person: Any, t: pd.Timestamp) -> float:
        """(Points in the sprint containing t + open carry-over) / sprint capacity."""
        if person is None or pd.isna(person) or person not in self.capacity:
            return 0.0
        start = self.sprint_start_at(t)
        g = self.by_assignee.get(person)
        if start is None or g is None:
            return 0.0
        pts = 0.0
        for sid, p, created, done in zip(
            g["sprint_id"], g["story_points"], g["created_at_src"], g["done_at"], strict=True
        ):
            if sid is None or pd.isna(sid) or created > t:
                continue
            s = self.sprint_start[sid]
            if s == start or (s < start and (pd.isna(done) or done > start)):
                pts += float(p)
        return pts / self.capacity[person]

    def on_time_rate(self, person: Any, t: pd.Timestamp, days: int = 90) -> float:
        g = self.by_assignee.get(person)
        if g is None:
            return 0.7
        done = g[(g["done_at"] <= t) & (g["done_at"] > t - timedelta(days=days))]
        if done.empty:
            return 0.7
        late = done["done_at"].dt.date > done["due_date"]
        return float(1 - late.mean())

    def completed_points(self, team: Any, lo: pd.Timestamp, hi: pd.Timestamp) -> float:
        g = self.by_team.get(team)
        if g is None:
            return 0.0
        return float(g.loc[(g["done_at"] >= lo) & (g["done_at"] < hi), "story_points"].sum())

    def sprint_velocities(self, team: Any, t: pd.Timestamp, n: int = 6) -> list[float]:
        """Completed points of the last `n` sprints that ended at or before t, oldest first."""
        ended = [s for s in self.sprint_starts if s + timedelta(days=SPRINT_DAYS) <= t][-n:]
        return [self.completed_points(team, s, s + timedelta(days=SPRINT_DAYS)) for s in ended]

    def velocity_trend(self, team: Any, t: pd.Timestamp) -> float:
        v = self.sprint_velocities(team, t, 6)
        if len(v) < 3 or np.mean(v) == 0:
            return 1.0
        return float(np.mean(v[-2:]) / np.mean(v))

    def review_norm(self, team: Any, t: pd.Timestamp) -> float:
        """Team's median PR review wait over the 90 days before the storyline window."""
        key = (team, int(t.timestamp() // (7 * DAY)))
        if key not in self._review_norm:
            g = self.by_team.get(team)
            vals: list[float] = []
            if g is not None:
                lo, hi = t - timedelta(days=120), t - timedelta(days=30)
                for wid in g.loc[(g["done_at"] > lo) & (g["done_at"] <= hi), "id"]:
                    vals += [
                        float(e.to or 0)
                        for e in self.events.get(wid, ())
                        if e.kind == "pr_reviewed"
                    ]
            self._review_norm[key] = float(np.median(vals)) if vals else 8.0
        return self._review_norm[key]

    def team_review_recent(self, team: Any, t: pd.Timestamp, days: int = 14) -> float:
        """Median PR review wait for the team's reviews completed in the last `days`."""
        g = self.by_team.get(team)
        if g is None:
            return 8.0
        lo = t - timedelta(days=days)
        vals = [
            float(e.to or 0)
            for wid in g.loc[
                (g["started_at"] <= t) & ((g["done_at"].isna()) | (g["done_at"] > lo)), "id"
            ]
            for e in self.events.get(wid, ())
            if e.kind == "pr_reviewed" and lo < e.t <= t
        ]
        return float(np.median(vals)) if vals else self.review_norm(team, t)

    @staticmethod
    def elapsed_vs_plan(r: Any, t: pd.Timestamp) -> float:
        """Share of the planned start-to-due window already used (0 if not started)."""
        start, due = r["started_at"], r["due_date"]
        if pd.isna(start) or start > t or due is None or pd.isna(due):
            return 0.0
        planned = max(_days(pd.Timestamp(due, tz="UTC"), start), 0.5)
        return _days(t, start) / planned

    def upstream_risk(self, wid: Any, t: pd.Timestamp) -> float:
        risk = 0.0
        for b in self.blockers.get(wid, ()):
            if b not in self.items.index or self.is_done_at(b, t):
                continue
            due = self.items.at[b, "due_date"]
            overdue = due is not None and pd.notna(due) and t.date() > due
            risk = max(risk, 1.0 if overdue else 0.5)
        return risk

    # ----------------------------------------------------------------- features
    def features(self, wid: Any, t: pd.Timestamp) -> dict[str, float]:
        r = self.items.loc[wid]
        status, since = self.status_at(wid, t)
        status = status if status in STATUSES else "in_review"
        review = self.review_hours_at(wid, t)
        norm = self.review_norm(r["team_id"], t)
        open_blockers = sum(
            1
            for b in self.blockers.get(wid, ())
            if b in self.items.index and not self.is_done_at(b, t)
        )
        due = r["due_date"]
        f = {
            "age_days": _days(t, r["created_at_src"]),
            "days_in_current_status": _days(t, since if since is not None else r["created_at_src"]),
            "story_points": float(r["story_points"]),
            "reopen_count": float(self.count_at(wid, "reopened", t)),
            "pr_review_hours": review,
            "pr_review_ratio": review / norm if norm else 0.0,
            "team_review_ratio": self.team_review_recent(r["team_id"], t) / norm if norm else 1.0,
            "open_blocker_count": float(
                open_blockers + self.count_at(wid, "status_change", t, "blocked")
            ),
            "upstream_dependency_risk": self.upstream_risk(wid, t),
            "assignee_utilisation": self.utilisation(r["assignee_person_id"], t),
            "assignee_on_time_rate_90d": self.on_time_rate(r["assignee_person_id"], t),
            "team_velocity_trend": self.velocity_trend(r["team_id"], t),
            "comments_count": float(self.count_at(wid, "comment", t)),
            "days_to_due": _days(pd.Timestamp(due, tz="UTC"), t) if pd.notna(due) else 60.0,
            "elapsed_vs_plan": self.elapsed_vs_plan(r, t),
        }
        for s in STATUSES:
            f[f"status_{s}"] = float(status == s)
        for ty in TYPES:
            f[f"type_{ty}"] = float(r["type"] == ty)
        return f

    def matrix(self, rows: list[tuple[Any, pd.Timestamp]]) -> pd.DataFrame:
        return pd.DataFrame([self.features(w, t) for w, t in rows], columns=list(FEATURES))


def training_snapshots(fb: FeatureBuilder) -> tuple[pd.DataFrame, np.ndarray, list[pd.Timestamp]]:
    """Snapshots of items while they were still open, labelled late (1) or on time (0).

    Labels are known for finished items, and for open items already past their due date
    (definitely late). Open items not yet due are censored and excluded, which avoids biasing
    recent history toward quick items.
    """
    now = pd.Timestamp(fb.data.now)
    rows: list[tuple[Any, pd.Timestamp]] = []
    labels: list[int] = []
    for r in fb.items.itertuples():
        if pd.isna(r.started_at) or r.due_date is None:
            continue
        if pd.notna(r.done_at):
            late, end = int(r.done_at.date() > r.due_date), r.done_at
        elif r.due_date < now.date():
            late, end = 1, now
        else:
            continue
        due = pd.Timestamp(r.due_date, tz="UTC")
        planned = max(_days(due, r.started_at), 0.5)
        # Only in-flight snapshots: before work starts the causes of delay are not yet
        # observable (unstarted items are scored from team history instead).
        snaps = [r.started_at + timedelta(days=planned * f) for f in (0.3, 0.55, 0.8)]
        for t in snaps:
            if t < end:
                rows.append((r.id, t))
                labels.append(late)
    return fb.matrix(rows), np.array(labels), [t for _, t in rows]


LABELS = {
    "assignee_utilisation": lambda f, c: f"Owner at {f:.0%} utilisation",
    "pr_review_ratio": lambda f, c: f"PR review time {f:.1f}x the team norm",
    "team_review_ratio": lambda f, c: f"Team review latency {f:.1f}x its norm",
    "pr_review_hours": lambda f, c: f"PRs waited {f:.0f}h for review",
    "reopen_count": lambda f, c: f"{int(f)} reopen{'s' if f != 1 else ''} after review",
    "open_blocker_count": lambda f, c: f"{int(f)} blocker{'s' if f != 1 else ''} encountered",
    "upstream_dependency_risk": lambda f, c: (
        "Upstream dependency still open" + (" and overdue" if f >= 1 else "")
    ),
    "team_velocity_trend": lambda f, c: f"Team velocity at {f:.0%} of its 6-sprint mean",
    "assignee_on_time_rate_90d": lambda f, c: f"Owner on-time rate {f:.0%} (90 days)",
    "days_to_due": lambda f, c: f"Due in {f:.0f} days" if f >= 0 else f"{-f:.0f} days overdue",
    "days_in_current_status": lambda f, c: f"{f:.0f} days in current status",
    "age_days": lambda f, c: f"Open for {f:.0f} days",
    "elapsed_vs_plan": lambda f, c: f"{f:.0%} of the planned time used",
    "story_points": lambda f, c: f"{f:.0f} story points",
    "comments_count": lambda f, c: f"{f:.0f} comments",
}


def label_for(feature: str, value: float) -> str:
    if feature.startswith("status_"):
        return f"Status: {feature.removeprefix('status_').replace('_', ' ')}"
    if feature.startswith("type_"):
        return f"Type: {feature.removeprefix('type_')}"
    fn = LABELS.get(feature)
    return fn(value, None) if fn else f"{feature} = {value:.2f}"
