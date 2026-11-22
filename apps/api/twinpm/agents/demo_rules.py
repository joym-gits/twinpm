"""Deterministic routing, tool choice and answer templates for DemoChatModel.

Answers are written only from real tool results, so demo mode shows the product's actual
computed state (health, risks, forecasts, candidates), not canned text.
"""

from __future__ import annotations

import json
import re
from typing import Any

AGENTS = ("strategy", "planner", "delegation", "risk", "comms", "insights")
ROUTES: list[tuple[tuple[str, ...], list[str]]] = [
    (
        (
            "what should i do",
            "what do i do",
            "options",
            "recommend",
            "how do we recover",
            "get back on track",
        ),
        ["risk", "planner", "delegation"],
    ),
    (
        (
            "status report",
            "exec update",
            "executive update",
            "write an update",
            "summarise for",
            "summarize for",
        ),
        ["comms"],
    ),
    (("transcript", "action item", "meeting notes", "meeting prep"), ["comms"]),
    (("decision", "decided", "why did we", "kafka", "sqs"), ["comms"]),
    (("feedback", "customer", "theme", "prd", "okr", "opportunit"), ["strategy"]),
    (
        (
            "who should",
            "reassign",
            "workload",
            "overload",
            "utilisation",
            "utilization",
            "nudge",
            "stalled",
            "rebalance",
            "delegate",
        ),
        ["delegation"],
    ),
    (
        (
            "velocity",
            "metric",
            "review latency",
            "cycle time",
            "throughput",
            "anomal",
            "sentiment",
            "team health",
            "bug inflow",
        ),
        ["insights"],
    ),
    (
        ("estimate", "break down", "breakdown", "scenario", "roadmap", "capacity", "sprint"),
        ["planner"],
    ),
    (("risk", "critical path", "dependenc", "forecast", "p80", "slip", "late", "launch"), ["risk"]),
]
METRIC_WORDS = {
    "review latency": "review_latency_p50",
    "review": "review_latency_p50",
    "cycle": "cycle_time_p50",
    "throughput": "throughput",
    "bug": "bug_inflow",
    "wip": "wip",
    "velocity": "velocity",
}
KEY = re.compile(r"\b[A-Z]{2,5}-\d{2,4}\b")


def route(question: str) -> list[str]:
    q = question.lower()
    for words, plan in ROUTES:
        if any(w in q for w in words):
            return plan
    return ["risk"]


def _called(results: dict[str, list[Any]], name: str) -> bool:
    return name in results


def next_tool_calls(
    agent: str, question: str, available: list[str], results: dict[str, list[Any]]
) -> list[tuple[str, dict[str, Any]]]:
    q = question.lower()
    plan: list[tuple[str, dict[str, Any]]] = []
    if agent == "risk":
        plan = [
            ("get_risky_items", {"min_score": 0.65}),
            ("run_forecast", {}),
            ("get_dependency_graph", {}),
        ]
        m = re.search(r"slip(?:s|ping)?\s+(?:by\s+)?(\d{1,3})\s*days?", q)
        if m:
            plan.append(
                ("impact_analysis", {"entity": "Payments API v2", "slip_days": int(m.group(1))})
            )
    elif agent == "planner":
        if "estimate" in q or "break" in q:
            plan = [("estimate_effort", {"titles": [question[:120]]})]
        elif "roadmap" in q:
            plan = [("get_roadmap", {})]
        else:
            plan = [("compare_options", {})]
    elif agent == "delegation":
        plan = [("get_workload", {})]
        keys = KEY.findall(question)
        if keys:
            plan.append(("rank_candidates", {"work_item": keys[0]}))
        if any(w in q for w in ("stalled", "nudge", "follow up", "follow-up")):
            plan.append(("find_stalled_items", {}))
        if any(w in q for w in ("what should", "rebalance", "recommend", "options", "recover")):
            plan.append(("propose_rebalance", {}))
    elif agent == "comms":
        if any(w in q for w in ("decision", "decided", "kafka", "sqs", "why did we")):
            plan = [
                (
                    "search_decisions",
                    {"query": "Kafka SQS" if "kafka" in q or "sqs" in q else question[:80]},
                )
            ]
        elif any(w in q for w in ("transcript", "action item", "meeting notes")):
            plan = [("extract_actions", {"document": "Architecture sync"})]
        else:
            plan = [("get_program_snapshot", {})]
    elif agent == "strategy":
        plan = [("get_themes", {})]
        if "feedback" in q or "customer" in q:
            plan.append(("search_feedback", {"query": question[:120]}))
    elif agent == "insights":
        metric = next((v for k, v in METRIC_WORDS.items() if k in q), "velocity")
        team = next((t for t in ("Payments", "Platform", "Mobile") if t.lower() in q), None)
        days = 56
        m = re.search(r"(\d{1,3})\s*(day|week)", q)
        if m:
            days = int(m.group(1)) * (7 if m.group(2) == "week" else 1)
        plan = [
            ("query_metric", {"metric": metric, "team": team, "days": max(7, min(days, 365))}),
            ("get_anomalies", {}),
        ]
        if "health" in q or "sentiment" in q:
            plan.append(("get_team_health", {}))
    pending = [(n, a) for n, a in plan if n in available and not _called(results, n)]
    # Tools within one stage run in parallel; propose_* waits for the reads before it.
    reads = [(n, a) for n, a in pending if not n.startswith("propose_")]
    return reads or pending[:1]


