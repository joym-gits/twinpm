"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, Bot, ChevronDown, Play, User } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { EmptyState, ErrorState, Skeleton, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { DriverList, type DriverLike } from "@/components/twin/driver-list";
import { ForecastBand } from "@/components/twin/forecast-band";
import { HealthGauge, healthTone } from "@/components/twin/health-gauge";
import { RiskBadge } from "@/components/twin/risk-badge";
import { ApprovalCard } from "@/components/twin/suggestion-card";
import { TwinLabel } from "@/components/twin/twin-label";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { useMe, useProgramId } from "@/lib/auth/use-me";
import { relTime, shortDate } from "@/lib/format";
import { useSuggestions } from "@/lib/hooks/use-suggestions";
import { useUi } from "@/lib/store";

const SUB_LABEL: Record<string, string> = {
  schedule: "Schedule",
  scope: "Scope",
  quality: "Quality",
  dependencies: "Dependencies",
  team: "Team",
};
const SEV_TONE = { critical: "danger", high: "warning", medium: "accent", low: "neutral" } as const;

function HealthCard({ programId }: { programId: string }) {
  const q = useQuery({
    queryKey: ["health", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/programs/{program_id}/health", { params: { path: { program_id: programId } } })),
  });
  if (q.isLoading) return <Card className="p-5"><Skeleton className="h-48" /></Card>;
  if (q.isError || !q.data) return <Card><ErrorState error={q.error} onRetry={() => void q.refetch()} /></Card>;
  const h = q.data;
  return (
    <Card data-testid="health-card">
      <CardHeader>
        <div>
          <CardTitle>Program health</CardTitle>
          <CardDescription>Updated {shortDate(h.computed_at)}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <HealthGauge score={h.score} delta={h.delta_7d} size={180} />
          <div className="h-20 min-w-0 flex-1" aria-label="30-day health trend">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={h.trend}>
                <defs>
                  <linearGradient id="hg" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <YAxis hide domain={[40, 100]} />
                <XAxis dataKey="date" hide />
                <RTooltip formatter={(v) => [`${Math.round(Number(v))}`, "Health"]} labelFormatter={(l) => shortDate(String(l))} />
                <Area type="monotone" dataKey="score" stroke="var(--accent)" fill="url(#hg)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="flex flex-wrap gap-2" aria-label="Health sub-scores">
          {Object.entries(h.subscores).map(([k, v]) => {
            const tone = healthTone(v);
            const driver = h.drivers.find((d) => d.subscore === k);
            return (
              <Tooltip key={k} content={driver?.label ?? SUB_LABEL[k]}>
                <button type="button" className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs">
                  <span className="size-2 rounded-full" style={{ background: tone.color }} aria-hidden />
                  {SUB_LABEL[k]} <strong className="tabular-nums">{Math.round(v)}</strong>
                  <span className="sr-only">{tone.label}. {driver?.label}</span>
                </button>
              </Tooltip>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

type Option = {
  name: string;
  description: string;
  p80: string;
  delta_days: number;
  days_vs_target: number;
  risk_delta: number;
  moves?: { key: string; to_name: string; from_name?: string; explanation: string }[];
};

function OptionsDialog({ suggestionId, open, setOpen }: { suggestionId: string; open: boolean; setOpen: (o: boolean) => void }) {
  const { org } = useParams<{ org: string }>();
  const router = useRouter();
  const q = useQuery({
    queryKey: ["suggestion", suggestionId],
    enabled: open,
    queryFn: async () => unwrap(await api.GET("/api/v1/suggestions/{suggestion_id}", { params: { path: { suggestion_id: suggestionId } } })),
  });
  const payload = (q.data?.payload ?? {}) as { options?: Option[]; result?: { baseline_p80?: string } };
  const best = payload.options?.reduce<Option | undefined>(
    (b, o) => (!b || o.delta_days < b.delta_days ? o : b),
    undefined,
  );
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Options" description={`Simulated 10,000 times each. Baseline P80 ${shortDate(payload.result?.baseline_p80)}.`} className="w-[min(760px,94vw)]">
        {q.isLoading && <SkeletonLoader rows={5} />}
        <div className="grid gap-3 md:grid-cols-3" data-testid="options">
          {payload.options?.map((o) => (
            <Card key={o.name} className={`p-4 ${o === best ? "ring-2 ring-accent" : ""}`}>
              <div className="flex items-center justify-between">
                <p className="font-semibold">{o.name}</p>
                {o === best && <Badge tone="accent">Recommended</Badge>}
              </div>
              <p className="mt-1 text-xs text-muted">{o.description}</p>
              <p className="mt-3 text-2xl font-semibold tabular-nums">
                {o.delta_days > 0 ? "+" : ""}
                {o.delta_days}d
              </p>
              <p className="text-xs text-muted">
                P80 {shortDate(o.p80)} · {Math.abs(o.days_vs_target)}d {o.days_vs_target > 0 ? "late" : "early"}
              </p>
              {o.moves && o.moves.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs">
                  {o.moves.slice(0, 4).map((m) => (
                    <li key={m.key}>
                      {m.key} → {m.to_name}
                    </li>
                  ))}
                </ul>
              )}
              {o.name === "Rebalance" && (
                <Button size="sm" variant="accent" className="mt-3 w-full" onClick={() => router.push(`/${org}/delegation?rebalance=1`)}>
                  Choose rebalance <ArrowRight />
                </Button>
              )}
              {o.name !== "Rebalance" && (
                <Button size="sm" variant="outline" className="mt-3 w-full" onClick={() => router.push(`/${org}/roadmap`)}>
                  Explore in simulator
                </Button>
              )}
            </Card>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function BriefingCard({ item, twinName }: { item: Schemas["BriefingItem"]; twinName: string }) {
  const [why, setWhy] = useState(false);
  const [options, setOptions] = useState(false);
  const { org } = useParams<{ org: string }>();
  const router = useRouter();
  const action = item.recommended_action;
  return (
    <Card className="p-4" data-testid="briefing-item">
      <div className="flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-navy-900 text-xs font-bold text-white">{item.rank}</span>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Badge tone={SEV_TONE[item.severity]}>{item.severity}</Badge>
            <TwinLabel who={twinName} verb="Flagged by" />
          </div>
          <p className="text-sm font-medium leading-snug">{item.title}</p>
          {why && (
            <div className="space-y-3 rounded-lg bg-surface-2 p-3">
              <p className="text-sm text-muted">{item.why}</p>
              <DriverList drivers={item.drivers as unknown as DriverLike[]} />
              <Citations items={item.evidence as unknown as CitationLike[]} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant={item.rank === 1 ? "accent" : "outline"}
              onClick={() => (action.suggestion_id ? setOptions(true) : action.href && router.push(`/${org}${action.href}`))}
            >
              {action.label}
            </Button>
            <Button size="sm" variant="ghost" aria-expanded={why} onClick={() => setWhy((w) => !w)}>
              Why? <ChevronDown className={why ? "rotate-180" : ""} />
            </Button>
          </div>
        </div>
      </div>
      {action.suggestion_id && <OptionsDialog suggestionId={action.suggestion_id} open={options} setOpen={setOptions} />}
    </Card>
  );
}

function Briefing({ programId, twinName }: { programId: string; twinName: string }) {
  const q = useQuery({
    queryKey: ["briefing", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/programs/{program_id}/briefing", { params: { path: { program_id: programId } } })),
  });
  return (
    <section aria-labelledby="briefing-h" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="briefing-h" className="text-sm font-semibold">Morning briefing</h2>
        {q.data && <span className="text-xs text-muted">Generated {relTime(q.data.generated_at)}</span>}
      </div>
      {q.isLoading && [0, 1, 2].map((i) => <Card key={i} className="p-4"><Skeleton className="h-16" /></Card>)}
      {q.isError && <Card><ErrorState error={q.error} onRetry={() => void q.refetch()} /></Card>}
      {q.data?.items.length === 0 && <Card><EmptyState title="Nothing needs you right now" /></Card>}
      {q.data?.items.map((i) => <BriefingCard key={i.rank} item={i} twinName={twinName} />)}
    </section>
  );
}

function ForecastCard({ programId }: { programId: string }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const fc = useQuery({
    queryKey: ["forecast", programId],
    queryFn: async () => {
      const ms = unwrap(await api.GET("/api/v1/milestones", { params: { query: { program_id: programId } } }));
      const id = ms[0]?.id;
      if (!id) return null;
      return unwrap(await api.GET("/api/v1/forecasts/{milestone_id}", { params: { path: { milestone_id: id } } }));
    },
  });
  const run = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/forecasts/{milestone_id}/run", { params: { path: { milestone_id: fc.data!.milestone_id } } })),
    onSuccess: (d) => qc.setQueryData(["forecast", programId], d),
  });
  const f = run.data ?? fc.data;
  return (
    <Card data-testid="forecast-card">
      <CardHeader>
        <div>
          <CardTitle>{f?.milestone ?? "Launch"} forecast</CardTitle>
          <CardDescription>
            {f ? `Monte Carlo, ${f.assumptions.simulations as number} runs · ${relTime(f.run_at)}` : "Monte Carlo"}
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" disabled={!f || run.isPending} onClick={() => run.mutate()}>
          <Play /> {run.isPending ? "Running…" : "Run forecast"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {fc.isLoading && <Skeleton className="h-16" />}
        {fc.data === null && <EmptyState title="No milestone yet" />}
        {fc.isError && <ErrorState error={fc.error} />}
        {f && (
          <>
            <ForecastBand p50={f.p50} p80={f.p80} p95={f.p95} target={f.target_date} />
            {f.previous && (
              <p className="text-xs text-muted">
                Two weeks ago P80 was <strong>{shortDate(f.previous.p80)}</strong>
                {f.on_time_probability !== null && <> · on-time probability {Math.round((f.on_time_probability ?? 0) * 100)}%</>}
              </p>
            )}
            <Button size="sm" variant="link" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
              {expanded ? "Hide" : "Show"} distribution
            </Button>
            {expanded && (
              <div className="h-32" aria-label="Completion date distribution">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={f.histogram as { date: string; count: number }[]}>
                    <XAxis dataKey="date" tickFormatter={(d) => shortDate(String(d))} fontSize={10} />
                    <RTooltip labelFormatter={(l) => shortDate(String(l))} />
                    <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PendingSuggestions({ twinName }: { twinName: string }) {
  const q = useSuggestions({ status: "pending" });
  const items = (q.data ?? []).filter((s) => s.type !== "scenario").slice(0, 4);
  return (
    <section aria-labelledby="pending-h" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="pending-h" className="text-sm font-semibold">Waiting for you</h2>
        <span className="text-xs text-muted">{q.data?.length ?? 0} pending</span>
      </div>
      {q.isLoading && <Card><SkeletonLoader /></Card>}
      {!q.isLoading && items.length === 0 && (
        <Card>
          <EmptyState title="No pending approvals" description="The twin will ask here before it acts." />
        </Card>
      )}
      {items.map((s) => (
        <ApprovalCard key={s.id} s={s} twinName={twinName} />
      ))}
    </section>
  );
}

function ActivityFeed({ programId }: { programId: string }) {
  const q = useQuery({
    queryKey: ["activity", programId],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/programs/{program_id}/activity", { params: { path: { program_id: programId }, query: { limit: 15 } } })),
  });
  const openAudit = useUi((s) => s.openAudit);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
      </CardHeader>
      <CardContent>
        {q.isLoading && <SkeletonLoader rows={5} className="p-0" />}
        {q.data?.length === 0 && <EmptyState title="No activity yet" />}
        <ol className="space-y-2.5" data-testid="activity">
          {q.data?.map((a) => (
            <li key={a.id} className="flex items-start gap-2 text-xs">
              {a.actor_type === "twin" ? (
                <Bot className="mt-0.5 size-3.5 shrink-0 text-accent" aria-label="Twin action" />
              ) : a.actor_type === "system" ? (
                <Activity className="mt-0.5 size-3.5 shrink-0 text-muted" aria-label="System" />
              ) : (
                <User className="mt-0.5 size-3.5 shrink-0 text-muted" aria-label="User action" />
              )}
              <button
                type="button"
                className="min-w-0 text-left hover:underline"
                onClick={() => openAudit({ entityId: a.entity_id ?? undefined, suggestionId: a.entity_id ? undefined : a.suggestion_id ?? undefined, title: a.summary })}
              >
                <span className="line-clamp-2">{a.summary}</span>
                <span className="text-muted">{relTime(a.occurred_at)}</span>
              </button>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function TopRisks({ programId }: { programId: string }) {
  const { org } = useParams<{ org: string }>();
  const openEntity = useUi((s) => s.openEntity);
  const q = useQuery({
    queryKey: ["risky", programId, 0.6],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/risk/work-items", { params: { query: { program_id: programId, min_score: 0.6, limit: 6 } } })),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Top at-risk items</CardTitle>
        <Link href={`/${org}/risk`} className="text-xs text-accent hover:underline">
          Risk radar
        </Link>
      </CardHeader>
      <CardContent className="px-2">
        {q.isLoading && <SkeletonLoader />}
        <Table>
          <THead>
            <TR>
              <TH>Item</TH>
              <TH>Owner</TH>
              <TH>Risk</TH>
              <TH>Top driver</TH>
            </TR>
          </THead>
          <TBody>
            {q.data?.map((r) => (
              <TR key={r.work_item_id}>
                <TD>
                  <button type="button" className="text-left hover:underline" onClick={() => openEntity({ type: "work_item", id: r.work_item_id, label: r.key })}>
                    <span className="font-mono text-xs">{r.key}</span>
                    <span className="block max-w-52 truncate text-xs text-muted">{r.title}</span>
                  </button>
                </TD>
                <TD className="text-xs">{r.owner ?? "Unassigned"}</TD>
                <TD>
                  <RiskBadge probability={r.probability} showValue />
                </TD>
                <TD className="max-w-52 text-xs text-muted">{r.drivers[0]?.label}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function AnomalyStrip() {
  const q = useQuery({ queryKey: ["anomalies"], queryFn: async () => unwrap(await api.GET("/api/v1/insights/anomalies")) });
  if (!q.data?.length) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Metric anomalies">
      {q.data.slice(0, 6).map((a) => (
        <Tooltip key={a.id} content={a.explanation}>
          <div className="flex shrink-0 items-center gap-2 rounded-lg border border-warning/40 bg-warning/5 px-3 py-1.5 text-xs">
            <AlertTriangle className="size-3.5 text-warning" aria-hidden />
            <span className="max-w-72 truncate">{a.explanation.split(",")[0]}</span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

export default function CommandCenterPage() {
  const me = useMe();
  const programId = useProgramId();
  const twinName = `${me.data?.user.name.split(" ")[0] ?? "Your"}'s twin`;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Command Center"
        description="TwinPM doesn't just answer questions about your program. It runs it the way you would, and shows its reasoning every time."
      />
      <AnomalyStrip />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="space-y-6">
          <HealthCard programId={programId} />
          <ForecastCard programId={programId} />
        </div>
        <Briefing programId={programId} twinName={twinName} />
      </div>
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2 space-y-6">
          <TopRisks programId={programId} />
          <PendingSuggestions twinName={twinName} />
        </div>
        <ActivityFeed programId={programId} />
      </div>
    </div>
  );
}
