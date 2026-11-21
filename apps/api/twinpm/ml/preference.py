"""7.7 Preference model: per-user logistic re-ranker with a global prior, and weight nudging."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from twinpm.ml.delegation import DEFAULT_WEIGHTS, WEIGHT_BOUND

TYPES = (
    "reassign",
    "create_task",
    "status_report",
    "risk_update",
    "nudge",
    "roadmap_change",
    "scenario",
    "alert",
)
MIN_USER_EVENTS = 8
ACCEPTED = ("accepted", "edited", "auto_executed")


def context_features(
    s_type: str,
    level: int,
    n_drivers: int,
    n_citations: int,
    max_contribution: float,
    risk: float | None = None,
) -> dict[str, float]:
    f = {f"type_{t}": float(s_type == t) for t in TYPES}
    f.update(
        level=float(level),
        n_drivers=float(n_drivers),
        n_citations=float(n_citations),
        max_contribution=float(max_contribution),
        risk=float(risk or 0.0),
    )
    return f


FEATURES = tuple(context_features("alert", 1, 0, 0, 0.0))


@dataclass
class PreferenceModel:
    prior: dict[str, float]  # acceptance rate by type (smoothed), all users
    clf: LogisticRegression | None = None
    n_events: int = 0
    by_type: dict[str, dict[str, float]] = field(default_factory=dict)

    def accept_probability(self, features: dict[str, float]) -> float:
        s_type = next((t for t in TYPES if features.get(f"type_{t}")), "alert")
        prior = self.prior.get(s_type, 0.6)
        if self.clf is None:
            return prior
        x = np.array([[features.get(k, 0.0) for k in FEATURES]])
        p = float(self.clf.predict_proba(x)[0, 1])
        w = min(1.0, self.n_events / (4 * MIN_USER_EVENTS))  # shrink toward the prior
        return w * p + (1 - w) * prior


def fit(events: pd.DataFrame, user_id: Any | None = None) -> PreferenceModel:
    """events: user_id, suggestion_type, context_features (dict), outcome."""
    if events.empty:
        return PreferenceModel(dict.fromkeys(TYPES, 0.6))
    y_all = events["outcome"].isin(ACCEPTED).astype(int)
    prior = {}
    by_type = {}
    for t in TYPES:
        m = events["suggestion_type"] == t
        prior[t] = float((y_all[m].sum() + 3) / (m.sum() + 5))  # Beta(3, 2) smoothing
        if m.any():
            by_type[t] = {"seen": int(m.sum()), "accept_rate": round(float(y_all[m].mean()), 3)}
    mine = events if user_id is None else events[events["user_id"] == user_id]
    clf = None
    if len(mine) >= MIN_USER_EVENTS and mine["outcome"].isin(ACCEPTED).nunique() == 2:
        x = np.array([[cf.get(k, 0.0) for k in FEATURES] for cf in mine["context_features"]])
        clf = LogisticRegression(C=1.0, max_iter=500).fit(x, mine["outcome"].isin(ACCEPTED))
    return PreferenceModel(prior, clf, len(mine), by_type)


def nudge_weights(events: pd.DataFrame, lr: float = 0.5) -> dict[str, float]:
    """Shift delegation weights toward factors that distinguish accepted reassignments.

    Each weight moves by lr * (mean factor | accepted - mean factor | rejected), bounded to
    +-30% of its default.
    """
    rs = events[events["suggestion_type"] == "reassign"] if not events.empty else events
    out = dict(DEFAULT_WEIGHTS)
    if rs.empty:
        return out
    acc = rs["outcome"].isin(ACCEPTED)
    for k, base in DEFAULT_WEIGHTS.items():
        vals = rs["context_features"].map(lambda cf, k=k: float(cf.get(f"factor_{k}", 0.0)))
        if acc.all() or (~acc).all():
            continue
        diff = float(vals[acc].mean() - vals[~acc].mean())
        out[k] = round(
            float(
                np.clip(
                    base * (1 + lr * diff), base * (1 - WEIGHT_BOUND), base * (1 + WEIGHT_BOUND)
                )
            ),
            4,
        )
    return out
