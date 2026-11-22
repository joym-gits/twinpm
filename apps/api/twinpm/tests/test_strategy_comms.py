"""Strategy and comms endpoints in demo mode."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("seeded")


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        ev, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if data:
            out.append((ev, json.loads(data)))
    return out


async def test_themes_prd_critique_and_okrs(priya: httpx.AsyncClient) -> None:
    themes = (await priya.get("/api/v1/strategy/themes")).json()
    assert (
        themes
        and themes[0]["opportunity_score"]["score"] >= themes[-1]["opportunity_score"]["score"]
    )
    top = themes[0]
    r = await priya.post(
        "/api/v1/strategy/prd", json={"idea": "Self-serve bulk export", "theme_id": top["id"]}
    )
    evs = _events(r.text)
    kinds = [k for k, _ in evs]
    assert "token" in kinds and kinds[-1] == "done"
    doc_id = evs[-1][1]["document_id"]
    text = "".join(d["text"] for k, d in evs if k == "token")
    assert "## Problem" in text and "## Success metrics" in text
    doc = (await priya.get(f"/api/v1/documents/{doc_id}")).json()
    assert doc["type"] == "prd"
    crit = (
        await priya.post("/api/v1/strategy/devils-advocate", json={"document_id": doc_id})
    ).json()
    assert crit["assumptions"] and len(crit["validation_experiments"]) == 3
    bad = await priya.post("/api/v1/strategy/devils-advocate", json={})
    assert bad.status_code == 400
    prog = (await priya.get("/api/v1/programs")).json()[0]
    okrs = (await priya.post("/api/v1/strategy/okrs/draft", json={"program_id": prog["id"]})).json()
    assert len(okrs["objectives"]) == 3 and okrs["citations"]


async def test_feedback_import_and_recompute(priya: httpx.AsyncClient) -> None:
    csv = (
        "text,source,customer_segment,sentiment,received_at\n"
        "Please add CSV export for refunds,support,enterprise,-0.4,2026-11-01T10:00:00\n"
        "Dark mode would be lovely,survey,consumer,0.3,\n"
    )
    r = await priya.post("/api/v1/feedback/import", files={"file": ("f.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2
    empty = await priya.post(
        "/api/v1/feedback/import", files={"file": ("f.csv", "text\n\n", "text/csv")}
    )
    assert empty.status_code == 400
    bad = await priya.post(
        "/api/v1/feedback/import",
        files={"file": ("f.csv", "text,sentiment\nx,notanumber\n", "text/csv")},
    )
    assert bad.status_code == 400
    rc = (await priya.post("/api/v1/strategy/themes/recompute")).json()
    assert rc["status"] in ("done", "queued")
    fb = (await priya.get("/api/v1/feedback", params={"limit": 5})).json()
    assert len(fb) == 5


async def test_meeting_prep_and_decisions(priya: httpx.AsyncClient) -> None:
    prog = (await priya.get("/api/v1/programs")).json()[0]
    people = {p["name"]: p["id"] for p in (await priya.get("/api/v1/people")).json()}
    prep = (
        await priya.post(
            "/api/v1/comms/meeting-prep",
            json={
                "meeting_title": "Payments sync",
                "program_id": prog["id"],
                "attendee_ids": [people["Vikram Rao"], people["Karan Malhotra"]],
            },
        )
    ).json()
    assert prep["talking_points"] and prep["citations"]
    hits = (await priya.get("/api/v1/decisions", params={"q": "Kafka"})).json()
    assert any("Kafka" in d["title"] for d in hits)
    new = await priya.post(
        "/api/v1/decisions",
        json={"program_id": prog["id"], "title": "Freeze API v2 schema", "chosen_option": "Freeze"},
    )
    assert new.status_code == 201
    pasted = await priya.post(
        "/api/v1/comms/extract",
        json={
            "transcript_text": (
                "Priya: let's go with weekly demos.\nPriya: Karan, can you book the room by Monday?"
            )
        },
    )
    out = pasted.json()
    assert len(out["decisions"]) == 1 and out["action_items"][0]["owner_name"] == "Karan Malhotra"
