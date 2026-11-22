"use client";

import { useQuery } from "@tanstack/react-query";
import { EyeOff, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pct, shortDate } from "@/lib/format";

function TeamCard({ t }: { t: Schemas["TeamHealthOut"] }) {
  if (t.suppressed)
    return (
      <li className="rounded-lg border border-dashed border-border p-4">
        <p className="font-medium">{t.team}</p>
        <p className="mt-2 flex items-center gap-1.5 text-sm text-muted">
          <EyeOff className="size-4" aria-hidden /> Hidden for privacy
        </p>
        <p className="mt-1 text-xs text-muted">Fewer than 5 people, so no signals are shown.</p>
      </li>
    );
  const trend = t.sentiment_trend ?? 0;
  const series = t.series as { date: string; sentiment: number; after_hours: number }[];
  const Arrow = trend >= 0 ? TrendingUp : TrendingDown;
  return (
    <li className="rounded-lg border border-border p-4">
      <div className="flex items-baseline justify-between">
        <p className="font-medium">{t.team}</p>
        <span className="text-xs text-muted">{t.size} people</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-muted">Sentiment index</dt>
          <dd className="flex items-center gap-1 font-semibold tabular-nums">
            {t.sentiment_index?.toFixed(2) ?? "—"}
            <span className={trend < 0 ? "text-danger" : "text-success"}>
              <Arrow className="inline size-3.5" aria-hidden />
              {trend >= 0 ? "+" : ""}
              {trend.toFixed(2)}
              <span className="sr-only">{trend < 0 ? " down" : " up"} vs the prior 4 weeks</span>
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-muted">After-hours messages</dt>
          <dd className="font-semibold tabular-nums">{t.after_hours_ratio != null ? pct(t.after_hours_ratio) : "—"}</dd>
        </div>
        <div>
          <dt className="text-muted">Messages / day</dt>
          <dd className="font-semibold tabular-nums">{t.message_volume ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted">Mean utilisation</dt>
          <dd className="font-semibold tabular-nums">{t.utilisation_mean != null ? pct(t.utilisation_mean) : "—"}</dd>
        </div>
      </dl>
      {series.length > 1 && (
        <div className="mt-3 h-14" role="img" aria-label={`${t.team} sentiment over the last ${series.length} days`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series}>
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--text)" }}
                labelFormatter={(_l, p) => shortDate(String(p?.[0]?.payload?.date ?? ""))}
                formatter={(v) => [Number(v).toFixed(2), "Sentiment"]}
              />
              <Line dataKey="sentiment" stroke="var(--accent)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </li>
  );
}

export function TeamHealthPanel({ programId }: { programId: string }) {
  const q = useQuery({
    queryKey: ["team-health", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/insights/team-health", { params: { query: { program_id: programId } } })),
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Team health</CardTitle>
          <CardDescription>Last 7 days compared with the 4 weeks before.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2 rounded-lg border border-accent/30 bg-accent/5 p-3 text-xs" role="note">
          <ShieldCheck className="size-4 shrink-0 text-accent" aria-hidden />
          <p>
            <strong>Privacy:</strong> these are team-level aggregates only, never individuals. Teams with fewer than 5 people are suppressed so no one can be
            singled out.
          </p>
        </div>
        {q.isLoading && <Skeleton className="h-40" />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && <EmptyState title="No teams yet" />}
        <ul className="grid gap-3 md:grid-cols-2" data-testid="team-health">
          {q.data?.map((t) => <TeamCard key={t.team_id} t={t} />)}
        </ul>
      </CardContent>
    </Card>
  );
}
