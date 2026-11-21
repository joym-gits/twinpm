"""Section 12 ML gates, on the deterministic seed (no database needed)."""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from twinpm.ml import anomaly, delay, delegation, effort, forecast, health, preference, scenario
from twinpm.ml.data import ProgramData, as_of, from_dataset
from twinpm.ml.features import FEATURES, PROTECTED, FeatureBuilder
from twinpm.ml.registry import ModelRegistry
from twinpm.seed.generator import generate

ANCHOR = date(2026, 11, 21)


@pytest.fixture(scope="module")
def data() -> ProgramData:
    return from_dataset(generate(42, ANCHOR))


@pytest.fixture(scope="module")
def trained(data: ProgramData) -> tuple[delay.DelayModel, dict[str, Any]]:
    return delay.train(data)


@pytest.fixture(scope="module")
def risks(data: ProgramData, trained: tuple[delay.DelayModel, dict[str, Any]]) -> dict[Any, float]:
    return {r.work_item_id: r.score for r in delay.score_open_items(data, trained[0])}


def _ids(data: ProgramData, table: str, col: str) -> dict[str, Any]:
    df = getattr(data, table)
    return dict(zip(df[col], df["id"], strict=True))


@pytest.fixture(scope="module")
def baseline(data: ProgramData, risks: dict[Any, float]) -> tuple[Any, Any]:
    ms = data.milestones["id"].iloc[0]
    inp = forecast.build_input(data, ms, risks)
    return inp, forecast.simulate(inp)


def test_delay_model_meets_auc_target(trained: tuple[delay.DelayModel, dict[str, Any]]) -> None:
    metrics = trained[1]
    assert metrics["roc_auc"] >= 0.80, metrics
    assert 0 <= metrics["brier"] < 0.25
    assert metrics["precision_at_10"] >= 0.7


def test_storyline_items_score_above_065(data: ProgramData, risks: dict[Any, float]) -> None:
    epics = _ids(data, "epics", "title")
    vikram = _ids(data, "people", "name")["Vikram Rao"]
    it = data.items
    story = it[
        (it["epic_id"] == epics["Payments API v2"])
        & (it["status"] != "done")
        & (
            (it["reopen_count"] > 0)
            | ((it["assignee_person_id"] == vikram) & (it["due_date"] < ANCHOR))
        )
    ]
    assert len(story) >= 2
    assert all(risks[w] > 0.65 for w in story["id"]), [risks[w] for w in story["id"]]


def test_drivers_are_human_readable(
    data: ProgramData, trained: tuple[delay.DelayModel, Any]
) -> None:
    scored = delay.score_open_items(data, trained[0])
    top = max(scored, key=lambda r: r.score)
    assert 1 <= len(top.drivers) <= 4
    assert all(d["label"] and d["contribution"] > 0 for d in top.drivers)


def test_monte_carlo_is_deterministic_and_fast(baseline: tuple[Any, Any]) -> None:
    inp, first = baseline
    t0 = time.perf_counter()
    again = forecast.simulate(inp)
    assert time.perf_counter() - t0 < 1.0
    assert (again.p50, again.p80, again.p95) == (first.p50, first.p80, first.p95)
    assert first.p50 <= first.p80 <= first.p95
    assert sum(h["count"] for h in first.histogram) == forecast.DEFAULT_SIMS


def _no_slip(data: ProgramData, risks: dict[Any, float]) -> forecast.ForecastResult:
    pay = _ids(data, "teams", "name")["Payments"]
    inp = forecast.build_input(data, data.milestones["id"].iloc[0], risks)
    fb = FeatureBuilder(data)
    inp.throughput[pay] = fb.sprint_velocities(pay, pd.Timestamp(data.now) - pd.Timedelta(days=28))
    inp.items.loc[inp.items["team_id"] == pay, "risk"] = 0.25
    return forecast.simulate(inp)


def test_payments_slip_moves_launch_p80(
    data: ProgramData, risks: dict[Any, float], baseline: tuple[Any, Any]
) -> None:
    slip = (baseline[1].p80 - _no_slip(data, risks).p80).days
    assert slip >= 7, slip


def test_p80_moved_over_the_last_two_weeks(
    data: ProgramData, trained: tuple[delay.DelayModel, Any], baseline: tuple[Any, Any]
) -> None:
    past = as_of(data, data.now - timedelta(days=14))
    prisks = {r.work_item_id: r.score for r in delay.score_open_items(past, trained[0])}
    prev = forecast.simulate(forecast.build_input(past, past.milestones["id"].iloc[0], prisks))
    assert (baseline[1].p80 - prev.p80).days >= 7


def test_rebalance_recovers_half_the_slip(
    data: ProgramData,
    risks: dict[Any, float],
    trained: tuple[delay.DelayModel, Any],
    baseline: tuple[Any, Any],
) -> None:
    inp, base = baseline
    slip = (base.p80 - _no_slip(data, risks).p80).days
    moves = delegation.plan_rebalance(data, risks, forecast.critical_epics(data, inp))
    targets = {m.to_name for m in moves}
    assert {"Karan Malhotra", "Li Wei"} <= targets, targets
    changes = [
        {
            "type": "reassign",
            "work_item_ids": [str(m.work_item_id)],
            "to_person_id": str(m.to_person_id),
        }
        for m in moves
    ]
    res = scenario.run(data, inp, changes, trained[0], baseline=base)
    assert -res.delta_days >= 0.5 * slip, (res.delta_days, slip)
    assert "earlier" in res.narrative


