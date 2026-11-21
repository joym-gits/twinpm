"""Seed determinism, storyline conditions and idempotent loading."""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.domain import capacity_points
from twinpm.seed.generator import Dataset, generate

ANCHOR = date(2026, 11, 21)


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return generate(42, ANCHOR)


def _by(ds: Dataset, table: str, field: str, value: object) -> dict[str, Any]:
    return next(r for r in ds.tables[table] if r[field] == value)


def test_generation_is_deterministic(ds: Dataset) -> None:
    assert generate(42, ANCHOR).digest() == ds.digest()
    assert generate(43, ANCHOR).digest() != ds.digest()


def test_volumes_match_spec(ds: Dataset) -> None:
    wi = ds.tables["work_items"]
    done = sum(r["status"] == "done" for r in wi)
    assert 360 <= done <= 460
    assert 90 <= len(wi) - done <= 150
    assert len(ds.tables["teams"]) == 3
    assert sum(1 for p in ds.tables["people"] if p["team_id"]) == 15
    assert len(ds.tables["objectives"]) == 4
    assert len(ds.tables["initiatives"]) == 8
    assert 16 <= len(ds.tables["epics"]) <= 20
    deps = ds.tables["dependencies"]
    assert 22 <= len(deps) <= 28
    assert len(ds.tables["decisions"]) == 15
    assert len(ds.tables["feedback_items"]) == 150
    docs = ds.tables["documents"]
    assert sum(d["type"] == "design_doc" for d in docs) == 8
    assert sum(d["type"] in ("meeting_notes", "transcript") for d in docs) == 12
    assert any("Kafka over SQS" in d["title"] for d in ds.tables["decisions"])


def test_launch_is_about_16_weeks_out(ds: Dataset) -> None:
    m = ds.tables["milestones"][0]
    assert (m["target_date"] - ANCHOR).days == 16 * 7


def _team(ds: Dataset, name: str) -> object:
    return _by(ds, "teams", "name", name)["id"]


def test_payments_velocity_drops_about_30_percent(ds: Dataset) -> None:
    sprints = sorted(
        (s for s in ds.tables["sprints"] if s["team_id"] == _team(ds, "Payments")),
        key=lambda s: s["start_date"],
    )
    v = [float(s["completed_points"]) for s in sprints[:-1]]  # completed sprints only
    drop = 1 - statistics.mean(v[-2:]) / statistics.mean(v[-8:-2])
    assert 0.22 <= drop <= 0.45, drop


def test_payments_review_latency_rises_about_2_3x(ds: Dataset) -> None:
    md = sorted(
        (r for r in ds.tables["metrics_daily"] if r["team_id"] == _team(ds, "Payments")),
        key=lambda r: r["date"],
    )
    baseline = statistics.mean(float(r["review_latency_p50"]) for r in md[-120:-60])
    ratio = float(md[-1]["review_latency_p50"]) / baseline
    assert 1.9 <= ratio <= 2.8, ratio


def _utilisation(ds: Dataset, name: str) -> float:
    person = _by(ds, "people", "name", name)
    cur = max(s["start_date"] for s in ds.tables["sprints"])
    cur_dt = datetime(cur.year, cur.month, cur.day, tzinfo=UTC)
    sprint_start = {s["id"]: s["start_date"] for s in ds.tables["sprints"]}
    pts = 0.0
    for r in ds.tables["work_items"]:
        if r["assignee_person_id"] != person["id"] or not r["sprint_id"]:
            continue
        start = sprint_start[r["sprint_id"]]
        if start == cur or (start < cur and (r["done_at"] is None or r["done_at"] > cur_dt)):
            pts += float(r["story_points"])
    return pts / capacity_points(float(person["capacity_hours_per_week"]))


def test_utilisation_storyline(ds: Dataset) -> None:
    assert 1.0 <= _utilisation(ds, "Vikram Rao") <= 1.25
    assert 0.5 <= _utilisation(ds, "Karan Malhotra") <= 0.7
    assert 0.45 <= _utilisation(ds, "Li Wei") <= 0.65


def test_payments_api_storyline(ds: Dataset) -> None:
    api = _by(ds, "epics", "title", "Payments API v2")["id"]
    open_api = [r for r in ds.tables["work_items"] if r["epic_id"] == api and r["status"] != "done"]
    assert sum(r["reopen_count"] > 0 for r in open_api) >= 2
    blocked_epics = {
        _by(ds, "epics", "id", d["to_id"])["title"]
        for d in ds.tables["dependencies"]
        if d["from_type"] == "epic" and d["from_id"] == api
    }
    assert {"Mobile checkout UI", "Platform rate limiter", "Fraud hooks"} <= blocked_epics


def test_karan_and_liwei_have_the_right_skills(ds: Dataset) -> None:
    skill = {s["id"]: s["name"] for s in ds.tables["skills"]}

    def skills(name: str) -> dict[str, int]:
        pid = _by(ds, "people", "name", name)["id"]
        return {
            skill[ps["skill_id"]]: ps["level"]
            for ps in ds.tables["person_skills"]
            if ps["person_id"] == pid
        }

    assert skills("Karan Malhotra")["go"] == 5
    assert skills("Karan Malhotra")["api-design"] == 5
    assert skills("Li Wei")["postgres"] == 5
    karan = _by(ds, "people", "name", "Karan Malhotra")
    assert "payments" in karan["growth_goals"]


def test_payments_sentiment_declines(ds: Dataset) -> None:
    sig = sorted(
        (r for r in ds.tables["team_signals"] if r["team_id"] == _team(ds, "Payments")),
        key=lambda r: r["date"],
    )
    assert float(sig[-1]["sentiment_index"]) < float(sig[-30]["sentiment_index"]) - 0.2
    assert float(sig[-1]["after_hours_ratio"]) > float(sig[-30]["after_hours_ratio"]) + 0.08


def test_late_rate_is_realistic(ds: Dataset) -> None:
    done = [r for r in ds.tables["work_items"] if r["done_at"]]
    late = sum(r["done_at"].date() > r["due_date"] for r in done)
    assert 0.2 <= late / len(done) <= 0.45


async def test_load_is_idempotent(db: AsyncSession) -> None:
    from twinpm.core.tenancy import TenantContext
    from twinpm.db.models import DocumentChunk, Organization, WorkItem
    from twinpm.seed.loader import load
    from twinpm.services import audit

    data = generate(42, ANCHOR)
    await load(db, data, "pw-for-tests-123")
    org_id = await db.scalar(select(Organization.id).where(Organization.slug == "novapay"))
    assert org_id is not None
    await audit.record(
        db, TenantContext.system(org_id), action="x", entity_type="program", entity_id=None
    )
    await db.commit()
    timing = await load(db, generate(42, ANCHOR), "pw-for-tests-123")
    assert timing["seconds"] < 10
    n = await db.scalar(select(func.count()).select_from(WorkItem))
    assert n == len(data.tables["work_items"])
    chunks = await db.scalar(select(func.count()).select_from(DocumentChunk))
    assert chunks is not None
    assert chunks > 20
