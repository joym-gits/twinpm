"""7.1 Delay Risk Classifier: XGBoost + isotonic calibration + SHAP drivers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

from twinpm.ml.data import ProgramData
from twinpm.ml.features import FEATURES, FeatureBuilder, label_for, training_snapshots
from twinpm.ml.registry import ModelRegistry

NAME = "delay_risk"
XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 600,
    "max_depth": 3,
    "learning_rate": 0.02,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "min_child_weight": 5,
    "reg_lambda": 1.0,
    "eval_metric": "logloss",
    "random_state": 42,
    "n_jobs": 2,
}


@dataclass
class DelayModel:
    xgb: XGBClassifier
    calibrator: IsotonicRegression
    features: tuple[str, ...]

    def raw(self, x: pd.DataFrame) -> np.ndarray:
        out: np.ndarray = np.asarray(self.xgb.predict_proba(x[list(self.features)])[:, 1])
        return out

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        # Bounded away from 0/1: isotonic steps on a small calibration set overstate certainty.
        cal: np.ndarray = np.asarray(self.calibrator.predict(self.raw(x)), dtype=float)
        clipped: np.ndarray = np.clip(cal, 0.02, 0.97)
        return clipped

    def drivers(self, x: pd.DataFrame, top: int = 3) -> list[list[dict[str, Any]]]:
        sv = shap.TreeExplainer(self.xgb).shap_values(x[list(self.features)])
        out: list[list[dict[str, Any]]] = []
        for i in range(len(x)):
            row = sv[i]
            order = np.argsort(-row)
            drivers: list[dict[str, Any]] = []
            for j in order:
                if row[j] <= 0 or len(drivers) == top:
                    break
                feat = self.features[j]
                val = float(x.iloc[i][feat])
                drivers.append(
                    {
                        "feature": feat,
                        "value": round(val, 3),
                        "contribution": round(float(row[j]), 4),
                        "label": label_for(feat, val),
                    }
                )
            out.append(drivers)
        return out


def precision_at_k(y: np.ndarray, p: np.ndarray, k: int = 10) -> float:
    idx = np.argsort(-p)[:k]
    return float(y[idx].mean()) if len(idx) else 0.0


def train(
    data: ProgramData, registry: ModelRegistry | None = None
) -> tuple[DelayModel, dict[str, Any]]:
    fb = FeatureBuilder(data)
    x, y, times = training_snapshots(fb)
    order = np.argsort(np.array([t.value for t in times]))
    x, y = x.iloc[order].reset_index(drop=True), y[order]
    n = len(y)
    fit_end, cal_end = int(n * 0.65), int(n * 0.8)  # time-based: fit | calibrate | validate
    xgb = XGBClassifier(**XGB_PARAMS)
    xgb.fit(x.iloc[:fit_end], y[:fit_end])
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    cal.fit(xgb.predict_proba(x.iloc[fit_end:cal_end])[:, 1], y[fit_end:cal_end])
    model = DelayModel(xgb, cal, FEATURES)
    xv, yv = x.iloc[cal_end:], y[cal_end:]
    pv = model.predict(xv)
    metrics = {
        "roc_auc": round(float(roc_auc_score(yv, model.raw(xv))), 4),
        "precision_at_10": round(precision_at_k(yv, pv, 10), 4),
        "brier": round(float(brier_score_loss(yv, pv)), 4),
        "n_train": fit_end,
        "n_calibration": cal_end - fit_end,
        "n_validation": n - cal_end,
        "positive_rate": round(float(y.mean()), 3),
    }
    # Refit on everything for serving; calibration keeps the held-out mapping.
    final = XGBClassifier(**XGB_PARAMS)
    final.fit(x.iloc[:cal_end], y[:cal_end])
    model = DelayModel(final, cal, FEATURES)
    if registry is not None:
        registry.save(
            NAME,
            model,
            {
                "purpose": "Probability that a work item finishes after its due date",
                "algorithm": "XGBoost classifier + isotonic calibration; SHAP TreeExplainer",
                "features": list(FEATURES),
                "metrics": metrics,
                "split": "time-based 65/15/20",
                "training_data_hash": ModelRegistry.data_hash(
                    pd.util.hash_pandas_object(x).values.tobytes()
                ),
            },
        )
    return model, metrics


@dataclass(frozen=True)
class ItemRisk:
    work_item_id: Any
    score: float
    drivers: list[dict[str, Any]]


OVERDUE_SCORE = 0.97


def _team_late_rate(data: ProgramData, team: Any, days: int = 90) -> float:
    it = data.items
    lo = pd.Timestamp(data.now) - pd.Timedelta(days=days)
    done = it[(it["team_id"] == team) & (it["done_at"] > lo)]
    if done.empty:
        return 0.25
    return float((done["done_at"].dt.date > done["due_date"]).mean())


def score_open_items(data: ProgramData, model: DelayModel) -> list[ItemRisk]:
    """Score every open item.

    - Started, not yet due: calibrated model probability with SHAP drivers.
    - Started and already past due: certain to finish late (OVERDUE_SCORE), drivers still
      explain why.
    - Not started: the team's recent late rate, scaled by upstream dependency risk, because
      the causes the model relies on are not observable before work begins.
    """
    fb = FeatureBuilder(data)
    open_items = data.items[data.items["status"] != "done"]
    if open_items.empty:
        return []
    now = pd.Timestamp(data.now)
    x = fb.matrix([(wid, now) for wid in open_items["id"]])
    scores = model.predict(x)
    drivers = model.drivers(x)
    out: list[ItemRisk] = []
    for i, r in enumerate(open_items.itertuples()):
        score, drv = float(scores[i]), drivers[i]
        f = x.iloc[i]
        if pd.isna(r.started_at):
            base = _team_late_rate(data, r.team_id)
            score = min(0.9, base * (1 + f["upstream_dependency_risk"]))
            drv = [
                {
                    "feature": "team_late_rate_90d",
                    "value": round(base, 3),
                    "contribution": round(base, 4),
                    "label": f"Not started; team finished {base:.0%} of recent items late",
                }
            ]
            if f["upstream_dependency_risk"] > 0:
                drv.append(
                    {
                        "feature": "upstream_dependency_risk",
                        "value": float(f["upstream_dependency_risk"]),
                        "contribution": 0.1,
                        "label": label_for(
                            "upstream_dependency_risk", float(f["upstream_dependency_risk"])
                        ),
                    }
                )
        elif f["days_to_due"] < 0:
            score = max(score, OVERDUE_SCORE)
            overdue = {
                "feature": "days_to_due",
                "value": round(float(f["days_to_due"]), 2),
                "contribution": 1.0,
                "label": label_for("days_to_due", f["days_to_due"]),
            }
            drv = [d for d in drv if d["feature"] != "days_to_due"][:3]
            drv = [*drv, overdue] if drv else [overdue]
        out.append(ItemRisk(r.id, round(score, 4), drv))
    return out
