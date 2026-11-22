"""Router integration tests on the seeded NovaPay org (testcontainers Postgres + Redis)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("seeded")


async def _program(c: httpx.AsyncClient) -> dict[str, Any]:
    r = await c.get("/api/v1/programs")
    assert r.status_code == 200
    first: dict[str, Any] = r.json()[0]
    return first


async def _ids(c: httpx.AsyncClient) -> dict[str, Any]:
    prog = await _program(c)
    wl = (await c.get("/api/v1/delegation/workload", params={"program_id": prog["id"]})).json()
    people = {p["name"]: p for p in wl["people"]}
    rm = (await c.get("/api/v1/roadmap", params={"program_id": prog["id"]})).json()
    epics = {e["title"]: e["id"] for b in rm["buckets"].values() for i in b for e in i["epics"]}
    return {"program": prog, "people": people, "epics": epics, "roadmap": rm}


async def test_health_and_briefing(priya: httpx.AsyncClient) -> None:
    prog = await _program(priya)
    h = (await priya.get(f"/api/v1/programs/{prog['id']}/health")).json()
    assert 60 <= h["score"] <= 82
    assert set(h["subscores"]) == {"schedule", "scope", "quality", "dependencies", "team"}
    assert h["delta_7d"] is not None and h["delta_7d"] < 0
    assert len(h["trend"]) >= 20
    b = (
        await priya.get(f"/api/v1/programs/{prog['id']}/briefing", params={"refresh": True})
    ).json()
    assert len(b["items"]) == 3
    first = b["items"][0]
    assert "Payments API v2" in first["title"]
    assert first["recommended_action"]["suggestion_id"]
    assert first["evidence"] and first["drivers"]
    assert b["drafted_by"] == "Priya's twin"


async def test_scenario_options_suggestion(priya: httpx.AsyncClient) -> None:
    prog = await _program(priya)
    b = (await priya.get(f"/api/v1/programs/{prog['id']}/briefing")).json()
    sid = b["items"][0]["recommended_action"]["suggestion_id"]
    s = (await priya.get(f"/api/v1/suggestions/{sid}")).json()
    names = [o["name"] for o in s["payload"]["options"]]
    assert names == ["Rebalance", "Descope", "Move the date"]
    rebalance = s["payload"]["options"][0]
    assert rebalance["delta_days"] < 0
    assert {"Karan Malhotra", "Li Wei"} <= {mv["to_name"] for mv in rebalance["moves"]}


async def test_roadmap_and_initiative_patch_is_audited(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    later = ids["roadmap"]["buckets"]["later"][0]
    r = await priya.patch(f"/api/v1/initiatives/{later['id']}", json={"roadmap_bucket": "next"})
    assert r.status_code == 200, r.text
    audit = (await priya.get("/api/v1/audit", params={"entity_id": later["id"]})).json()
    assert audit[0]["action"] == "initiative.updated"
    assert audit[0]["before"]["roadmap_bucket"] == "later"
    assert audit[0]["after"]["roadmap_bucket"] == "next"
    await priya.patch(f"/api/v1/initiatives/{later['id']}", json={"roadmap_bucket": "later"})


async def test_simulate_and_save_scenario(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    team = ids["people"]["Vikram Rao"]["team_id"]
    body = {
        "program_id": ids["program"]["id"],
        "changes": [{"type": "capacity_change", "team_id": team, "factor": 1.3}],
    }
    r = await priya.post("/api/v1/scenarios/simulate", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["delta_days"] < 0
    assert out["narrative"].startswith("Launch P80 moves")
    bad = await priya.post(
        "/api/v1/scenarios/simulate",
        json={**body, "changes": [{"type": "capacity_change", "team_id": team, "factor": -1}]},
    )
    assert bad.status_code == 422
    saved = await priya.post("/api/v1/scenarios", json={**body, "name": "Payments +30%"})
    assert saved.status_code == 201, saved.text
    listed = (await priya.get("/api/v1/scenarios")).json()
    assert any(s["name"] == "Payments +30%" for s in listed)


async def test_forecast(priya: httpx.AsyncClient, seeded: dict[str, Any]) -> None:
    from sqlalchemy import select

    from twinpm.db.models import Milestone
    from twinpm.db.session import get_sessionmaker

    async with get_sessionmaker()() as s:
        ms = (
            await s.execute(select(Milestone.id).where(Milestone.org_id == seeded["org_id"]))
        ).scalar_one()
    f = (await priya.get(f"/api/v1/forecasts/{ms}")).json()
    assert f["p50"] <= f["p80"] <= f["p95"]
    assert f["previous"] is not None and f["previous"]["p80"] < f["p80"]
    run = await priya.post(f"/api/v1/forecasts/{ms}/run")
    assert run.status_code == 200


async def test_delegation_endpoints(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    vikram = ids["people"]["Vikram Rao"]
    assert vikram["overloaded"] and vikram["utilisation"] > 1.0
    assert len(vikram["weeks"]) == 8
    risky = (
        await priya.get(
            "/api/v1/risk/work-items", params={"program_id": ids["program"]["id"], "min_score": 0.6}
        )
    ).json()
    target = next(r for r in risky if r["epic"] == "Payments API v2")
    cands = (await priya.get(f"/api/v1/delegation/candidates/{target['work_item_id']}")).json()
    assert cands["candidates"][0]["explanation"]
    assert "skill_match" in cands["candidates"][0]["factors"]
    nud = await priya.post(
        "/api/v1/delegation/nudges/run", params={"program_id": ids["program"]["id"]}
    )
    assert nud.status_code == 200 and nud.json()["stalled"] > 0


async def test_rebalance_accept_and_undo(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    r = await priya.post("/api/v1/delegation/rebalance", json={"program_id": ids["program"]["id"]})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["delta_days"] < 0
    move = next(mv for mv in plan["moves"] if mv["to_name"] == "Karan Malhotra")
    res = await priya.post(
        f"/api/v1/suggestions/{move['suggestion_id']}/respond", json={"action": "accept"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "accepted"
    audit = (await priya.get("/api/v1/audit", params={"entity_id": move["work_item_id"]})).json()
    assert audit[0]["action"] == "work_item.reassigned"
    assert audit[0]["after"]["assignee_person_id"] == move["to_person_id"]
    again = await priya.post(
        f"/api/v1/suggestions/{move['suggestion_id']}/respond", json={"action": "accept"}
    )
    assert again.status_code == 409
    undo = await priya.post(f"/api/v1/suggestions/{move['suggestion_id']}/undo")
    assert undo.status_code == 200, undo.text
    audit = (await priya.get("/api/v1/audit", params={"entity_id": move["work_item_id"]})).json()
    assert audit[0]["action"] == "work_item.reassign_undone"
    learning = (await priya.get("/api/v1/twin/learning")).json()
    assert learning["suggestions_seen"] >= 1


async def test_reject_records_preference(priya: httpx.AsyncClient) -> None:
    pending = (await priya.get("/api/v1/suggestions", params={"type": "nudge"})).json()
    assert pending
    r = await priya.post(
        f"/api/v1/suggestions/{pending[0]['id']}/respond",
        json={"action": "reject", "reason": "Already discussed in standup"},
    )
    assert r.json()["status"] == "rejected"
    assert r.json()["feedback_reason"] == "Already discussed in standup"


async def test_risk_register_crud_and_graph(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    pid = ids["program"]["id"]
    reg = (await priya.get("/api/v1/risk/register", params={"program_id": pid})).json()
    assert any(r["source"] == "model" for r in reg)
    new = await priya.post(
        "/api/v1/risk/register",
        json={
            "program_id": pid,
            "title": "Vendor SDK deprecation",
            "probability": 0.3,
            "impact": 3,
        },
    )
    assert new.status_code == 201, new.text
    rid = new.json()["id"]
    upd = await priya.patch(f"/api/v1/risk/register/{rid}", json={"status": "mitigating"})
    assert upd.json()["status"] == "mitigating"
    assert upd.json()["severity"] == pytest.approx(0.9)
    g = (await priya.get("/api/v1/dependencies/graph", params={"program_id": pid})).json()
    crit = {n["label"] for n in g["nodes"] if n["critical"] and n["kind"] == "epic"}
    assert "Payments API v2" in crit
    api = next(n for n in g["nodes"] if n["label"] == "Payments API v2")
    imp = (
        await priya.post(
            "/api/v1/dependencies/impact", json={"entity_id": api["id"], "slip_days": 9}
        )
    ).json()
    assert imp["delta_days"] > 0
    assert any(a["label"] == "Mobile checkout UI" for a in imp["affected"])


async def test_insights(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    pid = ids["program"]["id"]
    series = (
        await priya.get("/api/v1/insights/metrics", params={"metric": "review_latency_p50"})
    ).json()
    assert len(series) == 3
    bad = await priya.get("/api/v1/insights/metrics", params={"metric": "salary"})
    assert bad.status_code == 400
    an = (await priya.get("/api/v1/insights/anomalies")).json()
    assert any(a["metric"] == "review_latency_p50" for a in an)
    th = (await priya.get("/api/v1/insights/team-health", params={"program_id": pid})).json()
    pay = next(t for t in th if t["team"] == "Payments")
    assert pay["sentiment_trend"] < 0 and not pay["suppressed"]
    ask = (
        await priya.post(
            "/api/v1/insights/ask",
            json={"question": "How has Payments review latency changed over the last 6 weeks?"},
        )
    ).json()
    assert ask["chart"]["metric"] == "review_latency_p50"
    assert ask["tool_calls"][0]["tool"] == "query_metric"
    assert "Payments" in ask["narrative"]


async def test_planning(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    epic = ids["epics"]["Fraud hooks"]
    br = await priya.post(
        "/api/v1/planning/breakdown",
        json={
            "epic_id": epic,
            "text": (
                "- Score each authorisation\n- Stream fraud signals to Kafka\n- Add a kill switch"
            ),
        },
    )
    assert br.status_code == 200, br.text
    stories = br.json()["stories"]
    assert len(stories) >= 3 and stories[0]["acceptance_criteria"]
    assert stories[0]["p10_days"] <= stories[0]["estimate_days"] <= stories[0]["p90_days"]
    assert len(br.json()["suggestion_ids"]) == len(stories)
    team = ids["people"]["Meera Nair"]["team_id"]
    sp = (await priya.post("/api/v1/planning/sprint-plan", json={"team_id": team})).json()
    assert sp["recommended_commitment"] <= sp["capacity_points"]


async def test_persona_autonomy_and_policy(priya: httpx.AsyncClient) -> None:
    ids = await _ids(priya)
    p = (await priya.get("/api/v1/persona")).json()
    assert p["tone"] == "concise" and p["priorities"]
    p["tone"] = "friendly"
    put = await priya.put(
        "/api/v1/persona",
        json={
            k: p[k]
            for k in (
                "priorities",
                "style_examples",
                "tone",
                "risk_tolerance",
                "escalation_rules",
                "working_hours",
            )
        },
    )
    assert put.json()["tone"] == "friendly"
    pol = (await priya.get("/api/v1/autonomy-policy")).json()
    levels = {x["action_type"]: x["level"] for x in pol["policies"]}
    assert levels["reassign"] == 3 and levels["roadmap_change"] == 2
    too_high = await priya.put("/api/v1/autonomy-policy", json={"levels": {"status_report": 4}})
    assert too_high.status_code == 400
    ok = await priya.put("/api/v1/autonomy-policy", json={"levels": {"nudge": 4}})
    assert ok.status_code == 200
    run = (
        await priya.post(
            "/api/v1/delegation/nudges/run", params={"program_id": ids["program"]["id"]}
        )
    ).json()
    assert run["auto_executed"] == run["suggestions_created"]
    await priya.put("/api/v1/autonomy-policy", json={"levels": {"nudge": 3}})
    notes = (await priya.get("/api/v1/notifications")).json()
    assert isinstance(notes, list)


async def test_executive_is_read_only(client: httpx.AsyncClient, seeded: dict[str, Any]) -> None:
    from twinpm.tests.conftest import DEMO_PASSWORD

    r = await client.post(
        "/api/v1/auth/login", json={"email": "rahul@novapay.example", "password": DEMO_PASSWORD}
    )
    assert r.status_code == 200
    client.headers["x-csrf-token"] = client.cookies["twinpm_csrf"]
    prog = await _program(client)
    r = await client.post("/api/v1/delegation/rebalance", json={"program_id": prog["id"]})
    assert r.status_code == 403
    r = await client.get(f"/api/v1/programs/{prog['id']}/health")
    assert r.status_code == 200


async def test_zz_reset_demo_is_fast_and_rbac_checked(
    client: httpx.AsyncClient, priya: httpx.AsyncClient
) -> None:
    """Runs last in this module: it re-seeds the shared demo org."""
    r = await priya.post("/api/v1/admin/reset-demo")
    assert r.status_code == 200, r.text
    assert r.json()["seed_seconds"] < 10
    print("reset timings", r.json())
    me = await priya.get("/api/v1/auth/me")  # deterministic IDs: the session survives
    assert me.status_code == 200