def _data(results: dict[str, list[Any]], name: str) -> Any:
    vals = results.get(name) or [{}]
    return vals[-1].get("data") if isinstance(vals[-1], dict) else None


def _fmt_date(s: Any) -> str:
    return str(s) if s else "unknown"


def compose(agent: str, question: str, results: dict[str, list[Any]], system: str = "") -> str:
    fn = {
        "risk": _risk,
        "planner": _planner,
        "delegation": _delegation,
        "comms": _comms,
        "strategy": _strategy,
        "insights": _insights,
        "compose": _final,
    }.get(agent, _generic)
    return fn(question, results)


def _risk(q: str, r: dict[str, list[Any]]) -> str:
    items = _data(r, "get_risky_items") or []
    fc = _data(r, "run_forecast") or {}
    g = _data(r, "get_dependency_graph") or {}
    imp = _data(r, "impact_analysis")
    if not items and not fc:
        return "I could not find delay-risk data for this program yet."
    by_epic: dict[str, list[dict[str, Any]]] = {}
    for i in items:
        by_epic.setdefault(i.get("epic") or "Other", []).append(i)
    top_epic, top = max(by_epic.items(), key=lambda kv: len(kv[1])) if by_epic else ("", [])
    drivers: list[str] = []
    for i in top:
        drivers += [d for d in i.get("drivers", []) if d not in drivers]
    late = fc.get("days_late_at_p80")
    parts = []
    if top:
        parts.append(
            f"The biggest threat is {top_epic}: {len(top)} open items are above 65% "
            f"delay risk ({', '.join(i['key'] for i in top[:4])}). Main drivers: "
            f"{'; '.join(drivers[:3])}."
        )
    if fc:
        moved = ""
        if fc.get("p80_two_weeks_ago"):
            moved = f", up from {fc['p80_two_weeks_ago']} two weeks ago"
        parts.append(
            f"Launch P80 is {_fmt_date(fc.get('p80'))}{moved}, "
            f"{late} days {'after' if (late or 0) > 0 else 'before'} the "
            f"{_fmt_date(fc.get('target'))} target."
        )
    if g.get("critical_path"):
        parts.append("Critical path: " + " → ".join(g["critical_path"]) + ".")
    if imp:
        parts.append(imp.get("narrative", ""))
    return " ".join(p for p in parts if p)


def _planner(q: str, r: dict[str, list[Any]]) -> str:
    opts = (_data(r, "compare_options") or {}).get("options", [])
    if opts:
        lines = ["Three options, each simulated 10,000 times:"]
        for i, o in enumerate(opts, 1):
            vs = o.get("days_vs_target", 0)
            lines.append(
                f"{i}. {o['name']}: {o['description']}. P80 {o['p80']} "
                f"({o['delta_days']:+d} days; {abs(vs)} days "
                f"{'after' if vs > 0 else 'before'} target)."
            )
        best = min(
            opts, key=lambda o: (o["days_vs_target"] > 0, o["name"] != "Rebalance", o["delta_days"])
        )
        lines.append(
            f"I recommend {best['name']}: it recovers the most time without cutting "
            "launch scope or moving the date."
        )
        return "\n".join(lines)
    est = _data(r, "estimate_effort")
    if est:
        e = est[0]
        return (
            f"Estimate: {e['estimate_days']} days (80% interval {e['p10_days']}-"
            f"{e['p90_days']}), based on similar items "
            + ", ".join(s["key"] for s in e["similar"])
            + "."
        )
    rm = _data(r, "get_roadmap")
    if rm:
        return " ".join(
            f"{b.title()}: " + ", ".join(c["title"] for c in cards) + "." for b, cards in rm.items()
        )
    return "I don't have enough planning data to answer that."


