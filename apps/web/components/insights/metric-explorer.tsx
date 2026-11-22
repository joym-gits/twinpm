"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, Skeleton, SkeletonLoader } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { shortDate } from "@/lib/format";
import { useUi } from "@/lib/store";
import { AnomalyPoints, SeriesChart } from "./series-chart";

export const METRICS: Record<string, { label: string; unit: string }> = {
  velocity: { label: "Velocity", unit: "pts" },
  throughput: { label: "Throughput", unit: "items/wk" },
  cycle_time_p50: { label: "Cycle time (p50)", unit: "days" },
  bug_inflow: { label: "Bug inflow", unit: "bugs/wk" },
  review_latency_p50: { label: "Review latency (p50)", unit: "h" },
  wip: { label: "Work in progress", unit: "items" },
};

const iso = (d: Date) => d.toISOString().slice(0, 10);

export function MetricExplorer({ programId }: { programId: string }) {
  const [metric, setMetric] = useState("velocity");
  const [teamId, setTeamId] = useState("");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 90 * 86_400_000)));
  const [to, setTo] = useState(() => iso(new Date()));
  const setPageContext = useUi((s) => s.setPageContext);
  const teams = useQuery({ queryKey: ["teams"], queryFn: async () => unwrap(await api.GET("/api/v1/teams")) });
  const q = useQuery({
    queryKey: ["metrics", metric, teamId, from, to],
    enabled: from <= to,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/insights/metrics", { params: { query: { metric, team_id: teamId || null, from: from || null, to: to || null } } })),
  });
  const series = useMemo(() => (q.data ?? []).map((s) => ({ name: s.team, data: s.points })), [q.data]);
  const unit = ` ${METRICS[metric]!.unit}`;

  useEffect(() => {
    setPageContext({ screen: "insights", program_id: programId, metric, team_id: teamId || null, from, to });
  }, [programId, metric, teamId, from, to, setPageContext]);

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle>Metric explorer</CardTitle>
          <CardDescription>Team delivery metrics with anomalies flagged by the detector.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="m-metric">Metric</Label>
            <Select id="m-metric" value={metric} onChange={(e) => setMetric(e.target.value)}>
              {Object.entries(METRICS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="m-team">Team</Label>
            <Select id="m-team" value={teamId} onChange={(e) => setTeamId(e.target.value)} disabled={teams.isLoading}>
              <option value="">All teams</option>
              {teams.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="m-from">From</Label>
            <Input id="m-from" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="m-to">To</Label>
            <Input id="m-to" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className="w-40" />
          </div>
        </div>
        {from > to && <p role="alert" className="text-sm text-danger">The start date must be before the end date.</p>}
        {q.isLoading && <Skeleton className="h-72" />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && series.every((s) => !s.data.length) && <EmptyState title="No data in this range" description="Widen the date range or pick another team." />}
        {q.data && series.some((s) => s.data.length) && (
          <div className="space-y-3" data-testid="metric-chart">
            <SeriesChart series={series} unit={unit} label={`${METRICS[metric]!.label} from ${shortDate(from)} to ${shortDate(to)}`} />
            <div>
              <h3 className="mb-1 text-xs font-medium">Anomalous points</h3>
              <AnomalyPoints series={series} unit={unit} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function AnomalyList() {
  const q = useQuery({ queryKey: ["anomalies"], queryFn: async () => unwrap(await api.GET("/api/v1/insights/anomalies")) });
  const teams = useQuery({ queryKey: ["teams"], queryFn: async () => unwrap(await api.GET("/api/v1/teams")) });
  const teamName = (id: string) => teams.data?.find((t) => t.id === id)?.name;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Open anomalies</CardTitle>
          <CardDescription>What the detector flagged, and its explanation.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {q.isLoading && <SkeletonLoader rows={4} className="p-0" />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && <EmptyState title="No open anomalies" />}
        <ul className="space-y-3" data-testid="anomaly-list">
          {q.data?.map((a) => (
            <li key={a.id} className="flex gap-2 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
              <div className="min-w-0 space-y-0.5">
                <p>{a.explanation}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Badge>{METRICS[a.metric]?.label ?? a.metric}</Badge>
                  {teamName(a.team_id) && <span>{teamName(a.team_id)}</span>}
                  <span>{shortDate(a.date)}</span>
                  <span className="tabular-nums">
                    {a.value.toFixed(1)} vs expected {a.expected.toFixed(1)} (z {a.z_score.toFixed(1)})
                  </span>
                  <span>{a.method}</span>
                </p>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
