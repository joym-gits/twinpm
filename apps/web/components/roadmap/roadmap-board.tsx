"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, GitBranch, GripVertical, History, Map as MapIcon } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from "@/components/ui/menu";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { Tooltip } from "@/components/ui/tooltip";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

type Initiative = Schemas["InitiativeCard"];
type Bucket = Initiative["roadmap_bucket"];
type Roadmap = Schemas["RoadmapOut"];
/** InitiativeCard.epics is untyped in the contract; this is the shape services/planning.py emits. */
type EpicSummary = { id: string; title: string; status: string; open_items: number };

const BUCKETS: { id: Bucket; label: string; hint: string }[] = [
  { id: "now", label: "Now", hint: "In flight this quarter" },
  { id: "next", label: "Next", hint: "Up after current work" },
  { id: "later", label: "Later", hint: "On the horizon" },
];
const DRAG_TYPE = "application/x-twinpm-initiative";

function moveError(e: unknown): string {
  if (e instanceof ApiError && e.status === 403)
    return "Your role can view the roadmap but not change it. Ask a program admin for write access.";
  return e instanceof Error ? e.message : "Couldn't move the initiative.";
}

function ScoreBadge({ name, data }: { name: string; data: Record<string, number> }) {
  const parts = Object.entries(data).filter(([k]) => k !== "score");
  return (
    <Tooltip content={parts.length ? parts.map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ") : name}>
      <button type="button" className="rounded-md focus-visible:outline-2" aria-label={`${name} score ${data.score ?? "not set"}`}>
        <Badge tone="accent">
          {name} <strong className="tabular-nums">{data.score !== undefined ? Math.round(data.score * 10) / 10 : "—"}</strong>
        </Badge>
      </button>
    </Tooltip>
  );
}

function InitiativeTile({
  card,
  onMove,
  disabled,
}: {
  card: Initiative;
  onMove: (card: Initiative, to: Bucket) => void;
  disabled: boolean;
}) {
  const openAudit = useUi((s) => s.openAudit);
  const epics = card.epics as unknown as EpicSummary[];
  return (
    <Card
      draggable={!disabled}
      onDragStart={(e) => {
        e.dataTransfer.setData(DRAG_TYPE, card.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className="cursor-grab p-3 active:cursor-grabbing"
      data-testid="initiative-card"
    >
      <div className="flex items-start gap-2">
        <GripVertical className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h4 className="text-sm font-medium leading-snug">{card.title}</h4>
            <div className="flex shrink-0 items-center">
              <Menu>
                <MenuTrigger asChild>
                  <Button size="icon" variant="ghost" className="size-7" disabled={disabled} aria-label={`Move ${card.title} to another bucket`}>
                    <ArrowRightLeft />
                  </Button>
                </MenuTrigger>
                <MenuContent>
                  <MenuLabel>Move to…</MenuLabel>
                  {BUCKETS.filter((b) => b.id !== card.roadmap_bucket).map((b) => (
                    <MenuItem key={b.id} onSelect={() => onMove(card, b.id)}>
                      {b.label}
                    </MenuItem>
                  ))}
                </MenuContent>
              </Menu>
              <Button
                size="icon"
                variant="ghost"
                className="size-7"
                aria-label={`Open audit log for ${card.title}`}
                onClick={() => openAudit({ entityId: card.id, title: card.title })}
              >
                <History />
              </Button>
            </div>
          </div>
          {card.objective && <p className="text-xs text-muted">Objective: {card.objective}</p>}
          <div className="flex flex-wrap items-center gap-1.5">
            <ScoreBadge name="RICE" data={card.rice} />
            <ScoreBadge name="WSJF" data={card.wsjf} />
            <RiskBadge probability={card.risk} />
            <Badge tone="neutral" aria-label={`${card.dependency_count} dependencies`}>
              <GitBranch className="size-3" aria-hidden /> {card.dependency_count}
            </Badge>
          </div>
          {epics.length > 0 && (
            <ul className="space-y-0.5 border-t border-border pt-2 text-xs" aria-label="Epics">
              {epics.map((e) => (
                <li key={e.id} className="flex justify-between gap-2">
                  <span className="truncate">{e.title}</span>
                  <span className="shrink-0 text-muted tabular-nums">
                    {e.open_items} open · {e.status.replace(/_/g, " ")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

export function RoadmapBoard({ programId }: { programId: string }) {
  const qc = useQueryClient();
  const key = ["roadmap", programId];
  const [over, setOver] = useState<Bucket | null>(null);
  const [notice, setNotice] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const q = useQuery({
    queryKey: key,
    queryFn: async () => unwrap(await api.GET("/api/v1/roadmap", { params: { query: { program_id: programId } } })),
  });
  const move = useMutation({
    mutationFn: async ({ card, to }: { card: Initiative; to: Bucket }) =>
      unwrap(
        await api.PATCH("/api/v1/initiatives/{initiative_id}", {
          params: { path: { initiative_id: card.id } },
          body: { roadmap_bucket: to },
        }),
      ),
    onMutate: async ({ card, to }) => {
      setNotice(null);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Roadmap>(key);
      if (prev) {
        const buckets = Object.fromEntries(
          Object.entries(prev.buckets).map(([b, cards]) => [b, cards.filter((c) => c.id !== card.id)]),
        );
        buckets[to] = [...(buckets[to] ?? []), { ...card, roadmap_bucket: to }];
        qc.setQueryData<Roadmap>(key, { ...prev, buckets });
      }
      return { prev };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      setNotice({ tone: "error", text: moveError(e) });
    },
    onSuccess: (_d, { card, to }) =>
      setNotice({ tone: "ok", text: `Moved “${card.title}” to ${BUCKETS.find((b) => b.id === to)?.label}. The change is in the audit log.` }),
    onSettled: () => void qc.invalidateQueries({ queryKey: key }),
  });
  const onMove = (card: Initiative, to: Bucket) => {
    if (card.roadmap_bucket !== to) move.mutate({ card, to });
  };
  const all = q.data ? Object.values(q.data.buckets).flat() : [];

  return (
    <section aria-labelledby="roadmap-h" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="roadmap-h" className="text-sm font-semibold">Roadmap</h2>
        <p className="text-xs text-muted">Drag cards between columns, or use the move button on each card.</p>
      </div>
      <div aria-live="polite">
        {notice && (
          <p
            role={notice.tone === "error" ? "alert" : "status"}
            className={cn(
              "rounded-lg border px-3 py-2 text-xs",
              notice.tone === "error" ? "border-danger/40 bg-danger/5 text-danger" : "border-success/40 bg-success/5 text-success",
            )}
          >
            {notice.text}
          </p>
        )}
      </div>
      {q.isError && <Card><ErrorState error={q.error} onRetry={() => void q.refetch()} /></Card>}
      {q.data && all.length === 0 && (
        <Card>
          <EmptyState icon={MapIcon} title="No initiatives yet" description="Initiatives appear here once they're created in Strategy or synced from your tracker." />
        </Card>
      )}
      {(q.isLoading || all.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-3">
          {BUCKETS.map((b) => {
            const cards = q.data?.buckets[b.id] ?? [];
            return (
              <div
                key={b.id}
                role="group"
                aria-labelledby={`bucket-${b.id}`}
                onDragOver={(e) => {
                  if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setOver(b.id);
                }}
                onDragLeave={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(null);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setOver(null);
                  const card = all.find((c) => c.id === e.dataTransfer.getData(DRAG_TYPE));
                  if (card) onMove(card, b.id);
                }}
                className={cn(
                  "min-h-40 space-y-3 rounded-xl border-2 border-dashed border-transparent bg-surface-2/60 p-3 transition-colors",
                  over === b.id && "border-accent bg-accent/5",
                )}
              >
                <div className="flex items-baseline justify-between">
                  <h3 id={`bucket-${b.id}`} className="text-sm font-semibold">
                    {b.label} <span className="font-normal text-muted">({cards.length})</span>
                  </h3>
                  <span className="text-xs text-muted">{b.hint}</span>
                </div>
                {q.isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-32" />)}
                {q.data && cards.length === 0 && <p className="py-6 text-center text-xs text-muted">Nothing here. Drop a card to plan it {b.label.toLowerCase()}.</p>}
                {cards.map((c) => (
                  <InitiativeTile key={c.id} card={c} onMove={onMove} disabled={move.isPending} />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