def test_scenario_change_types(data: ProgramData, baseline: tuple[Any, Any]) -> None:
    inp, base = baseline
    pay = _ids(data, "teams", "name")["Payments"]
    epic = _ids(data, "epics", "title")["Payments API v2"]
    more = scenario.run(
        data,
        inp,
        [
            {
                "type": "add_scope",
                "team_id": str(pay),
                "epic_id": str(epic),
                "points": 40,
                "items": 8,
            }
        ],
        baseline=base,
    )
    assert more.delta_days > 0
    less_cap = scenario.run(
        data, inp, [{"type": "capacity_change", "team_id": str(pay), "factor": 0.7}], baseline=base
    )
    assert less_cap.delta_days > 0
    ids = [str(w) for w in inp.items.loc[inp.items["epic_id"] == epic, "id"]]
    cut = scenario.run(data, inp, [{"type": "remove_scope", "work_item_ids": ids}], baseline=base)
    assert cut.delta_days < 0
    shifted = scenario.apply_changes(data, inp, [{"type": "date_shift", "days": 14}])
    assert shifted.target == inp.target + timedelta(days=14)


def test_anomalies_flag_payments_velocity_and_review_latency(data: ProgramData) -> None:
    pay = _ids(data, "teams", "name")["Payments"]
    found = {f.metric for f in anomaly.detect(data) if f.team_id == pay}
    assert {"velocity", "review_latency_p50"} <= found, found


def test_health_score_and_drivers(
    data: ProgramData, risks: dict[Any, float], baseline: tuple[Any, Any]
) -> None:
    target = data.milestones["target_date"].iloc[0]
    h = health.compute(data, baseline[1].p80, target, risks)
    assert 60 <= h.score <= 82, h
    assert set(h.subscores) == {"schedule", "scope", "quality", "dependencies", "team"}
    assert h.subscores["dependencies"] < 70  # amber
    assert len(h.drivers) == 5


def test_effort_estimator(data: ProgramData) -> None:
    model, metrics = effort.train(data)
    assert metrics["mae_days"] < 4
    assert metrics["interval_80_coverage"] >= 0.75
    row = data.items[data.items["status"] != "done"].head(2)
    est = model.estimate(row, row["title"].tolist())
    assert est[0]["p10_days"] <= est[0]["estimate_days"] <= est[0]["p90_days"]
    assert len(est[0]["similar"]) == 3


def test_delegation_excludes_protected_attributes() -> None:
    feats = {f.lower() for f in (*FEATURES, *delegation.FEATURE_NAMES)}
    people_attrs = {f"{who}_{p}" for who in ("assignee", "person", "owner") for p in PROTECTED}
    assert not feats & (set(PROTECTED) | people_attrs)
    # The ranker reads only work signals from people records.
    import inspect

    src = inspect.getsource(delegation.Ranker.factors)
    for attr in ("timezone", '"name"', "gender", "nationality"):
        assert attr not in src


def test_delegation_candidates_explain_themselves(data: ProgramData) -> None:
    epic = _ids(data, "epics", "title")["Payments API v2"]
    item = data.items[(data.items["epic_id"] == epic) & (data.items["status"] == "todo")].iloc[0]
    ranked = delegation.Ranker(data).rank(item)
    assert ranked[0].score >= ranked[-1].score
    assert set(ranked[0].factors) == set(delegation.FEATURE_NAMES)
    assert ranked[0].explanation.endswith(".")


def test_bounded_weights() -> None:
    w = delegation.bounded_weights({"skill_match": 10.0, "availability": 0.0})
    assert w["skill_match"] == pytest.approx(0.35 * 1.3)
    assert w["availability"] == pytest.approx(0.25 * 0.7)


def test_preference_model_learns_and_nudges() -> None:
    rows = []
    rng = np.random.default_rng(0)
    for _ in range(40):
        skill = float(rng.random())
        accepted = skill > 0.5
        cf = preference.context_features("reassign", 3, 3, 2, 0.5)
        cf["factor_skill_match"] = skill
        rows.append(
            {
                "user_id": "u",
                "suggestion_type": "reassign",
                "context_features": cf,
                "outcome": "accepted" if accepted else "rejected",
            }
        )
    rows += [
        {
            "user_id": "u",
            "suggestion_type": "nudge",
            "context_features": preference.context_features("nudge", 3, 1, 1, 0.1),
            "outcome": "rejected",
        }
        for _ in range(6)
    ]
    ev = pd.DataFrame(rows)
    model = preference.fit(ev, "u")
    assert model.prior["nudge"] < model.prior["reassign"]
    w = preference.nudge_weights(ev)
    assert w["skill_match"] > delegation.DEFAULT_WEIGHTS["skill_match"]
    assert w["skill_match"] <= delegation.DEFAULT_WEIGHTS["skill_match"] * 1.3 + 1e-9
    cold = preference.fit(pd.DataFrame())
    assert cold.accept_probability(preference.context_features("nudge", 3, 0, 0, 0)) == 0.6


def test_registry_roundtrip(tmp_path: Path) -> None:
    reg = ModelRegistry(tmp_path)
    info = reg.save("demo", {"w": [1, 2]}, {"metrics": {"auc": 0.9}})
    assert info.version == "v0001"
    assert reg.save("demo", {"w": [3]}, {}).version == "v0002"
    loaded = reg.load("demo")
    assert loaded is not None
    assert loaded[0] == {"w": [3]}
    assert loaded[1].metadata["name"] == "demo"
    assert reg.versions("demo") == ["v0001", "v0002"]


def test_as_of_hides_the_future(data: ProgramData) -> None:
    t = data.now - timedelta(days=30)
    past = as_of(data, t)
    assert (past.items["created_at_src"] <= pd.Timestamp(t)).all()
    assert not (past.items["done_at"] > pd.Timestamp(t)).any()
    assert set(past.items["status"]) <= {"todo", "in_progress", "in_review", "blocked", "done"}
