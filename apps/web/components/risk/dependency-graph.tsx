"use client";

import "@xyflow/react/dist/style.css";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { ExternalLink, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, Skeleton, SkeletonLoader } from "@/components/ui/states";
import { DriverList, type DriverLike } from "@/components/twin/driver-list";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { riskLevel, shortDate } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

type GNode = Schemas["GraphNode"];
type Affected = { id: string; label: string; kind: string; team: string | null };

/** Categorical palette, assigned to teams in name order so a team keeps its colour across renders. */
const PALETTE = ["#2563eb", "#0d9488", "#9333ea", "#ea580c", "#db2777", "#65a30d", "#0891b2", "#ca8a04"];
const RISK_BORDER = { Low: 1, Medium: 2, High: 3, Critical: 4 } as const;
const RISK_COLOR = { Low: "var(--color-success)", Medium: "var(--color-warning)", High: "var(--color-danger)", Critical: "var(--color-danger)" } as const;
const COL_W = 300;
const EPIC_H = 88;
const ITEM_H = 52;
const GAP = 28;

type NodeData = GNode & { color: string; impacted: boolean; dimmed: boolean; selected: boolean };
type RNode = Node<NodeData, "twin">;

function TwinNode({ data }: NodeProps<RNode>) {
  const level = riskLevel(data.risk);
  const epic = data.kind === "epic";
  const width = epic ? 180 + Math.min(80, Math.sqrt(data.scope_points) * 6) : 200;
  return (
    <div
      className={cn(
        "rounded-lg bg-surface px-2.5 py-1.5 text-left text-xs shadow-sm transition-opacity",
        data.critical && "ring-2 ring-danger ring-offset-2 ring-offset-bg",
        data.impacted && "outline-2 outline-dashed outline-offset-4 outline-accent",
        data.selected && "shadow-lg",
        data.dimmed && "opacity-40",
      )}
      style={{ width, borderStyle: "solid", borderWidth: RISK_BORDER[level], borderColor: RISK_COLOR[level], borderLeft: `6px solid ${data.color}` }}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="flex items-center justify-between gap-1">
        <span className="truncate font-mono text-[10px] text-muted">{data.key ?? (epic ? "Epic" : "Item")}</span>
        <RiskBadge probability={data.risk} showValue={false} />
      </div>
      <p className={cn("truncate font-medium", epic ? "text-sm" : "")}>{data.label}</p>
      <div className="flex flex-wrap gap-x-2 text-[10px] text-muted">
        <span>{data.team ?? "No team"}</span>
        {epic && <span>{data.scope_points} pts</span>}
        {data.critical && <span className="font-semibold text-danger">Critical path</span>}
        {data.impacted && <span className="font-semibold text-accent">Impacted</span>}
      </div>
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}
const nodeTypes = { twin: TwinNode };

/** Layered layout: epics by longest-path depth over epic edges; work items stacked under their epic. */
export function layout(graph: Schemas["GraphOut"]): Map<string, { x: number; y: number }> {
  const epics = graph.nodes.filter((n) => n.kind === "epic");
  const epicIds = new Set(epics.map((e) => e.id));
  const epicOf = (id: string) => (epicIds.has(id) ? id : graph.nodes.find((n) => n.id === id)?.epic_id ?? id);
  const preds = new Map<string, Set<string>>(epics.map((e) => [e.id, new Set()]));
  for (const e of graph.edges) {
    const s = epicOf(e.source);
    const t = epicOf(e.target);
    if (s !== t && preds.has(t) && epicIds.has(s)) preds.get(t)!.add(s);
  }
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  const d = (id: string): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (visiting.has(id)) return 0; // cycle guard
    visiting.add(id);
    const v = Math.max(-1, ...[...(preds.get(id) ?? [])].map(d)) + 1;
    visiting.delete(id);
    depth.set(id, v);
    return v;
  };
  const items = new Map<string, GNode[]>();
  for (const n of graph.nodes) if (n.kind === "work_item" && n.epic_id) items.set(n.epic_id, [...(items.get(n.epic_id) ?? []), n]);
  const pos = new Map<string, { x: number; y: number }>();
  const colY = new Map<number, number>();
  for (const e of [...epics].sort((a, b) => d(a.id) - d(b.id) || a.label.localeCompare(b.label))) {
    const col = d(e.id);
    const x = col * COL_W;
    let y = colY.get(col) ?? 0;
    pos.set(e.id, { x, y });
    y += EPIC_H;
    for (const w of items.get(e.id) ?? []) {
      pos.set(w.id, { x: x + 24, y });
      y += ITEM_H;
    }
    colY.set(col, y + GAP);
  }
  // Orphan work items (epic not in graph) go in a trailing column.
  let oy = 0;
  const lastX = (Math.max(-1, ...colY.keys()) + 1) * COL_W;
  for (const n of graph.nodes) if (!pos.has(n.id)) pos.set(n.id, { x: lastX, y: (oy += ITEM_H) });
  return pos;
}

