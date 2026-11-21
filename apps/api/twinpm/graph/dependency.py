"""Program dependency graph (NetworkX): critical path, slack and slip cascades."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from twinpm.domain import PROGRAM_ALLOCATION, SPRINT_DAYS
from twinpm.ml.data import ProgramData
from twinpm.ml.features import FeatureBuilder


@dataclass
class GraphResult:
    graph: nx.DiGraph[Any]
    critical_path: list[Any]
    finish_days: float


def _team_daily(data: ProgramData) -> dict[Any, float]:
    fb = FeatureBuilder(data)
    now = pd.Timestamp(data.now)
    out = {}
    for t in data.teams["id"]:
        v = fb.sprint_velocities(t, now, 6)
        out[t] = max(float(np.mean(v)) if v else 20.0, 1.0) * PROGRAM_ALLOCATION / SPRINT_DAYS
    return out


def build(data: ProgramData, risks: dict[Any, float], scope: set[Any] | None = None) -> GraphResult:
    """Epics and open dependent work items as a DAG with CPM timing.

    Epic duration = remaining points (plus expected overrun) / team daily program throughput.
    Edges are `blocks` dependencies. Forward/backward passes give earliest/latest finish and
    slack; zero-slack nodes on the longest path are the critical path.
    """
    g: nx.DiGraph[Any] = nx.DiGraph()
    it = data.items
    epics = data.epics if scope is None else data.epics[data.epics["id"].isin(scope)]
    daily = _team_daily(data)
    team_name = data.teams.set_index("id")["name"].to_dict()
    for e in epics.itertuples():
        items = it[(it["epic_id"] == e.id) & (it["status"] != "done")]
        work = float(
            sum(
                p * (1 + 0.75 * risks.get(w, 0.25))
                for w, p in zip(items["id"], items["story_points"], strict=True)
            )
        )
        days = work / daily.get(e.team_id, 2.0) if work else 0.0
        mean_risk = float(np.mean([risks.get(w, 0.0) for w in items["id"]])) if len(items) else 0
        g.add_node(
            e.id,
            kind="epic",
            label=e.title,
            key=e.key,
            team_id=e.team_id,
            team=team_name.get(e.team_id),
            status=e.status,
            duration=round(days, 1),
            scope_points=float(items["story_points"].sum()),
            open_items=len(items),
            risk=round(mean_risk, 3),
        )
    deps = data.deps
    for d in deps.itertuples():
        if d.from_type == "epic" and d.to_type == "epic" and d.from_id in g and d.to_id in g:
            g.add_edge(d.from_id, d.to_id, kind=d.kind, status=d.status, level="epic")
    items_by_id = it.set_index("id")
    for d in deps.itertuples():
        if d.from_type != "work_item" or d.to_type != "work_item":
            continue
        if d.from_id not in items_by_id.index or d.to_id not in items_by_id.index:
            continue
        a, b = items_by_id.loc[d.from_id], items_by_id.loc[d.to_id]
        if a["epic_id"] not in g or b["epic_id"] not in g:
            continue
        for wid, r in ((d.from_id, a), (d.to_id, b)):
            if wid not in g:
                g.add_node(
                    wid,
                    kind="work_item",
                    label=r["title"],
                    key=r["key"],
                    team_id=r["team_id"],
                    team=team_name.get(r["team_id"]),
                    status=r["status"],
                    duration=0.0,
                    scope_points=float(r["story_points"]),
                    open_items=1,
                    risk=round(risks.get(wid, 0.0), 3),
                    epic_id=r["epic_id"],
                )
        g.add_edge(d.from_id, d.to_id, kind=d.kind, status=d.status, level="work_item")
    _cpm(g)
    epic_nodes = [n for n, a in g.nodes(data=True) if a["kind"] == "epic"]
    finish = max((g.nodes[n]["ef"] for n in epic_nodes), default=0.0)
    path = _critical_chain(g, epic_nodes)
    for n in g.nodes:
        g.nodes[n]["critical"] = n in path or (
            g.nodes[n]["kind"] == "work_item"
            and g.nodes[n].get("epic_id") in path
            and g.nodes[n]["status"] != "done"
        )
    return GraphResult(g, path, round(finish, 1))


def _cpm(g: nx.DiGraph[Any]) -> None:
    epic_g = g.subgraph(n for n, a in g.nodes(data=True) if a["kind"] == "epic")
    order = (
        list(nx.topological_sort(epic_g))
        if nx.is_directed_acyclic_graph(epic_g)
        else list(epic_g.nodes)
    )
    for n in order:
        es = max((g.nodes[p]["ef"] for p in epic_g.predecessors(n)), default=0.0)
        g.nodes[n]["es"], g.nodes[n]["ef"] = es, es + g.nodes[n]["duration"]
    finish = max((g.nodes[n]["ef"] for n in order), default=0.0)
    for n in reversed(order):
        lf = min((g.nodes[s]["ls"] for s in epic_g.successors(n)), default=finish)
        g.nodes[n]["lf"], g.nodes[n]["ls"] = lf, lf - g.nodes[n]["duration"]
        g.nodes[n]["slack"] = round(lf - g.nodes[n]["ef"], 1)
    for _, a in g.nodes(data=True):
        if a["kind"] == "work_item":
            parent = g.nodes.get(a.get("epic_id"), {})
            a.update(
                es=parent.get("es", 0.0), ef=parent.get("ef", 0.0), slack=parent.get("slack", 0.0)
            )


def _critical_chain(g: nx.DiGraph[Any], epic_nodes: list[Any]) -> list[Any]:
    """Follow zero-slack epics backward from the latest-finishing one."""
    if not epic_nodes:
        return []
    end = max(epic_nodes, key=lambda n: g.nodes[n]["ef"])
    chain = [end]
    while True:
        preds = [
            p
            for p in g.predecessors(chain[-1])
            if g.nodes[p]["kind"] == "epic"
            and abs(g.nodes[p]["ef"] - g.nodes[chain[-1]]["es"]) < 1e-6
        ]
        if not preds:
            break
        chain.append(max(preds, key=lambda p: g.nodes[p]["duration"]))
    return list(reversed(chain))


def downstream(g: nx.DiGraph[Any], node: Any) -> list[Any]:
    """Everything that (transitively) waits on `node`, including its epic's dependents."""
    starts = {node}
    attrs = g.nodes.get(node, {})
    if attrs.get("kind") == "work_item" and attrs.get("epic_id") in g:
        starts.add(attrs["epic_id"])
    out: set[Any] = set()
    for s in starts:
        out |= nx.descendants(g, s)
    return [n for n in out if n != node]


def to_uuid(v: Any) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
