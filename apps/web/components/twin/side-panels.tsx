"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { ErrorState, SkeletonLoader } from "@/components/ui/states";
import { DriverList, type DriverLike } from "@/components/twin/driver-list";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, unwrap } from "@/lib/api/client";
import { relTime } from "@/lib/format";
import { useUi } from "@/lib/store";

const SKIP = new Set(["drivers", "delay_probability", "body", "description", "created_at", "updated_at"]);

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Opens when a CitationChip is clicked: shows the source entity. */
export function EntityPanel() {
  const entity = useUi((s) => s.entity);
  const close = useUi((s) => s.openEntity);
  const { org } = useParams<{ org: string }>();
  const q = useQuery({
    queryKey: ["entity", entity?.type, entity?.id],
    enabled: !!entity && entity.type !== "metric",
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/entities/{entity_type}/{entity_id}", {
          params: { path: { entity_type: entity!.type, entity_id: entity!.id } },
        }),
      ),
  });
  const f = (q.data?.fields ?? {}) as Record<string, unknown>;
  const body = (f.body ?? f.description ?? f.rationale ?? f.text) as string | undefined;
  return (
    <Sheet open={!!entity} onOpenChange={(o) => !o && close(null)}>
      <SheetContent title={q.data?.title ?? entity?.label ?? "Source"} description={entity?.type.replace("_", " ")}>
        {q.isLoading && <SkeletonLoader rows={6} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data && (
          <div className="space-y-4 p-5">
            {typeof f.delay_probability === "number" && (
              <div className="space-y-2">
                <RiskBadge probability={f.delay_probability} />
                <DriverList drivers={(f.drivers as DriverLike[]) ?? []} />
              </div>
            )}
            {body && <div className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm">{String(body)}</div>}
            <dl className="grid grid-cols-[minmax(0,10rem)_1fr] gap-x-3 gap-y-1.5 text-xs">
              {Object.entries(f)
                .filter(([k]) => !SKIP.has(k) && k !== "rationale" && k !== "text")
                .map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
                    <dd className="break-words">{fmt(v)}</dd>
                  </div>
                ))}
            </dl>
            {q.data.link && (
              <Link className="text-sm text-accent underline-offset-4 hover:underline" href={`/${org}/${q.data.link}`} onClick={() => close(null)}>
                Open in {q.data.link.replace("-", " ")}
              </Link>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** Audit trail for an entity or a suggestion. Reachable from every suggestion and entity. */
export function AuditDrawer() {
  const audit = useUi((s) => s.audit);
  const close = useUi((s) => s.openAudit);
  const q = useQuery({
    queryKey: ["audit", audit],
    enabled: !!audit,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/audit", {
          params: {
            query: {
              entity_id: audit?.entityId ?? null,
              entity_type: audit?.entityType ?? null,
              suggestion_id: audit?.suggestionId ?? null,
              limit: 100,
            },
          },
        }),
      ),
  });
  return (
    <Sheet open={!!audit} onOpenChange={(o) => !o && close(null)}>
      <SheetContent title="Audit log" description={audit?.title}>
        {q.isLoading && <SkeletonLoader rows={6} />}
        {q.isError && <ErrorState error={q.error} />}
        <ol className="space-y-3 p-5" aria-label="Audit entries">
          {q.data?.length === 0 && <li className="text-sm text-muted">No entries yet.</li>}
          {q.data?.map((e) => (
            <li key={e.id} className="rounded-lg border border-border p-3 text-xs" data-testid="audit-entry">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{e.action}</span>
                <Badge tone={e.actor_type === "twin" ? "accent" : "neutral"}>{e.actor_type}</Badge>
              </div>
              <p className="mt-1 text-muted">
                {e.entity_type} · {relTime(e.occurred_at)}
              </p>
              {e.reason && <p className="mt-1">Reason: {e.reason}</p>}
              {(e.before || e.after) && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <pre className="overflow-x-auto rounded bg-surface-2 p-2">{JSON.stringify(e.before ?? {}, null, 1)}</pre>
                  <pre className="overflow-x-auto rounded bg-surface-2 p-2">{JSON.stringify(e.after ?? {}, null, 1)}</pre>
                </div>
              )}
            </li>
          ))}
        </ol>
      </SheetContent>
    </Sheet>
  );
}
