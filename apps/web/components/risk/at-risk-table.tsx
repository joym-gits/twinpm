"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { DriverList } from "@/components/twin/driver-list";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, unwrap } from "@/lib/api/client";
import { shortDate } from "@/lib/format";
import { useUi } from "@/lib/store";

const THRESHOLDS = [
  { value: 0.35, label: "Medium and above (≥35%)" },
  { value: 0.6, label: "High and above (≥60%)" },
  { value: 0.8, label: "Critical only (≥80%)" },
];

export function AtRiskTable({ programId }: { programId: string }) {
  const [minScore, setMinScore] = useState(0.35);
  const [epic, setEpic] = useState("");
  const [team, setTeam] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const openEntity = useUi((s) => s.openEntity);
  const setPageContext = useUi((s) => s.setPageContext);
  const q = useQuery({
    queryKey: ["risky", programId, minScore],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/risk/work-items", { params: { query: { program_id: programId, min_score: minScore, limit: 200 } } })),
  });
  const epics = useMemo(() => [...new Set(q.data?.map((r) => r.epic).filter((x): x is string => !!x))].sort(), [q.data]);
  const teams = useMemo(() => [...new Set(q.data?.map((r) => r.team).filter((x): x is string => !!x))].sort(), [q.data]);
  const rows = (q.data ?? []).filter((r) => (!epic || r.epic === epic) && (!team || r.team === team));

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle id="atrisk-h">At-risk work items</CardTitle>
          <CardDescription>Delay probability from the risk model, with its top contributing factors.</CardDescription>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="min-score">Minimum risk</Label>
            <Select id="min-score" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))}>
              {THRESHOLDS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="epic-filter">Epic</Label>
            <Select id="epic-filter" value={epic} onChange={(e) => setEpic(e.target.value)} className="max-w-56">
              <option value="">All epics</option>
              {epics.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="team-filter">Team</Label>
            <Select id="team-filter" value={team} onChange={(e) => setTeam(e.target.value)}>
              <option value="">All teams</option>
              {teams.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-2">
        {q.isLoading && <SkeletonLoader rows={6} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && rows.length === 0 && <EmptyState title="No items above this threshold" description="Lower the minimum risk or clear the filters." />}
        {rows.length > 0 && (
          <Table aria-labelledby="atrisk-h" data-testid="at-risk-table">
            <THead>
              <TR>
                <TH>Item</TH>
                <TH>Probability</TH>
                <TH>Top drivers</TH>
                <TH>Owner</TH>
                <TH>Due</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((r) => {
                const expanded = open === r.work_item_id;
                const toggle = () => {
                  setOpen(expanded ? null : r.work_item_id);
                  if (!expanded) setPageContext({ screen: "risk_radar", program_id: programId, selected_entity: { type: "work_item", id: r.work_item_id, label: r.key, risk: r.probability } });
                };
                return (
                  <Fragment key={r.work_item_id}>
                    <TR className="cursor-pointer" onClick={toggle}>
                      <TD>
                        <button
                          type="button"
                          className="flex items-start gap-1 text-left"
                          aria-expanded={expanded}
                          aria-controls={`drv-${r.work_item_id}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggle();
                          }}
                        >
                          <ChevronDown className={`mt-0.5 size-3.5 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden />
                          <span>
                            <span className="font-mono text-xs">{r.key}</span>
                            <span className="block max-w-64 truncate text-xs text-muted">{r.title}</span>
                          </span>
                        </button>
                      </TD>
                      <TD>
                        <RiskBadge probability={r.probability} />
                      </TD>
                      <TD className="max-w-72 text-xs text-muted">
                        {r.drivers.slice(0, 2).map((d) => (
                          <span key={d.feature} className="block truncate">
                            {d.label}
                          </span>
                        ))}
                      </TD>
                      <TD className="text-xs">{r.owner ?? "Unassigned"}</TD>
                      <TD className="text-xs tabular-nums">{shortDate(r.due_date)}</TD>
                    </TR>
                    {expanded && (
                      <tr id={`drv-${r.work_item_id}`}>
                        <td colSpan={5} className="bg-surface-2/60 px-6 py-3">
                          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
                            <DriverList drivers={r.drivers} />
                            <div className="space-y-1 text-xs text-muted">
                              <p>Epic: {r.epic ?? "—"}</p>
                              <p>Team: {r.team ?? "—"}</p>
                              <p>Status: {r.status}</p>
                              <p>Model {r.model_version}</p>
                              <Button size="sm" variant="outline" onClick={() => openEntity({ type: "work_item", id: r.work_item_id, label: r.key })}>
                                Open item
                              </Button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