function NodeDetails({ node, onOpen }: { node: GNode; onOpen: () => void }) {
  const q = useQuery({
    queryKey: ["entity", "work_item", node.id],
    enabled: node.kind === "work_item",
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/entities/{entity_type}/{entity_id}", { params: { path: { entity_type: "work_item", entity_id: node.id } } })),
  });
  const f = (q.data?.fields ?? {}) as { drivers?: DriverLike[]; delay_probability?: number };
  return (
    <div className="space-y-3 text-sm" aria-live="polite">
      <div>
        <p className="font-mono text-xs text-muted">{node.key ?? (node.kind === "epic" ? "Epic" : "Work item")}</p>
        <h3 className="font-semibold">{node.label}</h3>
        <p className="text-xs text-muted">
          {node.team ?? "No team"} · {node.status}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <RiskBadge probability={f.delay_probability ?? node.risk} />
        {node.critical && <Badge tone="danger">Critical path</Badge>}
      </div>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded-lg bg-surface-2 p-2">
          <dt className="text-muted">Slack</dt>
          <dd className="font-semibold tabular-nums">{node.slack_days.toFixed(1)}d</dd>
        </div>
        <div className="rounded-lg bg-surface-2 p-2">
          <dt className="text-muted">Open items</dt>
          <dd className="font-semibold tabular-nums">{node.open_items}</dd>
        </div>
        <div className="rounded-lg bg-surface-2 p-2">
          <dt className="text-muted">Duration</dt>
          <dd className="font-semibold tabular-nums">{node.duration_days.toFixed(1)}d</dd>
        </div>
      </dl>
      {node.kind === "work_item" && (
        <div>
          <h4 className="mb-1.5 text-xs font-medium">Why it may slip</h4>
          {q.isLoading && <SkeletonLoader rows={3} className="p-0" />}
          {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
          {q.data && <DriverList drivers={f.drivers ?? []} />}
        </div>
      )}
      <Button size="sm" variant="outline" onClick={onOpen}>
        <ExternalLink /> Open details
      </Button>
    </div>
  );
}

export function DependencyGraph({ programId }: { programId: string }) {
  const openEntity = useUi((s) => s.openEntity);
  const setPageContext = useUi((s) => s.setPageContext);
  const q = useQuery({
    queryKey: ["dep-graph", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/dependencies/graph", { params: { query: { program_id: programId } } })),
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [slipId, setSlipId] = useState<string>("");
  const [slipDays, setSlipDays] = useState(9);
  const impact = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/dependencies/impact", { body: { entity_id: slipId, slip_days: slipDays } })),
  });

  const graph = q.data;
  const byId = useMemo(() => new Map(graph?.nodes.map((n) => [n.id, n]) ?? []), [graph]);
  const teams = useMemo(() => [...new Set(graph?.nodes.map((n) => n.team ?? "No team") ?? [])].sort(), [graph]);
  const teamColor = useCallback((t: string | null) => PALETTE[Math.max(0, teams.indexOf(t ?? "No team")) % PALETTE.length]!, [teams]);
  const epics = useMemo(() => graph?.nodes.filter((n) => n.kind === "epic").sort((a, b) => a.label.localeCompare(b.label)) ?? [], [graph]);
  const workItems = useMemo(() => graph?.nodes.filter((n) => n.kind === "work_item") ?? [], [graph]);

  useEffect(() => {
    if (!graph || slipId) return;
    const def = epics.find((e) => e.label.includes("Payments API v2")) ?? epics.find((e) => e.critical) ?? epics[0];
    if (def) setSlipId(def.id);
  }, [graph, epics, slipId]);

  const selected = selectedId ? byId.get(selectedId) : undefined;
  useEffect(() => {
    setPageContext({
      screen: "risk_radar",
      program_id: programId,
      ...(selected && { selected_entity: { type: selected.kind, id: selected.id, label: selected.label, risk: selected.risk } }),
    });
  }, [selected, programId, setPageContext]);

  const affected = useMemo(() => (impact.data?.affected ?? []) as Affected[], [impact.data]);
  const impacted = useMemo(() => new Set(impact.data ? [impact.data.entity_id, ...affected.map((a) => a.id)] : []), [impact.data, affected]);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as RNode[], edges: [] as Edge[] };
    const pos = layout(graph);
    const nodes: RNode[] = graph.nodes.map((n) => ({
      id: n.id,
      type: "twin",
      position: pos.get(n.id)!,
      ariaLabel: `${n.kind === "epic" ? "Epic" : "Work item"} ${n.label}, ${riskLevel(n.risk)} risk${n.critical ? ", on critical path" : ""}${impacted.has(n.id) ? ", impacted by simulated slip" : ""}`,
      data: { ...n, color: teamColor(n.team), impacted: impacted.has(n.id), dimmed: impacted.size > 0 && !impacted.has(n.id), selected: n.id === selectedId },
    }));
    const edges: Edge[] = graph.edges.map((e) => {
      const hot = impacted.has(e.source) && impacted.has(e.target);
      const color = e.critical ? "var(--color-danger)" : hot ? "var(--accent)" : "var(--muted)";
      return {
        id: `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        animated: e.critical || hot,
        style: { stroke: color, strokeWidth: e.critical || hot ? 2.5 : 1.25, strokeDasharray: e.level === "work_item" ? "4 3" : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color },
        ariaLabel: `${byId.get(e.source)?.label} ${e.kind} ${byId.get(e.target)?.label}${e.critical ? ", critical" : ""}`,
      };
    });
    return { nodes, edges };
  }, [graph, impacted, selectedId, byId, teamColor]);

  if (q.isLoading) return <Card className="p-5"><Skeleton className="h-[560px]" /></Card>;
  if (q.isError || !graph) return <Card><ErrorState error={q.error} onRetry={() => void q.refetch()} /></Card>;
  if (!graph.nodes.length) return <Card><EmptyState title="No dependencies mapped" description="Epics and work items with dependencies will appear here." /></Card>;

  const slipNode = byId.get(slipId);
  return (
    <section aria-labelledby="graph-h" className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle id="graph-h">Dependency graph</CardTitle>
            <CardDescription>
              {graph.nodes.length} nodes · critical path {graph.critical_path.length} epics · finishes in {graph.finish_days} working days
            </CardDescription>
          </div>
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Team colours">
            {teams.map((t) => (
              <li key={t} className="flex items-center gap-1.5">
                <span className="h-3 w-1.5 rounded-sm" style={{ background: teamColor(t) }} aria-hidden />
                {t}
              </li>
            ))}
          </ul>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-muted">
            Border thickness and colour show risk level (also shown as text). Red ring and animated red edges mark the critical path; dashed edges are work-item
            dependencies. Select a node for details.
          </p>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="h-[560px] rounded-lg border border-border bg-bg" data-testid="dep-graph">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                minZoom={0.2}
                nodesDraggable={false}
                nodesConnectable={false}
                onNodeClick={(_, n) => setSelectedId(n.id)}
                proOptions={{ hideAttribution: true }}
              >
                <Background color="var(--border)" gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
            <aside aria-label="Node details" className="rounded-lg border border-border p-4">
              {selected ? (
                <NodeDetails node={selected} onOpen={() => openEntity({ type: selected.kind, id: selected.id, label: selected.key ?? selected.label })} />
              ) : (
                <EmptyState title="Select a node" description="Click an epic or work item to see its risk, slack and drivers. Nodes are also reachable with Tab and Enter." />
              )}
            </aside>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Simulate a slip</CardTitle>
            <CardDescription>What happens downstream if one piece of work lands late?</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (slipId) impact.mutate();
            }}
          >
            <div className="space-y-1">
              <Label htmlFor="slip-node">Node</Label>
              <Select id="slip-node" value={slipId} onChange={(e) => setSlipId(e.target.value)} className="w-72">
                <optgroup label="Epics">
                  {epics.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label}
                    </option>
                  ))}
                </optgroup>
                {workItems.length > 0 && (
                  <optgroup label="Work items">
                    {workItems.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.key} {n.label}
                      </option>
                    ))}
                  </optgroup>
                )}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="slip-days">Slip (days)</Label>
              <Input id="slip-days" type="number" min={1} max={60} value={slipDays} onChange={(e) => setSlipDays(Math.max(1, Number(e.target.value) || 1))} className="w-24" />
            </div>
            <Button type="submit" variant="accent" disabled={!slipId || impact.isPending}>
              <Zap /> {impact.isPending ? "Simulating…" : "Simulate slip"}
            </Button>
            {impact.data && (
              <Button type="button" variant="ghost" onClick={() => impact.reset()}>
                Clear highlight
              </Button>
            )}
          </form>
          {impact.isError && <ErrorState error={impact.error} onRetry={() => impact.mutate()} />}
          {impact.data && (
            <div className="space-y-3" aria-live="polite" data-testid="impact-result">
              <p className="text-sm">{impact.data.narrative}</p>
              <dl className="grid max-w-lg grid-cols-3 gap-2 text-sm">
                <div className="rounded-lg bg-surface-2 p-3">
                  <dt className="text-xs text-muted">Baseline P80</dt>
                  <dd className="font-semibold tabular-nums">{shortDate(impact.data.baseline_p80)}</dd>
                </div>
                <div className="rounded-lg bg-surface-2 p-3">
                  <dt className="text-xs text-muted">New P80</dt>
                  <dd className="font-semibold tabular-nums">{shortDate(impact.data.new_p80)}</dd>
                </div>
                <div className="rounded-lg bg-surface-2 p-3">
                  <dt className="text-xs text-muted">Change</dt>
                  <dd className={cn("font-semibold tabular-nums", impact.data.delta_days > 0 && "text-danger")}>
                    {impact.data.delta_days > 0 ? "+" : ""}
                    {impact.data.delta_days}d
                  </dd>
                </div>
              </dl>
              <div>
                <h3 className="mb-1 text-xs font-medium">
                  Cascade from {slipNode?.label ?? "selection"}: {affected.length} downstream {affected.length === 1 ? "node" : "nodes"} (outlined on the graph)
                </h3>
                {affected.length === 0 ? (
                  <p className="text-xs text-muted">Nothing depends on this node.</p>
                ) : (
                  <ul className="flex flex-wrap gap-1.5">
                    {affected.map((a) => (
                      <li key={a.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(a.id)}
                          className="rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs hover:border-accent"
                        >
                          {a.label} <span className="text-muted">· {a.kind === "epic" ? "epic" : "item"}{a.team ? ` · ${a.team}` : ""}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
