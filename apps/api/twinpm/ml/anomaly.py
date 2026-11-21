"""7.4 Anomaly detection: rolling z-score per metric plus Isolation Forest per team."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from twinpm.ml.data import ProgramData

METRICS = ("velocity", "throughput", "cycle_time_p50", "bug_inflow", "review_latency_p50", "wip")
LABEL = {
    "velocity": ("velocity", "pts"),
    "throughput": ("throughput", "items/wk"),
    "cycle_time_p50": ("cycle time p50", "days"),
    "bug_inflow": ("bug inflow", "bugs/wk"),
    "review_latency_p50": ("review latency p50", "h"),
    "wip": ("work in progress", "items"),
}
WINDOW = 28
Z_THRESHOLD = 2.5
BASELINE_LAG = 14


@dataclass(frozen=True)
class AnomalyFinding:
    team_id: Any
    metric: str
    date: date
    value: float
    expected: float
    z_score: float
    method: str
    explanation: str


def detect(data: ProgramData, lookback_days: int = 21) -> list[AnomalyFinding]:
    out: list[AnomalyFinding] = []
    team_name = data.teams.set_index("id")["name"].to_dict()
    cutoff = data.today - pd.Timedelta(days=lookback_days)
    for team, g in data.metrics.groupby("team_id"):
        g = g.sort_values("date").reset_index(drop=True)
        vals = g[list(METRICS)].astype(float)
        # Baseline: the 28 days ending two weeks earlier, so a gradual shift cannot absorb
        # itself into its own baseline.
        mean = vals.rolling(WINDOW, min_periods=14).mean().shift(BASELINE_LAG)
        std = vals.rolling(WINDOW, min_periods=14).std().shift(BASELINE_LAG).clip(lower=1e-6)
        z = (vals - mean) / std
        z = z.where(std > 0.05 * mean.abs().clip(lower=1.0), 0.0).fillna(0.0)
        scaled = ((vals - vals.mean()) / vals.std().replace(0, 1)).fillna(0.0)
        iso = IsolationForest(n_estimators=200, contamination=0.03, random_state=42)
        iso_flag = iso.fit_predict(scaled.to_numpy()) == -1
        recent = g["date"] >= cutoff
        best: dict[str, AnomalyFinding] = {}
        for i in np.where(recent.to_numpy())[0]:
            zrow = z.iloc[i]
            flagged = [m for m in METRICS if abs(zrow[m]) > Z_THRESHOLD]
            if iso_flag[i] and not flagged:
                m = max(METRICS, key=lambda k: abs(zrow[k]))
                if abs(zrow[m]) > 1.5:
                    flagged = [m]
            for m in flagged:
                method = (
                    "zscore+iforest"
                    if iso_flag[i] and abs(zrow[m]) > Z_THRESHOLD
                    else ("zscore" if abs(zrow[m]) > Z_THRESHOLD else "iforest")
                )
                v, e = float(vals.iloc[i][m]), float(mean.iloc[i][m])
                name, unit = LABEL[m]
                direction = "above" if v > e else "below"
                pct = abs(v - e) / e if e else 0.0
                f = AnomalyFinding(
                    team,
                    m,
                    g.iloc[i]["date"],
                    round(v, 2),
                    round(e, 2),
                    round(float(zrow[m]), 2),
                    method,
                    f"{team_name.get(team, 'Team')} {name} is {v:.1f}{unit} on "
                    f"{g.iloc[i]['date']:%b %d}, {pct:.0%} {direction} its baseline of "
                    f"{e:.1f}{unit} (z = {zrow[m]:+.1f}, {method}).",
                )
                # Deduplicate runs: keep the most recent finding per metric.
                if m not in best or f.date >= best[m].date:
                    best[m] = f
        out.extend(best.values())
    return sorted(out, key=lambda f: -abs(f.z_score))
