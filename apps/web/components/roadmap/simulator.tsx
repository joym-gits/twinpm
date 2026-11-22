"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Play, Plus, Save, Trash2 } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { Area, AreaChart, Legend, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { ForecastBand } from "@/components/twin/forecast-band";
import { Markdown } from "@/components/twin/markdown";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { shortDate } from "@/lib/format";

type Change = Schemas["SimulateRequest"]["changes"][number];
type ChangeType = Change["type"];
type Sim = Schemas["SimulateOut"];
/** Untyped dicts in SimulateOut; shapes from services/planning.py and ml/forecast.py. */
type Hist = { date: string; count: number }[];
type AffectedEpic = { id: string; title: string; baseline_p80: string; scenario_p80: string };

const TYPE_LABEL: Record<ChangeType, string> = {
  add_scope: "Add scope",
  remove_scope: "Remove scope",
  capacity_change: "Change team capacity",
  reassign: "Reassign work",
  date_shift: "Shift target date",
};
const MAX_COMPARE = 3;
const signed = (n: number, unit = "") => `${n > 0 ? "+" : ""}${n}${unit}`;
const pp = (n: number) => `${n > 0 ? "+" : ""}${Math.round(n * 100)} pts`;

function useLookups() {
  const teams = useQuery({ queryKey: ["teams"], queryFn: async () => unwrap(await api.GET("/api/v1/teams")) });
  const epics = useQuery({ queryKey: ["epics"], queryFn: async () => unwrap(await api.GET("/api/v1/epics")) });
  const people = useQuery({ queryKey: ["people"], queryFn: async () => unwrap(await api.GET("/api/v1/people")) });
  return { teams, epics, people };
}

function useOpenItems(epicId?: string, enabled = true) {
  return useQuery({
    queryKey: ["work-items", { epicId: epicId ?? null, open: true }],
    enabled,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/work-items", { params: { query: { epic_id: epicId ?? null, open_only: true } } })),
  });
}

