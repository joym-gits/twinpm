"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Tooltip } from "@/components/ui/tooltip";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { cn } from "@/lib/utils";

const STEPS = [1, 2, 3, 4] as const;
const humanize = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

function LevelControl({ p, value, onChange, disabled }: { p: Schemas["PolicyEntry"]; value: number; onChange: (v: number) => void; disabled: boolean }) {
  return (
    <fieldset className="min-w-0" disabled={disabled}>
      <legend className="sr-only">Autonomy level for {humanize(p.action_type)}</legend>
      <div className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
        {STEPS.map((n) => {
          const capped = n > p.max_level;
          const id = `lvl-${p.action_type}-${n}`;
          const label = (
            <label
              htmlFor={id}
              className={cn(
                "relative flex h-8 w-10 cursor-pointer items-center justify-center rounded-md text-sm tabular-nums has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                value === n ? "bg-accent font-semibold text-accent-fg shadow-sm" : "text-muted hover:text-text",
                capped && "cursor-not-allowed opacity-40 hover:text-muted",
              )}
            >
              <input
                type="radio"
                id={id}
                name={`lvl-${p.action_type}`}
                value={n}
                checked={value === n}
                disabled={capped}
                onChange={() => onChange(n)}
                className="sr-only"
              />
              {n}
              {n === p.default_level && <span className="absolute bottom-0.5 size-1 rounded-full bg-current" aria-hidden />}
              <span className="sr-only">
                {n === p.default_level ? " (default)" : ""}
                {capped ? " (capped: needs a human)" : ""}
              </span>
            </label>
          );
          return capped ? (
            <Tooltip key={n} content="Capped: needs a human">
              {label}
            </Tooltip>
          ) : (
            <span key={n} className="contents">
              {label}
            </span>
          );
        })}
      </div>
    </fieldset>
  );
}

function AutonomyForm({ data, canEdit }: { data: Schemas["AutonomyOut"]; canEdit: boolean }) {
  const qc = useQueryClient();
  const [levels, setLevels] = useState<Record<string, number>>(() => Object.fromEntries(data.policies.map((p) => [p.action_type, p.level])));
  const dirty = data.policies.some((p) => levels[p.action_type] !== p.level);
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PUT("/api/v1/autonomy-policy", { body: { levels, program_id: data.program_id } })),
    onSuccess: (d) => qc.setQueryData(["autonomy"], d),
  });
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="mb-2 text-sm font-semibold">What each level means</h3>
        <dl className="grid gap-2 sm:grid-cols-2">
          {Object.entries(data.levels)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <dt className="grid size-6 shrink-0 place-items-center rounded-md bg-surface-2 font-semibold">{k}</dt>
                <dd className="text-muted">{v}</dd>
              </div>
            ))}
        </dl>
        <p className="mt-2 text-xs text-muted">A dot marks the default level. Levels above an action&apos;s cap always need a human.</p>
      </Card>
      <Card>
        <CardContent className="p-0">
          <ul className="divide-y divide-border" data-testid="autonomy-table">
            {data.policies.map((p) => (
              <li key={p.action_type} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0 max-w-md">
                  <p className="text-sm font-medium">{humanize(p.action_type)}</p>
                  <p className="mt-0.5 text-xs">
                    Level {levels[p.action_type]}: <span className="text-muted">{data.levels[String(levels[p.action_type])]}</span>
                  </p>
                </div>
                <LevelControl p={p} value={levels[p.action_type] ?? p.level} disabled={!canEdit} onChange={(v) => setLevels((l) => ({ ...l, [p.action_type]: v }))} />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      {canEdit ? (
        <div className="flex items-center gap-3">
          <Button variant="accent" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save autonomy"}
          </Button>
          <span role="status" className="text-sm">
            {save.isSuccess && !dirty && <span className="text-success">Saved.</span>}
            {save.isError && <span className="text-danger">{save.error instanceof ApiError ? save.error.message : "Couldn't save."}</span>}
          </span>
        </div>
      ) : (
        <p className="text-sm text-muted">Your role can view but not change autonomy levels.</p>
      )}
    </div>
  );
}

export default function AutonomyPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["autonomy"], queryFn: async () => unwrap(await api.GET("/api/v1/autonomy-policy")) });
  return (
    <SettingsShell title="Autonomy" description="How far your twin may act on its own, per action type.">
      {q.isLoading && <SkeletonLoader rows={8} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data && <AutonomyForm data={q.data} canEdit={me.data?.permissions.includes("persona:write") ?? false} />}
    </SettingsShell>
  );
}
