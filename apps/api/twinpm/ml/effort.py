"""7.2 Effort Estimator: gradient-boosted quantile regression with similar past items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from twinpm.ml.data import ProgramData
from twinpm.ml.registry import ModelRegistry
from twinpm.rag.embedding import embed

NAME = "effort"
TYPES = ("story", "task", "bug", "spike")
QUANTILES = (0.1, 0.5, 0.9)
PCA_DIMS = 16


@dataclass
class EffortModel:
    models: dict[float, GradientBoostingRegressor]
    pca: PCA
    teams: list[str]
    labels: list[str]
    history: pd.DataFrame  # id, key, title, days, embedding (unit vectors)
    interval_scale: float = 1.0  # conformal widening so the 10-90 band covers ~80%

    def _x(self, rows: pd.DataFrame, vecs: np.ndarray) -> np.ndarray:
        cols = [
            rows["story_points"].astype(float).to_numpy()[:, None],
            np.stack([(rows["type"] == t).to_numpy(float) for t in TYPES], axis=1),
            np.stack(
                [(rows["team_id"].astype(str) == t).to_numpy(float) for t in self.teams], axis=1
            ),
            np.stack(
                [
                    rows["labels"].map(lambda ls, lb=lb: float(lb in (ls or []))).to_numpy()
                    for lb in self.labels
                ],
                axis=1,
            ),
            self.pca.transform(vecs),
        ]
        return np.hstack(cols)

    def estimate(self, rows: pd.DataFrame, texts: list[str]) -> list[dict[str, Any]]:
        vecs = embed(texts)
        x = self._x(rows, vecs)
        preds = {q: m.predict(x) for q, m in self.models.items()}
        hist_vecs = np.stack(self.history["embedding"].to_numpy())
        out = []
        for i in range(len(rows)):
            lo, mid, hi = sorted(max(0.25, float(preds[q][i])) for q in QUANTILES)
            lo = max(0.25, mid - self.interval_scale * (mid - lo))
            hi = mid + self.interval_scale * (hi - mid)
            sims = hist_vecs @ vecs[i]
            top = np.argsort(-sims)[:3]
            out.append(
                {
                    "estimate_days": round(mid, 1),
                    "p10_days": round(lo, 1),
                    "p90_days": round(hi, 1),
                    "similar": [
                        {
                            "id": str(self.history.iloc[j]["id"]),
                            "key": self.history.iloc[j]["key"],
                            "title": self.history.iloc[j]["title"],
                            "actual_days": round(float(self.history.iloc[j]["days"]), 1),
                            "similarity": round(float(sims[j]), 3),
                        }
                        for j in top
                    ],
                }
            )
        return out


def _text(r: Any) -> str:
    return f"{r.title}. {r.description}"


def train(
    data: ProgramData, registry: ModelRegistry | None = None
) -> tuple[EffortModel, dict[str, Any]]:
    it = data.items[data.items["done_at"].notna() & data.items["started_at"].notna()].copy()
    it["days"] = (it["done_at"] - it["started_at"]).dt.total_seconds() / 86400
    it = it.sort_values("done_at").reset_index(drop=True)
    vecs = embed([_text(r) for r in it.itertuples()])
    pca = PCA(n_components=PCA_DIMS, random_state=42).fit(vecs)
    teams = sorted(it["team_id"].astype(str).unique())
    labels = sorted({lb for ls in it["labels"] for lb in (ls or [])})
    shell = EffortModel({}, pca, teams, labels, pd.DataFrame())
    x, y = shell._x(it, vecs), it["days"].to_numpy()
    cut = int(len(y) * 0.8)
    models: dict[float, GradientBoostingRegressor] = {}
    for q in QUANTILES:
        m = GradientBoostingRegressor(
            loss="quantile",
            alpha=q,
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            random_state=42,
        )
        models[q] = m.fit(x[:cut], y[:cut])
    p50 = models[0.5].predict(x[cut:])
    p10, p90 = models[0.1].predict(x[cut:]), models[0.9].predict(x[cut:])
    yv = y[cut:]
    scale = 1.0
    for scale in np.arange(1.0, 4.01, 0.05):  # smallest widening reaching 80% coverage
        if np.mean((p50 - scale * (p50 - p10) <= yv) & (yv <= p50 + scale * (p90 - p50))) >= 0.8:
            break
    coverage = float(np.mean((p50 - scale * (p50 - p10) <= yv) & (yv <= p50 + scale * (p90 - p50))))
    metrics = {
        "mae_days": round(float(mean_absolute_error(y[cut:], p50)), 3),
        "interval_80_coverage": round(coverage, 3),
        "interval_scale": round(float(scale), 2),
        "n_train": cut,
        "n_validation": len(y) - cut,
    }
    for q in QUANTILES:
        models[q].fit(x, y)
    hist = pd.DataFrame(
        {
            "id": it["id"],
            "key": it["key"],
            "title": it["title"],
            "days": it["days"],
            "embedding": list(vecs),
        }
    )
    model = EffortModel(models, pca, teams, labels, hist, float(scale))
    if registry is not None:
        registry.save(
            NAME,
            model,
            {
                "purpose": "Days to complete a work item, with an 80% interval and similar items",
                "algorithm": "GradientBoostingRegressor (quantile 0.1/0.5/0.9) on type, points, "
                "team, labels and 16-dim PCA of the text embedding",
                "features": [
                    "story_points",
                    *[f"type_{t}" for t in TYPES],
                    "team",
                    "labels",
                    f"text_pca_{PCA_DIMS}",
                ],
                "metrics": metrics,
                "split": "time-based 80/20",
                "training_data_hash": ModelRegistry.data_hash(y.tobytes()),
            },
        )
    return model, metrics