/** Checkbox list with a text filter, used for remove_scope and reassign. */
function ItemPicker({
  items,
  selected,
  onChange,
  legend,
}: {
  items: Schemas["WorkItemOut"][];
  selected: string[];
  onChange: (ids: string[]) => void;
  legend: string;
}) {
  const [filter, setFilter] = useState("");
  const id = useId();
  const f = filter.toLowerCase();
  const shown = items.filter((w) => !f || w.key.toLowerCase().includes(f) || w.title.toLowerCase().includes(f));
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-muted">
        {legend} <span className="tabular-nums">({selected.length} selected)</span>
      </legend>
      <label htmlFor={`${id}-f`} className="sr-only">
        Filter items
      </label>
      <Input id={`${id}-f`} placeholder="Filter by key or title" value={filter} onChange={(e) => setFilter(e.target.value)} />
      <ul className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border p-2 text-xs">
        {shown.length === 0 && <li className="text-muted">No open items match.</li>}
        {shown.map((w) => (
          <li key={w.id}>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5 accent-[var(--accent)]"
                checked={selected.includes(w.id)}
                onChange={(e) => onChange(e.target.checked ? [...selected, w.id] : selected.filter((x) => x !== w.id))}
              />
              <span>
                <span className="font-mono">{w.key}</span> {w.title} <span className="text-muted">· {w.story_points} pts</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

function ChangeBuilder({ onAdd }: { onAdd: (c: Change) => void }) {
  const { teams, epics, people } = useLookups();
  const id = useId();
  const [type, setType] = useState<ChangeType>("add_scope");
  const [teamId, setTeamId] = useState("");
  const [epicId, setEpicId] = useState("");
  const [points, setPoints] = useState(8);
  const [items, setItems] = useState(1);
  const [factor, setFactor] = useState(1);
  const [days, setDays] = useState(7);
  const [toPerson, setToPerson] = useState("");
  const [workIds, setWorkIds] = useState<string[]>([]);
  const epicItems = useOpenItems(epicId, type === "remove_scope" && !!epicId);
  const allItems = useOpenItems(undefined, type === "reassign");

  const build = (): Change | null => {
    switch (type) {
      case "add_scope":
        return teamId && epicId && points > 0 && items > 0 ? { type, team_id: teamId, epic_id: epicId, points, items } : null;
      case "remove_scope":
        return workIds.length ? { type, work_item_ids: workIds } : null;
      case "capacity_change":
        return teamId ? { type, team_id: teamId, factor } : null;
      case "reassign":
        return workIds.length && toPerson ? { type, work_item_ids: workIds, to_person_id: toPerson } : null;
      case "date_shift":
        return days !== 0 ? { type, days } : null;
    }
  };
  const change = build();
  const lookupError = teams.error ?? epics.error ?? people.error;

  const teamSelect = (
    <div className="space-y-1">
      <Label htmlFor={`${id}-team`}>Team</Label>
      <Select id={`${id}-team`} className="w-full" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
        <option value="">Choose a team</option>
        {teams.data?.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name} ({t.size})
          </option>
        ))}
      </Select>
    </div>
  );
  const epicSelect = (
    <div className="space-y-1">
      <Label htmlFor={`${id}-epic`}>Epic</Label>
      <Select
        id={`${id}-epic`}
        className="w-full"
        value={epicId}
        onChange={(e) => {
          setEpicId(e.target.value);
          setWorkIds([]);
        }}
      >
        <option value="">Choose an epic</option>
        {epics.data?.map((e) => (
          <option key={e.id} value={e.id}>
            {e.key} · {e.title}
          </option>
        ))}
      </Select>
    </div>
  );

  return (
    <div className="space-y-3">
      {lookupError && <ErrorState error={lookupError} />}
      <div className="space-y-1">
        <Label htmlFor={`${id}-type`}>Change type</Label>
        <Select
          id={`${id}-type`}
          className="w-full"
          value={type}
          onChange={(e) => {
            setType(e.target.value as ChangeType);
            setWorkIds([]);
          }}
        >
          {Object.entries(TYPE_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
      </div>
      {type === "add_scope" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {teamSelect}
          {epicSelect}
          <div className="space-y-1">
            <Label htmlFor={`${id}-pts`}>Story points</Label>
            <Input id={`${id}-pts`} type="number" min={1} value={points} onChange={(e) => setPoints(Number(e.target.value))} />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-items`}>Number of items</Label>
            <Input id={`${id}-items`} type="number" min={1} value={items} onChange={(e) => setItems(Number(e.target.value))} />
          </div>
        </div>
      )}
      {type === "remove_scope" && (
        <div className="space-y-3">
          {epicSelect}
          {epicId && epicItems.isLoading && <SkeletonLoader rows={2} className="p-0" />}
          {epicItems.isError && <ErrorState error={epicItems.error} onRetry={() => void epicItems.refetch()} />}
          {epicId && epicItems.data && (
            <ItemPicker legend="Open items to remove" items={epicItems.data} selected={workIds} onChange={setWorkIds} />
          )}
        </div>
      )}
      {type === "capacity_change" && (
        <div className="space-y-3">
          {teamSelect}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-muted">Capacity factor</span>
              <span className="tabular-nums" aria-hidden>
                ×{factor.toFixed(2)} ({signed(Math.round((factor - 1) * 100), "%")})
              </span>
            </div>
            <Slider
              label="Capacity factor"
              min={0.5}
              max={1.5}
              step={0.05}
              value={[factor]}
              onValueChange={([v]) => setFactor(v ?? 1)}
              aria-valuetext={`${Math.round(factor * 100)} percent of current capacity`}
            />
          </div>
        </div>
      )}
      {type === "reassign" && (
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor={`${id}-to`}>Reassign to</Label>
            <Select id={`${id}-to`} className="w-full" value={toPerson} onChange={(e) => setToPerson(e.target.value)}>
              <option value="">Choose a person</option>
              {people.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.title}
                </option>
              ))}
            </Select>
          </div>
          {allItems.isLoading && <SkeletonLoader rows={2} className="p-0" />}
          {allItems.isError && <ErrorState error={allItems.error} onRetry={() => void allItems.refetch()} />}
          {allItems.data && <ItemPicker legend="Items to reassign" items={allItems.data} selected={workIds} onChange={setWorkIds} />}
        </div>
      )}
      {type === "date_shift" && (
        <div className="space-y-1">
          <Label htmlFor={`${id}-days`}>Move target date by (days, negative = earlier)</Label>
          <Input id={`${id}-days`} type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} />
        </div>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={!change}
        onClick={() => {
          if (!change) return;
          onAdd(change);
          setWorkIds([]);
        }}
      >
        <Plus /> Add change
      </Button>
    </div>
  );
}

function describe(c: Change, names: Map<string, string>): string {
  const n = (id: string) => names.get(id) ?? "unknown";
  switch (c.type) {
    case "add_scope":
      return `Add ${c.items} item(s), ${c.points} pts to ${n(c.epic_id)} (${n(c.team_id)})`;
    case "remove_scope":
      return `Remove ${c.work_item_ids.length} item(s): ${c.work_item_ids.map(n).join(", ")}`;
    case "capacity_change":
      return `${n(c.team_id)} capacity ×${c.factor.toFixed(2)}`;
    case "reassign":
      return `Reassign ${c.work_item_ids.map(n).join(", ")} to ${n(c.to_person_id)}`;
    case "date_shift":
      return `Shift target ${signed(c.days, " days")}`;
  }
}

function Histograms({ sim }: { sim: Sim }) {
  const data = useMemo(() => {
    const rows = new Map<string, { date: string; baseline: number; scenario: number }>();
    const add = (h: Hist, k: "baseline" | "scenario") => {
      for (const { date, count } of h) {
        const r = rows.get(date) ?? { date, baseline: 0, scenario: 0 };
        r[k] = count;
        rows.set(date, r);
      }
    };
    add(sim.baseline_histogram as Hist, "baseline");
    add(sim.histogram as Hist, "scenario");
    return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [sim]);
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs font-medium text-muted">Completion date distribution (simulated runs)</figcaption>
      <div className="h-44" role="img" aria-label={`Overlaid histograms. Baseline P80 ${shortDate(sim.baseline.p80)}, scenario P80 ${shortDate(sim.scenario.p80)}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <XAxis dataKey="date" tickFormatter={(d) => shortDate(String(d))} fontSize={10} stroke="var(--muted)" />
            <YAxis hide />
            <RTooltip labelFormatter={(l) => shortDate(String(l))} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area type="step" dataKey="baseline" name="Baseline" stroke="var(--muted)" fill="var(--muted)" fillOpacity={0.2} strokeDasharray="4 3" />
            <Area type="step" dataKey="scenario" name="Scenario" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.3} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function SimResult({ sim }: { sim: Sim }) {
  const affected = sim.affected_epics as unknown as AffectedEpic[];
  const cap = Object.entries(sim.capacity_delta);
  const later = sim.delta_days > 0;
  return (
    <div className="space-y-4" data-testid="sim-result">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted">P80 change</p>
          <p className={`text-4xl font-semibold tabular-nums ${later ? "text-danger" : sim.delta_days < 0 ? "text-success" : ""}`}>
            {signed(sim.delta_days, "d")}
          </p>
          <p className="text-xs text-muted">{sim.delta_days === 0 ? "No change" : later ? "later than baseline" : "earlier than baseline"}</p>
        </div>
        <div>
          <p className="text-xs text-muted">Risk change</p>
          <p className="text-2xl font-semibold tabular-nums">{pp(sim.risk_delta)}</p>
          <p className="text-xs text-muted">average delay probability</p>
        </div>
        <div>
          <p className="text-xs text-muted">Capacity / scope change</p>
          {cap.length === 0 ? (
            <p className="text-sm">None</p>
          ) : (
            <ul className="text-xs">
              {cap.map(([k, v]) => (
                <li key={k}>
                  {k}: <strong className="tabular-nums">{k.endsWith(" capacity") ? signed(Math.round(v * 100), "%") : signed(v, " pts")}</strong>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <ForecastBand label="Baseline" {...sim.baseline} target={sim.target_date} />
        <ForecastBand label="Scenario" {...sim.scenario} target={sim.target_date} />
      </div>
      <Histograms sim={sim} />
      <div className="rounded-lg bg-surface-2 p-3">
        <Markdown text={sim.narrative} />
      </div>
      {affected.length > 0 && (
        <Table>
          <caption className="sr-only">Affected epics</caption>
          <THead>
            <TR>
              <TH>Affected epic</TH>
              <TH>Baseline P80</TH>
              <TH>Scenario P80</TH>
            </TR>
          </THead>
          <TBody>
            {affected.map((e) => (
              <TR key={e.id}>
                <TD className="text-xs">{e.title}</TD>
                <TD className="text-xs tabular-nums">{shortDate(e.baseline_p80)}</TD>
                <TD className="text-xs tabular-nums">{shortDate(e.scenario_p80)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}

function SavedScenarios({ programId }: { programId: string }) {
  const [selected, setSelected] = useState<string[]>([]);
  const q = useQuery({
    queryKey: ["scenarios", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/scenarios", { params: { query: { program_id: programId } } })),
  });
  const chosen = (q.data ?? []).filter((s) => selected.includes(s.id));
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Saved scenarios</CardTitle>
          <CardDescription>Select up to {MAX_COMPARE} to compare.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.isLoading && <SkeletonLoader rows={3} className="p-0" />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && <EmptyState title="No saved scenarios" description="Run a simulation above, name it, and save it to compare options side by side." />}
        {!!q.data?.length && (
          <fieldset>
            <legend className="sr-only">Scenarios to compare</legend>
            <ul className="space-y-1 text-sm">
              {q.data.map((s) => {
                const on = selected.includes(s.id);
                return (
                  <li key={s.id}>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="accent-[var(--accent)]"
                        checked={on}
                        disabled={!on && selected.length >= MAX_COMPARE}
                        onChange={() => setSelected(on ? selected.filter((x) => x !== s.id) : [...selected, s.id])}
                      />
                      {s.name} <span className="text-xs text-muted">· {s.changes.length} change(s) · {shortDate(s.created_at)}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </fieldset>
        )}
        {chosen.length > 0 && (
          <Table data-testid="scenario-compare">
            <caption className="sr-only">Scenario comparison</caption>
            <THead>
              <TR>
                <TH>Scenario</TH>
                <TH>P80</TH>
                <TH>Delta</TH>
                <TH>Risk delta</TH>
              </TR>
            </THead>
            <TBody>
              {chosen.map((s) => {
                const r = s.result as unknown as Partial<Sim>;
                return (
                  <TR key={s.id}>
                    <TD className="text-xs font-medium">{s.name}</TD>
                    <TD className="text-xs tabular-nums">{shortDate(r.scenario?.p80)}</TD>
                    <TD className="text-xs tabular-nums">{r.delta_days !== undefined ? signed(r.delta_days, "d") : "—"}</TD>
                    <TD className="text-xs tabular-nums">{r.risk_delta !== undefined ? pp(r.risk_delta) : "—"}</TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function Simulator({ programId }: { programId: string }) {
  const qc = useQueryClient();
  const { teams, epics, people } = useLookups();
  const allItems = useOpenItems(undefined);
  const [changes, setChanges] = useState<Change[]>([]);
  const [name, setName] = useState("");
  const nameId = useId();
  const names = useMemo(() => {
    const m = new Map<string, string>();
    teams.data?.forEach((t) => m.set(t.id, t.name));
    epics.data?.forEach((e) => m.set(e.id, e.title));
    people.data?.forEach((p) => m.set(p.id, p.name));
    allItems.data?.forEach((w) => m.set(w.id, w.key));
    return m;
  }, [teams.data, epics.data, people.data, allItems.data]);

  const sim = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/scenarios/simulate", { body: { program_id: programId, changes } })),
  });
  const save = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/scenarios", { body: { program_id: programId, name: name.trim(), changes } })),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["scenarios", programId] });
    },
  });

  return (
    <section aria-labelledby="sim-h" className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle id="sim-h">What-if simulator</CardTitle>
            <CardDescription>Compose changes, then rerun the Monte Carlo forecast against the baseline.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <div className="space-y-4">
            <ChangeBuilder onAdd={(c) => setChanges((cs) => [...cs, c])} />
            <div className="space-y-2">
              <h3 className="text-xs font-semibold">Changes in this scenario</h3>
              {changes.length === 0 ? (
                <p className="text-xs text-muted">None yet. Add at least one change to run a simulation.</p>
              ) : (
                <ol className="space-y-1.5">
                  {changes.map((c, i) => (
                    <li key={i} className="flex items-start justify-between gap-2 rounded-lg border border-border px-2 py-1.5 text-xs">
                      <span>
                        <Badge tone="neutral" className="mr-1">{TYPE_LABEL[c.type]}</Badge>
                        {describe(c, names)}
                      </span>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-6 shrink-0"
                        aria-label={`Remove change ${i + 1}`}
                        onClick={() => setChanges((cs) => cs.filter((_, j) => j !== i))}
                      >
                        <Trash2 />
                      </Button>
                    </li>
                  ))}
                </ol>
              )}
              <Button variant="accent" size="sm" disabled={changes.length === 0 || sim.isPending} onClick={() => sim.mutate()}>
                <Play /> {sim.isPending ? "Simulating…" : "Run simulation"}
              </Button>
            </div>
          </div>
          <div className="min-w-0 space-y-4" aria-live="polite">
            {sim.isPending && <SkeletonLoader rows={6} className="p-0" />}
            {sim.isError && <ErrorState error={sim.error} onRetry={() => sim.mutate()} />}
            {!sim.data && !sim.isPending && !sim.isError && (
              <EmptyState icon={FlaskConical} title="No simulation yet" description="Try a capacity change or removing scope to see how the P80 date moves." />
            )}
            {sim.data && !sim.isPending && (
              <>
                <SimResult sim={sim.data} />
                <form
                  className="flex flex-wrap items-end gap-2 border-t border-border pt-4"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (name.trim()) save.mutate();
                  }}
                >
                  <div className="min-w-48 flex-1 space-y-1">
                    <Label htmlFor={nameId}>Scenario name</Label>
                    <Input id={nameId} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cut reporting epic" required />
                  </div>
                  <Button type="submit" size="md" variant="outline" disabled={!name.trim() || save.isPending}>
                    <Save /> {save.isPending ? "Saving…" : "Save scenario"}
                  </Button>
                  {save.isError && <p role="alert" className="w-full text-xs text-danger">{(save.error as Error).message}</p>}
                  {save.isSuccess && <p role="status" className="w-full text-xs text-success">Saved.</p>}
                </form>
              </>
            )}
          </div>
        </CardContent>
      </Card>
      <SavedScenarios programId={programId} />
    </section>
  );
}
