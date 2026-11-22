"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Scale } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Markdown } from "@/components/twin/markdown";
import { RiskBadge } from "@/components/twin/risk-badge";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import { AcceptAll, useSuggestionsById } from "@/components/roadmap/suggestion-list";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { shortDate } from "@/lib/format";
import { useSuggestions } from "@/lib/hooks/use-suggestions";

function Plan({ plan }: { plan: Schemas["RebalanceOut"] }) {
  const ids = plan.moves.flatMap((m) => (m.suggestion_id ? [m.suggestion_id] : []));
  const qs = useSuggestionsById(ids);
  const loaded = qs.flatMap((q) => (q.data ? [q.data] : []));
  const later = plan.delta_days > 0;
  return (
    <div className="space-y-4" data-testid="rebalance-plan">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted">P80 impact</p>
          <p className={`text-4xl font-semibold tabular-nums ${later ? "text-danger" : plan.delta_days < 0 ? "text-success" : ""}`}>
            {plan.delta_days > 0 ? "+" : ""}
            {plan.delta_days}d
          </p>
          <p className="text-xs text-muted">{plan.delta_days === 0 ? "No change" : later ? "later" : "earlier"} if all moves are approved</p>
        </div>
        <div>
          <p className="text-xs text-muted">Baseline P80</p>
          <p className="text-xl font-semibold tabular-nums">{shortDate(plan.baseline_p80)}</p>
        </div>
        <div>
          <p className="text-xs text-muted">Rebalanced P80</p>
          <p className="text-xl font-semibold tabular-nums">{shortDate(plan.scenario_p80)}</p>
        </div>
      </div>
      <div className="rounded-lg bg-surface-2 p-3">
        <Markdown text={plan.narrative} />
      </div>
      {plan.moves.length === 0 ? (
        <EmptyState title="No moves needed" description="Workload is already balanced against the forecast." />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Proposed moves ({plan.moves.length})</h3>
            <AcceptAll items={loaded} label="Approve all" />
          </div>
          <ol className="space-y-3">
            {plan.moves.map((m) => {
              const s = qs[ids.indexOf(m.suggestion_id ?? "")]?.data;
              return (
                <li key={m.work_item_id} className="space-y-2 rounded-xl border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-mono text-xs">{m.key}</span>
                    <span className="min-w-0 flex-1 truncate">{m.title}</span>
                    <Badge tone="neutral">{m.points} pts</Badge>
                    <RiskBadge probability={m.risk} />
                  </div>
                  <p className="flex items-center gap-2 text-sm">
                    <span>{m.from_name ?? "Unassigned"}</span>
                    <ArrowRight className="size-4 text-muted" aria-label="to" />
                    <strong>{m.to_name}</strong>
                  </p>
                  <p className="text-xs text-muted">{m.explanation}</p>
                  {s && <SuggestionCard s={s} compact />}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}

/**
 * Rebalancing creates new suggestions on every call, so: run at most once per visit, and if pending
 * reassign suggestions already exist, show those instead and let the user explicitly re-plan.
 */
export function RebalancePanel({ programId }: { programId: string }) {
  const params = useSearchParams();
  const auto = params.get("rebalance") === "1";
  const existing = useSuggestions({ status: "pending", type: "reassign" });
  const ran = useRef(false);
  const ref = useRef<HTMLElement>(null);
  const run = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/delegation/rebalance", { body: { program_id: programId } })),
  });
  const pending = existing.data ?? [];

  useEffect(() => {
    if (!auto || ran.current || !existing.isSuccess) return;
    ran.current = true;
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (existing.data.length === 0) run.mutate();
  }, [auto, existing.isSuccess, existing.data, run]);

  const start = () => {
    ran.current = true;
    run.mutate();
  };

  return (
    <section ref={ref} aria-labelledby="rebalance-h" className="scroll-mt-6">
      <Card>
        <CardHeader>
          <div>
            <CardTitle id="rebalance-h">Rebalance</CardTitle>
            <CardDescription>The twin proposes reassignments to relieve overload, with the forecast impact. Each move needs your approval.</CardDescription>
          </div>
          <Button variant="accent" disabled={run.isPending || existing.isLoading} onClick={start}>
            <Scale /> {run.isPending ? "Planning…" : run.data || pending.length ? "Re-plan" : "Rebalance"}
          </Button>
        </CardHeader>
        <CardContent aria-live="polite">
          {(run.isPending || existing.isLoading) && <SkeletonLoader rows={5} className="p-0" />}
          {run.isError && <ErrorState error={run.error} onRetry={start} />}
          {!run.isPending && run.data && <Plan plan={run.data} />}
          {!run.isPending && !run.data && existing.isError && <ErrorState error={existing.error} onRetry={() => void existing.refetch()} />}
          {!run.isPending && !run.data && pending.length > 0 && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm">
                  {pending.length} reassignment{pending.length === 1 ? "" : "s"} from an earlier plan still need a decision.
                </p>
                <AcceptAll items={pending} label="Approve all" />
              </div>
              {pending.map((s) => (
                <SuggestionCard key={s.id} s={s} compact />
              ))}
            </div>
          )}
          {!run.isPending && !run.data && !run.isError && existing.isSuccess && pending.length === 0 && (
            <EmptyState icon={Scale} title="No rebalance plan yet" description="Run a rebalance to see suggested moves and how they shift the P80 date." action={{ label: "Rebalance", onClick: start }} />
          )}
        </CardContent>
      </Card>
    </section>
  );
}
