"use client";

import { AlertTriangle } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/states";
import { type Schemas } from "@/lib/api/client";
import { pct, shortDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Workload = Schemas["WorkloadOut"];
type Person = Schemas["PersonLoad"];
/** PersonLoad.weeks is untyped; shape from services/delegation.py. */
type Week = { week: string; utilisation: number };

/** Sequential scale: surface → accent, saturating at 150% utilisation. */
function cellStyle(u: number) {
  const mix = Math.round(Math.min(u / 1.5, 1) * 85);
  return {
    background: `color-mix(in oklab, var(--accent) ${mix}%, var(--surface))`,
    color: mix > 45 ? "var(--accent-fg)" : "var(--text)",
  };
}

export function WorkloadHeatmap({ data }: { data: Workload }) {
  const t = data.overload_threshold;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Workload</CardTitle>
          <CardDescription>
            Utilisation per person per week. Cells outlined with <AlertTriangle className="inline size-3" aria-hidden /> exceed {pct(t)}.
          </CardDescription>
        </div>
        <div className="flex items-center gap-1 text-[11px] text-muted" aria-hidden>
          0%
          {[0, 0.375, 0.75, 1.125, 1.5].map((u) => (
            <span key={u} className="size-3 rounded-sm border border-border" style={cellStyle(u)} />
          ))}
          150%+
        </div>
      </CardHeader>
      <CardContent className="px-2">
        {data.people.length === 0 ? (
          <EmptyState title="No people in this program" description="Add team members or sync from your tracker to see workload." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-1 text-xs" data-testid="heatmap">
              <caption className="sr-only">Weekly utilisation by person. Overload threshold {pct(t)}.</caption>
              <thead>
                <tr>
                  <th scope="col" className="px-2 text-left font-medium text-muted">Person</th>
                  {data.weeks.map((w) => (
                    <th key={w} scope="col" className="px-1 text-center font-medium text-muted">
                      {shortDate(w)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.people.map((p) => {
                  const byWeek = new Map((p.weeks as unknown as Week[]).map((w) => [w.week, w.utilisation]));
                  return (
                    <tr key={p.person_id}>
                      <th scope="row" className="whitespace-nowrap px-2 text-left font-medium">
                        {p.name}
                        <span className="block font-normal text-muted">{p.team ?? "No team"}</span>
                      </th>
                      {data.weeks.map((w) => {
                        const u = byWeek.get(w);
                        if (u === undefined)
                          return (
                            <td key={w} className="rounded-md border border-border text-center text-muted">
                              —
                            </td>
                          );
                        const over = u > t;
                        return (
                          <td
                            key={w}
                            className={cn(
                              "h-9 min-w-14 rounded-md border text-center tabular-nums",
                              over ? "border-2 border-danger font-semibold" : "border-transparent",
                            )}
                            style={cellStyle(u)}
                          >
                            <span className="inline-flex items-center gap-0.5">
                              {over && <AlertTriangle className="size-3" aria-hidden />}
                              {pct(u)}
                              {over && <span className="sr-only"> overloaded</span>}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Ring({ value, over }: { value: number; over: boolean }) {
  const r = 20;
  const c = 2 * Math.PI * r;
  const frac = Math.min(value, 1);
  return (
    <svg viewBox="0 0 48 48" className="size-14 shrink-0" role="img" aria-label={`Utilisation ${pct(value)}${over ? ", overloaded" : ""}`}>
      <circle cx="24" cy="24" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="5" />
      <circle
        cx="24"
        cy="24"
        r={r}
        fill="none"
        stroke={over ? "var(--color-danger)" : "var(--accent)"}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={`${frac * c} ${c}`}
        transform="rotate(-90 24 24)"
      />
      <text x="24" y="27" textAnchor="middle" fontSize="10" fontWeight="600" fill="var(--text)">
        {Math.round(value * 100)}%
      </text>
    </svg>
  );
}

function PersonCard({ p }: { p: Person }) {
  const skills = Object.entries(p.skills)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  return (
    <Card className={cn("space-y-2 p-3", p.overloaded && "border-danger/60")}>
      <div className="flex items-center gap-3">
        <Ring value={p.utilisation} over={p.overloaded} />
        <div className="min-w-0">
          <h4 className="truncate text-sm font-medium">{p.name}</h4>
          <p className="truncate text-xs text-muted">{p.title}</p>
          <p className="text-xs tabular-nums text-muted">
            {p.assigned_points} / {p.capacity_points} pts
          </p>
          {p.overloaded && (
            <Badge tone="danger" className="mt-1">
              <AlertTriangle className="size-3" aria-hidden /> Overloaded
            </Badge>
          )}
        </div>
      </div>
      {skills.length > 0 && (
        <ul className="space-y-0.5 text-xs" aria-label="Top skills">
          {skills.map(([name, level]) => (
            <li key={name} className="flex items-center justify-between gap-2">
              <span className="truncate">{name}</span>
              <span className="flex items-center gap-0.5" aria-label={`level ${level} of 5`}>
                {[1, 2, 3, 4, 5].map((i) => (
                  <span key={i} className={cn("size-1.5 rounded-full", i <= level ? "bg-accent" : "bg-surface-2 ring-1 ring-border")} aria-hidden />
                ))}
                <span className="ml-1 tabular-nums text-muted" aria-hidden>
                  {level}/5
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {p.growth_goals.length > 0 && (
        <div className="flex flex-wrap gap-1" aria-label="Growth goals">
          <span className="sr-only">Growth goals:</span>
          {p.growth_goals.map((g) => (
            <Badge key={g} tone="accent">
              ↗ {g}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

export function TeamColumns({ data }: { data: Workload }) {
  const teams = new Map<string, Person[]>();
  for (const p of data.people) {
    const k = p.team ?? "No team";
    teams.set(k, [...(teams.get(k) ?? []), p]);
  }
  if (teams.size === 0) return null;
  return (
    <section aria-labelledby="teams-h" className="space-y-3">
      <h2 id="teams-h" className="text-sm font-semibold">Teams</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[...teams.entries()].map(([team, people]) => (
          <div key={team} className="space-y-3 rounded-xl bg-surface-2/60 p-3">
            <h3 className="text-sm font-semibold">
              {team} <span className="font-normal text-muted">({people.length})</span>
            </h3>
            {people.map((p) => (
              <PersonCard key={p.person_id} p={p} />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function DistributionMonitor({ data }: { data: Workload }) {
  const rows = Object.entries(data.assignment_counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Distribution monitor</CardTitle>
          <CardDescription>Assignments in the last 90 days. Watch for work concentrating on a few people.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <EmptyState title="No assignments in the last 90 days" />
        ) : (
          <>
            <div style={{ height: Math.max(120, rows.length * 26) }} aria-hidden>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <XAxis type="number" allowDecimals={false} fontSize={10} stroke="var(--muted)" />
                  <YAxis type="category" dataKey="name" width={110} fontSize={11} stroke="var(--muted)" />
                  <RTooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
                  <Bar dataKey="count" name="Assignments" fill="var(--accent)" radius={[0, 3, 3, 0]} label={{ position: "right", fontSize: 10, fill: "var(--text)" }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <ul className="sr-only">
              {rows.map((r) => (
                <li key={r.name}>
                  {r.name}: {r.count} assignments
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
