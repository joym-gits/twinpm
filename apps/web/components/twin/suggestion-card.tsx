"use client";

import { Check, HelpCircle, History, Pencil, Undo2, X } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { DriverList, type DriverLike } from "@/components/twin/driver-list";
import { TwinLabel } from "@/components/twin/twin-label";
import { relTime } from "@/lib/format";
import { useRespond, useUndo, type Suggestion } from "@/lib/hooks/use-suggestions";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const LEVEL: Record<number, string> = {
  1: "L1 Observe",
  2: "L2 Suggest",
  3: "L3 Approve",
  4: "L4 Autonomous",
};
const STATUS_TONE = {
  pending: "accent",
  accepted: "success",
  edited: "success",
  auto_executed: "success",
  rejected: "neutral",
  expired: "neutral",
} as const;

function editableText(s: Suggestion): string | null {
  const p = s.payload as Record<string, unknown>;
  if (typeof p.body === "string") return p.body;
  if (typeof p.message === "string") return p.message;
  return null;
}

export function SuggestionCard({
  s,
  twinName = "your twin",
  compact = false,
}: {
  s: Suggestion;
  twinName?: string;
  compact?: boolean;
}) {
  const respond = useRespond();
  const undo = useUndo();
  const openAudit = useUi((u) => u.openAudit);
  const [why, setWhy] = useState(false);
  const [editing, setEditing] = useState(false);
  const original = editableText(s);
  const [draft, setDraft] = useState(original ?? "");
  const pending = s.status === "pending";
  const busy = respond.isPending || undo.isPending;
  const field = typeof (s.payload as Record<string, unknown>).body === "string" ? "body" : "message";
  const canUndo =
    ["accepted", "edited", "auto_executed"].includes(s.status) &&
    !s.undone_at &&
    ["reassign", "create_task", "status_report", "risk_update", "roadmap_change", "scenario"].includes(s.type);

  return (
    <Card className={cn("p-4", !pending && "opacity-90")} data-testid="suggestion-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="neutral">{s.type.replace("_", " ")}</Badge>
            <Badge tone={s.autonomy_level_required >= 3 ? "warning" : "neutral"}>
              {LEVEL[s.autonomy_level_required]}
            </Badge>
            <Badge tone={STATUS_TONE[s.status as keyof typeof STATUS_TONE] ?? "neutral"}>
              {s.status.replace("_", " ")}
            </Badge>
          </div>
          <p className="text-sm font-medium leading-snug">{s.title}</p>
          <div className="flex items-center gap-2">
            <TwinLabel who={twinName} verb={s.status === "auto_executed" ? "Done by" : "Proposed by"} />
            <span className="text-[11px] text-muted">{relTime(s.created_at)}</span>
          </div>
        </div>
      </div>
      {!compact && s.explanation && <p className="mt-2 text-sm text-muted">{s.explanation}</p>}
      {why && (
        <div className="mt-3 space-y-3 rounded-lg bg-surface-2 p-3">
          <DriverList drivers={(s.drivers as unknown as DriverLike[]).slice(0, 5)} />
          <Citations items={s.citations as unknown as CitationLike[]} />
        </div>
      )}
      {editing && original !== null && (
        <div className="mt-3 space-y-2">
          <label htmlFor={`edit-${s.id}`} className="sr-only">
            Edit before approving
          </label>
          <Textarea id={`edit-${s.id}`} rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <p className="text-[11px] text-muted">Your edits teach the twin your style.</p>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {pending && !editing && (
          <>
            <Button size="sm" variant="accent" disabled={busy} onClick={() => respond.mutate({ id: s.id, action: "accept" })}>
              <Check /> {s.type === "status_report" ? "Approve & send" : "Accept"}
            </Button>
            {original !== null && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => respond.mutate({ id: s.id, action: "reject" })}>
              <X /> Reject
            </Button>
          </>
        )}
        {pending && editing && (
          <>
            <Button
              size="sm"
              variant="accent"
              disabled={busy}
              onClick={() => respond.mutate({ id: s.id, action: "edit", edited_payload: { [field]: draft } })}
            >
              <Check /> Save & approve
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </>
        )}
        {canUndo && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => undo.mutate(s.id)}>
            <Undo2 /> Undo
          </Button>
        )}
        <Button size="sm" variant="ghost" aria-expanded={why} onClick={() => setWhy((w) => !w)}>
          <HelpCircle /> Why?
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => openAudit({ suggestionId: s.id, title: s.title })}
          aria-label="Open audit log for this suggestion"
        >
          <History />
        </Button>
      </div>
      {respond.isError && (
        <p className="mt-2 text-xs text-danger" role="alert">
          {(respond.error as Error).message}
        </p>
      )}
    </Card>
  );
}

/** Highlighted approval card for L3 actions waiting on the TPM. */
export function ApprovalCard({ s, twinName }: { s: Suggestion; twinName?: string }) {
  return (
    <div className="rounded-xl border-2 border-warning/40">
      <SuggestionCard s={s} twinName={twinName} />
    </div>
  );
}
