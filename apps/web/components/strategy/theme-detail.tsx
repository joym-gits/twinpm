"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { opportunity, signed, sentimentWord, type Theme } from "@/components/strategy/theme-charts";

const monthLabel = (key: string) =>
  new Date(`${key}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" });

function Trend({ themeId }: { themeId: string }) {
  const q = useQuery({
    queryKey: ["feedback", themeId],
    queryFn: async () => unwrap(await api.GET("/api/v1/feedback", { params: { query: { theme_id: themeId, limit: 500 } } })),
  });
  if (q.isLoading) return <Skeleton className="h-32" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const byMonth = new Map<string, number>();
  for (const f of q.data ?? []) {
    const k = f.received_at.slice(0, 7);
    byMonth.set(k, (byMonth.get(k) ?? 0) + 1);
  }
  const data = [...byMonth.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([month, count]) => ({ month, count }));
  if (!data.length) return <EmptyState title="No feedback items in this theme" />;
  return (
    <figure>
      <div className="h-32" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <XAxis dataKey="month" tickFormatter={(m) => monthLabel(String(m))} fontSize={10} />
            <YAxis allowDecimals={false} fontSize={10} width={28} />
            <RTooltip labelFormatter={(m) => monthLabel(String(m))} formatter={(v) => [String(v), "Items"]} />
            <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">
        Feedback per month: {data.map((d) => `${monthLabel(d.month)} ${d.count}`).join(", ")}
      </figcaption>
    </figure>
  );
}

function LinkedObjectives({ programId, theme }: { programId: string; theme: Theme }) {
  const q = useQuery({
    queryKey: ["roadmap", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/roadmap", { params: { query: { program_id: programId } } })),
  });
  if (q.isLoading) return <Skeleton className="h-12" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const initiatives = Object.values(q.data?.buckets ?? {}).flat();
  const words = theme.keywords.map((k) => k.toLowerCase().replace(/-/g, " ")).filter((k) => k.length > 2);
  // ponytail: keyword overlap is a naive link; swap for a theme→initiative relation if the API grows one.
  const matched = initiatives.filter((i) => words.some((w) => `${i.title} ${i.description}`.toLowerCase().includes(w)));
  if (matched.length) {
    return (
      <ul className="space-y-1.5 text-sm">
        {matched.slice(0, 4).map((i) => (
          <li key={i.id}>
            <span className="font-medium">{i.title}</span>
            <span className="text-muted"> → {i.objective ?? "No objective linked"}</span>
          </li>
        ))}
      </ul>
    );
  }
  const objectives = [...new Set(initiatives.map((i) => i.objective).filter((o): o is string => !!o))];
  if (!objectives.length) return <p className="text-sm text-muted">No program objectives on the roadmap yet.</p>;
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted">No initiative mentions this theme yet. Program objectives:</p>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {objectives.map((o) => (
          <li key={o}>{o}</li>
        ))}
      </ul>
    </div>
  );
}

export function ThemeDetail({ theme, programId }: { theme: Theme; programId: string }) {
  const o = opportunity(theme);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{theme.label}</CardTitle>
          <CardDescription>{theme.summary}</CardDescription>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold tabular-nums">{o.score.toFixed(1)}</p>
          <p className="text-[11px] text-muted">opportunity score{o.method ? ` · ${o.method}` : ""}</p>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={theme.avg_sentiment < -0.25 ? "danger" : theme.avg_sentiment > 0.25 ? "success" : "neutral"}>
            Sentiment {signed(theme.avg_sentiment)} ({sentimentWord(theme.avg_sentiment)})
          </Badge>
          <Badge>{theme.size} items</Badge>
          {theme.keywords.map((k) => (
            <Badge key={k} tone="accent">
              {k}
            </Badge>
          ))}
        </div>
        <section aria-labelledby="quotes-h" className="space-y-2">
          <h3 id="quotes-h" className="text-xs font-semibold uppercase tracking-wide text-muted">Representative quotes</h3>
          {o.quotes.length === 0 && <p className="text-sm text-muted">No quotes recorded for this theme.</p>}
          {o.quotes.map((q) => (
            <blockquote key={q} className="border-l-2 border-accent pl-3 text-sm italic">
              {q}
            </blockquote>
          ))}
        </section>
        <section aria-labelledby="trend-h" className="space-y-2">
          <h3 id="trend-h" className="text-xs font-semibold uppercase tracking-wide text-muted">Trend by month</h3>
          <Trend themeId={theme.id} />
        </section>
        <section aria-labelledby="obj-h" className="space-y-2">
          <h3 id="obj-h" className="text-xs font-semibold uppercase tracking-wide text-muted">Linked objectives</h3>
          <LinkedObjectives programId={programId} theme={theme} />
        </section>
      </CardContent>
    </Card>
  );
}
