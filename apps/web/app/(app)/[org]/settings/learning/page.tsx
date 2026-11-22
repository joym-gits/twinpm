"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { pct } from "@/lib/format";

const humanize = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export default function LearningPage() {
  const q = useQuery({ queryKey: ["twin-learning"], queryFn: async () => unwrap(await api.GET("/api/v1/twin/learning")) });
  const d = q.data;
  const byType = Object.entries(d?.by_type ?? {}).map(([type, v]) => ({ type: humanize(type), seen: v.seen ?? 0, rate: v.accept_rate ?? 0 }));
  const weights = Object.keys({ ...d?.default_weights, ...d?.learned_weights }).map((k) => {
    const def = d?.default_weights[k] ?? 0;
    const learned = d?.learned_weights[k] ?? def;
    return { k, def, learned, shift: def ? (learned - def) / def : 0 };
  });
  const maxShift = Math.max(0.05, ...weights.map((w) => Math.abs(w.shift)));

  return (
    <SettingsShell title="Twin learning" description="How your responses to suggestions have shaped the twin.">
      {q.isLoading && <SkeletonLoader rows={8} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <dl className="grid gap-3 sm:grid-cols-3">
            <Card className="p-4">
              <dt className="text-xs text-muted">Suggestions seen</dt>
              <dd className="text-2xl font-semibold tabular-nums">{d.suggestions_seen}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-xs text-muted">Acceptance rate</dt>
              <dd className="text-2xl font-semibold tabular-nums">{d.acceptance_rate != null ? pct(d.acceptance_rate) : "—"}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-xs text-muted">Style examples</dt>
              <dd className="text-2xl font-semibold tabular-nums">{d.style_examples}</dd>
            </Card>
          </dl>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Acceptance by suggestion type</CardTitle>
                <CardDescription>Share of suggestions you accepted or accepted with edits.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {byType.length === 0 ? (
                <EmptyState title="No responses yet" description="Accept, edit or reject a few suggestions and the twin will start learning." />
              ) : (
                <>
                  <div style={{ height: Math.max(120, byType.length * 40) }} role="img" aria-label="Acceptance rate by suggestion type, listed in the table below">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={byType} layout="vertical" margin={{ left: 24, right: 24 }}>
                        <CartesianGrid stroke="var(--border)" horizontal={false} />
                        <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => pct(Number(v))} fontSize={11} stroke="var(--muted)" />
                        <YAxis type="category" dataKey="type" width={120} fontSize={11} stroke="var(--muted)" />
                        <Tooltip
                          contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--text)" }}
                          formatter={(v, _n, item) => [`${pct(Number(v))} of ${(item.payload as { seen: number }).seen}`, "Accepted"]}
                        />
                        <Bar dataKey="rate" fill="var(--accent)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <table className="sr-only">
                    <caption>Acceptance by type</caption>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Seen</th>
                        <th>Accepted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byType.map((r) => (
                        <tr key={r.type}>
                          <td>{r.type}</td>
                          <td>{r.seen}</td>
                          <td>{pct(r.rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Delegation weight shifts</CardTitle>
                <CardDescription>How the twin now weighs each factor when picking an assignee, compared with the defaults.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {weights.length === 0 ? (
                <EmptyState title="No weights yet" />
              ) : (
                <ul className="space-y-3" aria-label="Weight shifts">
                  {weights.map((w) => {
                    const width = `${(Math.abs(w.shift) / maxShift) * 50}%`;
                    return (
                      <li key={w.k} className="grid items-center gap-3 text-xs sm:grid-cols-[160px_1fr_150px]">
                        <span className="font-medium">{humanize(w.k)}</span>
                        <div className="relative h-3 rounded-full bg-surface-2" aria-hidden>
                          <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
                          <div
                            className={`absolute inset-y-0 rounded-full ${w.shift >= 0 ? "bg-accent" : "bg-warning"}`}
                            style={w.shift >= 0 ? { left: "50%", width } : { right: "50%", width }}
                          />
                        </div>
                        <span className="tabular-nums">
                          <strong>
                            {w.shift >= 0 ? "+" : "−"}
                            {pct(Math.abs(w.shift))}
                          </strong>{" "}
                          <span className="text-muted">
                            ({w.def.toFixed(2)} → {w.learned.toFixed(2)})
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </SettingsShell>
  );
}
