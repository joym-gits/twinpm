"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ErrorState, SkeletonLoader } from "@/components/ui/states";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";

type Persona = Schemas["PersonaOut"];
type Rule = { when: string; then: string };
const MAX_EXAMPLES = 10;
const MAX_PRIORITIES = 12;

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length) return list;
  const next = [...list];
  const [x] = next.splice(from, 1);
  next.splice(to, 0, x!);
  return next;
}

function PersonaForm({ initial, canEdit }: { initial: Persona; canEdit: boolean }) {
  const qc = useQueryClient();
  const [priorities, setPriorities] = useState(initial.priorities);
  const [newPriority, setNewPriority] = useState("");
  const [tone, setTone] = useState(initial.tone);
  const [risk, setRisk] = useState(initial.risk_tolerance);
  const [rules, setRules] = useState<Rule[]>(() => initial.escalation_rules.map((r) => ({ when: String(r.when ?? ""), then: String(r.then ?? "") })));
  const [examples, setExamples] = useState(initial.style_examples);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [announce, setAnnounce] = useState("");

  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PUT("/api/v1/persona", {
          body: {
            priorities: priorities.filter((p) => p.trim()),
            tone,
            risk_tolerance: risk,
            escalation_rules: rules.filter((r) => r.when.trim() && r.then.trim()),
            style_examples: examples.filter((e) => e.trim()),
            working_hours: initial.working_hours,
          },
        }),
      ),
    onSuccess: (d) => qc.setQueryData(["persona"], d),
  });

  const movePriority = (i: number, to: number) => {
    if (to < 0 || to >= priorities.length) return;
    setPriorities((p) => move(p, i, to));
    setAnnounce(`${priorities[i]} moved to position ${to + 1} of ${priorities.length}`);
  };

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <fieldset disabled={!canEdit} className="space-y-4">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Priorities</CardTitle>
              <CardDescription>What the twin optimises for, most important first. Drag to reorder, or use the arrow buttons.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="sr-only" aria-live="polite">
              {announce}
            </p>
            <ol className="space-y-1.5" aria-label="Priorities in order">
              {priorities.map((p, i) => (
                <li
                  key={`${p}-${i}`}
                  draggable={canEdit}
                  onDragStart={() => setDragIdx(i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (dragIdx !== null) movePriority(dragIdx, i);
                    setDragIdx(null);
                  }}
                  onDragEnd={() => setDragIdx(null)}
                  className={`flex items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm ${dragIdx === i ? "opacity-50" : ""}`}
                >
                  <GripVertical className="size-4 shrink-0 cursor-grab text-muted" aria-hidden />
                  <span className="w-5 text-xs tabular-nums text-muted">{i + 1}.</span>
                  <span className="flex-1">{p}</span>
                  <Button type="button" size="icon" variant="ghost" className="size-7" aria-label={`Move ${p} up`} disabled={i === 0} onClick={() => movePriority(i, i - 1)}>
                    <ArrowUp />
                  </Button>
                  <Button type="button" size="icon" variant="ghost" className="size-7" aria-label={`Move ${p} down`} disabled={i === priorities.length - 1} onClick={() => movePriority(i, i + 1)}>
                    <ArrowDown />
                  </Button>
                  <Button type="button" size="icon" variant="ghost" className="size-7" aria-label={`Remove ${p}`} onClick={() => setPriorities((l) => l.filter((_, j) => j !== i))}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ol>
            {priorities.length < MAX_PRIORITIES && (
              <div className="flex gap-2">
                <Input aria-label="New priority" value={newPriority} onChange={(e) => setNewPriority(e.target.value)} placeholder="Add a priority" maxLength={120} />
                <Button
                  type="button"
                  variant="outline"
                  disabled={!newPriority.trim()}
                  onClick={() => {
                    setPriorities((l) => [...l, newPriority.trim()]);
                    setNewPriority("");
                  }}
                >
                  <Plus /> Add
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Voice and judgement</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="p-tone">Tone</Label>
              <Select id="p-tone" className="w-full" value={tone} onChange={(e) => setTone(e.target.value as Persona["tone"])}>
                <option value="concise">Concise</option>
                <option value="detailed">Detailed</option>
                <option value="formal">Formal</option>
                <option value="friendly">Friendly</option>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="p-risk">Risk tolerance</Label>
              <Select id="p-risk" className="w-full" value={risk} onChange={(e) => setRisk(e.target.value as Persona["risk_tolerance"])}>
                <option value="low">Low: flag early, escalate often</option>
                <option value="medium">Medium</option>
                <option value="high">High: only flag what is likely to bite</option>
              </Select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Escalation rules</CardTitle>
              <CardDescription>When this happens, the twin does that.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {rules.length === 0 && <p className="text-xs text-muted">No rules yet.</p>}
            <ul className="space-y-2">
              {rules.map((r, i) => (
                <li key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <div className="space-y-1">
                    <Label htmlFor={`rule-when-${i}`}>When</Label>
                    <Input id={`rule-when-${i}`} value={r.when} onChange={(e) => setRules((l) => l.map((x, j) => (j === i ? { ...x, when: e.target.value } : x)))} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`rule-then-${i}`}>Then</Label>
                    <Input id={`rule-then-${i}`} value={r.then} onChange={(e) => setRules((l) => l.map((x, j) => (j === i ? { ...x, then: e.target.value } : x)))} />
                  </div>
                  <Button type="button" size="icon" variant="ghost" aria-label={`Remove rule ${i + 1}`} onClick={() => setRules((l) => l.filter((_, j) => j !== i))}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
            {rules.length < 20 && (
              <Button type="button" size="sm" variant="outline" onClick={() => setRules((l) => [...l, { when: "", then: "" }])}>
                <Plus /> Add rule
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Style examples</CardTitle>
              <CardDescription>
                Samples of how you write, up to {MAX_EXAMPLES}. When you edit a status report the twin drafted, your edited version is added here automatically.
              </CardDescription>
            </div>
            <span className="text-xs tabular-nums text-muted">
              {examples.length}/{MAX_EXAMPLES}
            </span>
          </CardHeader>
          <CardContent className="space-y-2">
            {examples.map((ex, i) => (
              <div key={i} className="flex items-start gap-2">
                <Textarea aria-label={`Style example ${i + 1}`} rows={3} value={ex} onChange={(e) => setExamples((l) => l.map((x, j) => (j === i ? e.target.value : x)))} />
                <Button type="button" size="icon" variant="ghost" aria-label={`Remove style example ${i + 1}`} onClick={() => setExamples((l) => l.filter((_, j) => j !== i))}>
                  <Trash2 />
                </Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="outline" disabled={examples.length >= MAX_EXAMPLES} onClick={() => setExamples((l) => [...l, ""])}>
              <Plus /> Add example
            </Button>
          </CardContent>
        </Card>
      </fieldset>

      {canEdit ? (
        <div className="flex items-center gap-3">
          <Button type="submit" variant="accent" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save persona"}
          </Button>
          <span role="status" className="text-sm">
            {save.isSuccess && <span className="text-success">Saved.</span>}
            {save.isError && <span className="text-danger">{save.error instanceof ApiError ? save.error.message : "Couldn't save."}</span>}
          </span>
        </div>
      ) : (
        <p className="text-sm text-muted">Your role can view but not edit the persona.</p>
      )}
    </form>
  );
}

export default function PersonaPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["persona"], queryFn: async () => unwrap(await api.GET("/api/v1/persona")) });
  return (
    <SettingsShell title="Persona" description="How your twin thinks, prioritises and sounds.">
      {q.isLoading && <SkeletonLoader rows={8} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && <PersonaForm key={q.data.user_id} initial={q.data} canEdit={me.data?.permissions.includes("persona:write") ?? false} />}
    </SettingsShell>
  );
}
