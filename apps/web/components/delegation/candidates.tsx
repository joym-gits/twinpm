"use client";

import { useQuery } from "@tanstack/react-query";
import { UserSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pct } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const FACTORS: { key: string; label: string; penalty?: boolean }[] = [
  { key: "skill_match", label: "Skill match" },
  { key: "availability", label: "Availability" },
  { key: "throughput_similar", label: "Throughput on similar work" },
  { key: "growth_alignment", label: "Growth alignment" },
  { key: "context_continuity", label: "Context continuity" },
  { key: "over_allocation", label: "Over-allocation", penalty: true },
  { key: "pto_overlap", label: "PTO overlap", penalty: true },
];

function FactorBars({ factors }: { factors: Record<string, number> }) {
  return (
    <dl className="grid gap-x-4 gap-y-1 text-[11px] sm:grid-cols-2">
      {FACTORS.filter((f) => f.key in factors).map((f) => {
        const v = Math.max(0, Math.min(1, factors[f.key] ?? 0));
        return (
          <div key={f.key} className="grid grid-cols-[minmax(0,9rem)_1fr_2.5rem] items-center gap-2">
            <dt className="truncate text-muted">
              {f.label}
              {f.penalty && <span> (penalty)</span>}
            </dt>
            <dd className="h-1.5 rounded-full bg-surface-2" aria-hidden>
              <div className={cn("h-full rounded-full", f.penalty ? "bg-danger" : "bg-accent")} style={{ width: `${v * 100}%` }} />
            </dd>
            <dd className="text-right tabular-nums">{pct(v)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function CandidatesPanel({ item }: { item: Schemas["RiskyItem"] }) {
  const q = useQuery({
    queryKey: ["candidates", item.work_item_id],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/delegation/candidates/{work_item_id}", { params: { path: { work_item_id: item.work_item_id } } })),
  });
  return (
    <div className="space-y-3" aria-live="polite">
      <div>
        <h3 className="text-sm font-semibold">
          Best owners for <span className="font-mono">{item.key}</span>
        </h3>
        <p className="text-xs text-muted">{item.title}</p>
      </div>
      {q.isLoading && <SkeletonLoader rows={4} className="p-0" />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && (
        <>
          {Object.keys(q.data.required_skills).length > 0 && (
            <div className="flex flex-wrap items-center gap-1 text-xs">
              <span className="text-muted">Needs:</span>
              {Object.entries(q.data.required_skills).map(([s, l]) => (
                <Badge key={s} tone="neutral">
                  {s} {l}/5
                </Badge>
              ))}
            </div>
          )}
          {q.data.candidates.length === 0 && <EmptyState title="No suitable candidates" description="Nobody in the program has the skills and capacity for this item." />}
          <ol className="space-y-3">
            {q.data.candidates.map((c, i) => (
              <li key={c.person_id}>
                <Card className="space-y-2 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">
                      <span className="mr-1 text-muted">#{i + 1}</span>
                      {c.name}
                    </p>
                    <div className="flex items-center gap-1.5">
                      <Badge tone="neutral">Util {pct(c.utilisation)}</Badge>
                      <Badge tone="accent">Score {c.score.toFixed(2)}</Badge>
                    </div>
                  </div>
                  <FactorBars factors={c.factors} />
                  <p className="text-xs text-muted">{c.explanation}</p>
                </Card>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

export function AtRiskItems({ programId }: { programId: string }) {
  const setPageContext = useUi((s) => s.setPageContext);
  const [selected, setSelected] = useState<Schemas["RiskyItem"] | null>(null);
  const q = useQuery({
    queryKey: ["risky", programId, 0.5],
    queryFn: async () => unwrap(await api.GET("/api/v1/risk/work-items", { params: { query: { program_id: programId, min_score: 0.5 } } })),
  });
  useEffect(() => {
    setPageContext(
      selected
        ? { screen: "delegation", selected_work_item: { id: selected.work_item_id, key: selected.key, title: selected.title } }
        : { screen: "delegation" },
    );
  }, [selected, setPageContext]);
  useEffect(() => () => setPageContext({}), [setPageContext]);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>At-risk and unassigned items</CardTitle>
          <CardDescription>Select an item to see who the twin would assign and why.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div>
          {q.isLoading && <SkeletonLoader rows={5} className="p-0" />}
          {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
          {q.data?.length === 0 && <EmptyState title="No at-risk items" description="Nothing is above 50% delay probability right now." />}
          <ul className="space-y-1.5">
            {q.data?.map((r) => {
              const on = selected?.work_item_id === r.work_item_id;
              return (
                <li key={r.work_item_id}>
                  <button
                    type="button"
                    aria-pressed={on}
                    onClick={() => setSelected(on ? null : r)}
                    className={cn(
                      "w-full rounded-lg border px-3 py-2 text-left hover:bg-surface-2",
                      on ? "border-accent bg-accent/5" : "border-border",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{r.key}</span>
                      <RiskBadge probability={r.probability} />
                    </div>
                    <span className="block truncate text-xs">{r.title}</span>
                    <span className="text-[11px] text-muted">
                      {r.owner ? `Owner: ${r.owner}` : "Unassigned"} · {r.status.replace(/_/g, " ")}
                      {r.drivers[0] && <> · {r.drivers[0].label}</>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
        <div>
          {selected ? (
            <CandidatesPanel key={selected.work_item_id} item={selected} />
          ) : (
            <EmptyState icon={UserSearch} title="No item selected" description="Pick an item on the left to see ranked candidates with factor breakdowns." />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