def _delegation(q: str, r: dict[str, list[Any]]) -> str:
    wl = _data(r, "get_workload") or []
    parts = []
    hot = [p for p in wl if p.get("overloaded")]
    cool = sorted(wl, key=lambda p: p["utilisation"])[:2]
    if hot:
        parts.append(
            "Overloaded: "
            + ", ".join(f"{p['name']} ({p['utilisation']:.0%})" for p in hot[:3])
            + "."
        )
    if cool:
        parts.append(
            "Most headroom: "
            + ", ".join(
                f"{p['name']} ({p['utilisation']:.0%}, {', '.join(p['top_skills'])})" for p in cool
            )
            + "."
        )
    ranked = _data(r, "rank_candidates")
    if ranked:
        c = ranked["candidates"][0]
        parts.append(f"Best owner for {ranked['work_item']}: {c['explanation']}")
    moves = _data(r, "propose_rebalance") or []
    if moves:
        parts.append(
            "Proposed rebalance: "
            + "; ".join(f"{mv['key']} → {mv['to']}" for mv in moves)
            + ". Each move is waiting for your "
            "approval."
        )
    stalled = _data(r, "find_stalled_items") or []
    if stalled:
        parts.append(
            f"{len(stalled)} items look stalled, e.g. "
            + ", ".join(
                f"{s['key']} ({s['days']:.0f}d {s['status'].replace('_', ' ')})"
                for s in stalled[:3]
            )
            + "."
        )
    return " ".join(parts) or "No workload data available."


def _comms(q: str, r: dict[str, list[Any]]) -> str:
    dec = _data(r, "search_decisions")
    if dec:
        d = dec[0]
        rationale = re.sub(r"</?untrusted[-_]content[^>]*>", "", d["rationale"]).strip()
        return (
            f"Decision: {d['title']} (decided {d['decided']}). Chosen: {d['chosen']}. "
            f"Rationale: {rationale[:400]}"
        )
    ex = _data(r, "extract_actions")
    if ex:
        lines = [
            f"I found {len(ex['decisions'])} decisions and {len(ex['action_items'])} action items."
        ]
        lines += [f"- Decision: {d['title']}" for d in ex["decisions"]]
        lines += [
            f"- {a['owner_name']}: {a['title']} (due {a['due_date']})" for a in ex["action_items"]
        ]
        return "\n".join(lines)
    snap = _data(r, "get_program_snapshot")
    if snap:
        fc = snap["forecast"]
        return (
            f"{snap['program']}: health {snap['health']:.0f}, launch P80 {fc['p80']} vs "
            f"target {fc['target']}. {snap['completed_last_14d']} items shipped in two "
            f"weeks. Top risk: {snap['top_risks'][0]['title'] if snap['top_risks'] else 'none'}."
        )
    return "No communication data available."


def _strategy(q: str, r: dict[str, list[Any]]) -> str:
    themes = _data(r, "get_themes") or []
    if not themes:
        return "There are no feedback themes yet."
    top = themes[0]
    lines = [
        f"Top opportunity: {top['label']} ({top['size']} items, sentiment "
        f"{top['avg_sentiment']:+.2f}, score {top['opportunity']})."
    ]
    lines += [f"- {t['label']}: {t['size']} items, score {t['opportunity']}" for t in themes[1:5]]
    return "\n".join(lines)


def _insights(q: str, r: dict[str, list[Any]]) -> str:
    qm = _data(r, "query_metric") or {}
    parts = []
    for s in qm.get("series", []):
        a, b = s["first_half_mean"], s["second_half_mean"]
        ch = (b - a) / a if a else 0.0
        parts.append(
            f"{s['team']} {qm['metric'].replace('_', ' ')}: {b:.1f} recently vs "
            f"{a:.1f} earlier ({ch:+.0%})"
            + (f", {s['anomalous_days']} anomalous days" if s["anomalous_days"] else "")
            + "."
        )
    an = _data(r, "get_anomalies") or []
    if an:
        parts.append("Top anomaly: " + an[0]["explanation"])
    th = _data(r, "get_team_health")
    if th:
        parts += [
            f"{t['team']} sentiment {t['sentiment_index']:.2f} ({t['sentiment_trend']:+.2f})."
            for t in th
            if not t["suppressed"]
        ]
    return " ".join(parts) or "No metric data for that question."


def _generic(q: str, r: dict[str, list[Any]]) -> str:
    return "I don't have a tool that answers that yet."


def _final(q: str, r: dict[str, list[Any]]) -> str:
    try:
        payload = json.loads(q)
    except json.JSONDecodeError:
        return q
    name = payload.get("first_name") or "there"
    findings: dict[str, str] = payload.get("findings", {})
    actions = payload.get("actions", [])
    order = [
        a
        for a in ("risk", "planner", "delegation", "comms", "strategy", "insights")
        if a in findings
    ]
    if (
        payload.get("question", "").lower().startswith(("what should", "what do"))
        and "planner" in findings
    ):
        lines = [f"Here's what I'd do, {name}."]
    else:
        lines = []
    labels = {
        "risk": "Risk",
        "planner": "Options",
        "delegation": "Delegation",
        "comms": "Comms",
        "strategy": "Strategy",
        "insights": "Insights",
    }
    for a in order:
        lines.append(f"**{labels[a]}.** {findings[a]}")
    if actions:
        lines.append(
            f"{len(actions)} action{'s are' if len(actions) != 1 else ' is'} ready for "
            "your approval. Nothing changes until you approve."
        )
    return "\n\n".join(lines) if lines else "I couldn't find anything to report."
