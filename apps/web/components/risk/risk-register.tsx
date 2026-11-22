"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, History, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { RiskBadge } from "@/components/twin/risk-badge";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { relTime } from "@/lib/format";
import { useUi } from "@/lib/store";

type Risk = Schemas["RiskOut"];
const STATUSES = ["open", "mitigating", "closed"] as const;
const STATUS_TONE = { open: "warning", mitigating: "accent", closed: "neutral" } as const;

const createSchema = z.object({
  title: z.string().trim().min(3, "At least 3 characters").max(300),
  description: z.string(),
  probability: z.number({ error: "Enter a number" }).min(0, "0–100").max(100, "0–100"),
  impact: z.number().int().min(1).max(5),
  mitigation: z.string(),
  owner_person_id: z.string(),
});
type CreateValues = z.infer<typeof createSchema>;

const editSchema = z.object({
  status: z.enum(STATUSES),
  probability: z.number({ error: "Enter a number" }).min(0, "0–100").max(100, "0–100"),
  mitigation: z.string(),
});
type EditValues = z.infer<typeof editSchema>;

function FieldError({ id, msg }: { id: string; msg?: string }) {
  return msg ? (
    <p id={id} className="text-xs text-danger">
      {msg}
    </p>
  ) : null;
}

function CreateRiskDialog({ programId, open, setOpen }: { programId: string; open: boolean; setOpen: (o: boolean) => void }) {
  const qc = useQueryClient();
  const people = useQuery({ queryKey: ["people"], enabled: open, queryFn: async () => unwrap(await api.GET("/api/v1/people")) });
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { title: "", description: "", probability: 50, impact: 3, mitigation: "", owner_person_id: "" },
  });
  const create = useMutation({
    mutationFn: async (v: CreateValues) =>
      unwrap(
        await api.POST("/api/v1/risk/register", {
          body: {
            program_id: programId,
            title: v.title,
            description: v.description,
            probability: v.probability / 100,
            impact: v.impact,
            mitigation: v.mitigation,
            owner_person_id: v.owner_person_id || null,
          },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["risk-register", programId] });
      form.reset();
      setOpen(false);
    },
  });
  const e = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="New risk" description="Add a risk to the program register.">
        <form className="space-y-3" noValidate onSubmit={form.handleSubmit((v) => create.mutate(v))}>
          <div className="space-y-1">
            <Label htmlFor="r-title">Title</Label>
            <Input id="r-title" aria-invalid={!!e.title} aria-describedby="r-title-err" {...form.register("title")} />
            <FieldError id="r-title-err" msg={e.title?.message} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="r-desc">Description</Label>
            <Textarea id="r-desc" rows={3} {...form.register("description")} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="r-prob">Probability (%)</Label>
              <Input id="r-prob" type="number" min={0} max={100} aria-invalid={!!e.probability} aria-describedby="r-prob-err" {...form.register("probability", { valueAsNumber: true })} />
              <FieldError id="r-prob-err" msg={e.probability?.message} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="r-impact">Impact (1–5)</Label>
              <Select id="r-impact" className="w-full" {...form.register("impact", { valueAsNumber: true })}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="r-mit">Mitigation</Label>
            <Textarea id="r-mit" rows={2} {...form.register("mitigation")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="r-owner">Owner</Label>
            <Select id="r-owner" className="w-full" {...form.register("owner_person_id")}>
              <option value="">Unassigned</option>
              {people.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.title}
                </option>
              ))}
            </Select>
          </div>
          {create.isError && (
            <p role="alert" className="text-sm text-danger">
              {create.error instanceof ApiError ? create.error.message : "Couldn't save the risk."}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="accent" disabled={create.isPending}>
              {create.isPending ? "Saving…" : "Add risk"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditRiskDialog({ risk, programId, onClose }: { risk: Risk; programId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      status: (STATUSES as readonly string[]).includes(risk.status) ? (risk.status as EditValues["status"]) : "open",
      probability: Math.round(risk.probability * 100),
      mitigation: risk.mitigation,
    },
  });
  const save = useMutation({
    mutationFn: async (v: EditValues) =>
      unwrap(
        await api.PATCH("/api/v1/risk/register/{risk_id}", {
          params: { path: { risk_id: risk.id } },
          body: { status: v.status, probability: v.probability / 100, mitigation: v.mitigation },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["risk-register", programId] });
      onClose();
    },
  });
  const e = form.formState.errors;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Edit risk" description={risk.title}>
        <form className="space-y-3" noValidate onSubmit={form.handleSubmit((v) => save.mutate(v))}>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="e-status">Status</Label>
              <Select id="e-status" className="w-full" {...form.register("status")}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="e-prob">Probability (%)</Label>
              <Input id="e-prob" type="number" min={0} max={100} aria-invalid={!!e.probability} aria-describedby="e-prob-err" {...form.register("probability", { valueAsNumber: true })} />
              <FieldError id="e-prob-err" msg={e.probability?.message} />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="e-mit">Mitigation</Label>
            <Textarea id="e-mit" rows={4} {...form.register("mitigation")} />
          </div>
          {save.isError && (
            <p role="alert" className="text-sm text-danger">
              {save.error instanceof ApiError ? save.error.message : "Couldn't save changes."}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="accent" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RiskRegister({ programId }: { programId: string }) {
  const me = useMe();
  const canWrite = me.data?.permissions.includes("risk:write") ?? false;
  const openAudit = useUi((s) => s.openAudit);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Risk | null>(null);
  const q = useQuery({
    queryKey: ["risk-register", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/risk/register", { params: { query: { program_id: programId } } })),
  });
  const people = useQuery({ queryKey: ["people"], queryFn: async () => unwrap(await api.GET("/api/v1/people")) });
  const ownerName = (id: string | null) => (id ? people.data?.find((p) => p.id === id)?.name ?? "—" : "Unassigned");
  const rows = [...(q.data ?? [])].sort((a, b) => b.severity - a.severity);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle id="register-h">Risk register</CardTitle>
          <CardDescription>Program risks, including ones the model raised automatically.</CardDescription>
        </div>
        {canWrite && (
          <Button size="sm" variant="accent" onClick={() => setCreating(true)}>
            <Plus /> New risk
          </Button>
        )}
      </CardHeader>
      <CardContent className="px-2">
        {q.isLoading && <SkeletonLoader rows={5} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && (
          <EmptyState title="No risks registered" description="Add one, or let the model raise them as it finds them." action={canWrite ? { label: "New risk", onClick: () => setCreating(true) } : undefined} />
        )}
        {rows.length > 0 && (
          <Table aria-labelledby="register-h" data-testid="risk-register">
            <THead>
              <TR>
                <TH>Risk</TH>
                <TH>Probability</TH>
                <TH>Impact</TH>
                <TH>Status</TH>
                <TH>Owner</TH>
                <TH>Mitigation</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((r) => (
                <TR key={r.id}>
                  <TD className="max-w-72">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium">{r.title}</span>
                      {r.source === "model" && (
                        <Badge tone="accent" title="Raised automatically by the risk model">
                          <Bot className="size-3" aria-hidden /> Model
                        </Badge>
                      )}
                    </div>
                    {r.description && <p className="line-clamp-2 text-xs text-muted">{r.description}</p>}
                    <p className="text-[11px] text-muted">Updated {relTime(r.updated_at)}</p>
                  </TD>
                  <TD>
                    <RiskBadge probability={r.probability} />
                  </TD>
                  <TD className="tabular-nums">{r.impact}/5</TD>
                  <TD>
                    <Badge tone={STATUS_TONE[r.status as keyof typeof STATUS_TONE] ?? "neutral"}>{r.status}</Badge>
                  </TD>
                  <TD className="text-xs">{ownerName(r.owner_person_id)}</TD>
                  <TD className="max-w-64 text-xs text-muted">
                    <span className="line-clamp-2">{r.mitigation || "—"}</span>
                  </TD>
                  <TD>
                    <div className="flex gap-1">
                      {canWrite && (
                        <Button size="icon" variant="ghost" aria-label={`Edit ${r.title}`} onClick={() => setEditing(r)}>
                          <Pencil />
                        </Button>
                      )}
                      <Button size="icon" variant="ghost" aria-label={`Audit trail for ${r.title}`} onClick={() => openAudit({ entityId: r.id, title: r.title })}>
                        <History />
                      </Button>
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
      <CreateRiskDialog programId={programId} open={creating} setOpen={setCreating} />
      {editing && <EditRiskDialog risk={editing} programId={programId} onClose={() => setEditing(null)} />}
    </Card>
  );
}
