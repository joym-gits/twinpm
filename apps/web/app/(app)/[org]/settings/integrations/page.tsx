"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Integration = Schemas["IntegrationOut"];
type Field = { key: string; label: string; secret?: boolean; placeholder?: string };

const PROVIDERS: Record<string, { name: string; fields: Field[] }> = {
  jira: {
    name: "Jira",
    fields: [
      { key: "base_url", label: "Base URL", placeholder: "https://your-site.atlassian.net" },
      { key: "email", label: "Account email" },
      { key: "api_token", label: "API token", secret: true },
      { key: "jql", label: "JQL filter", placeholder: "project = PAY" },
    ],
  },
  github: {
    name: "GitHub",
    fields: [
      { key: "token", label: "Access token", secret: true },
      { key: "repo", label: "Repository", placeholder: "owner/name" },
    ],
  },
  slack: { name: "Slack", fields: [{ key: "bot_token", label: "Bot token", secret: true, placeholder: "xoxb-…" }] },
};

function ProviderCard({ i, canManage }: { i: Integration; canManage: boolean }) {
  const qc = useQueryClient();
  const meta = PROVIDERS[i.provider] ?? { name: i.provider, fields: [] };
  const [configuring, setConfiguring] = useState(false);
  const [config, setConfig] = useState<Record<string, string>>({});
  const patch = useMutation({
    mutationFn: async (body: Schemas["IntegrationPatch"]) =>
      unwrap(await api.PATCH("/api/v1/integrations/{integration_id}", { params: { path: { integration_id: i.id } }, body })),
    onSuccess: () => {
      setConfiguring(false);
      setConfig({});
      void qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
  const sync = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/integrations/{integration_id}/sync", { params: { path: { integration_id: i.id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["integrations"] }),
  });
  const chooseMode = (mode: "mock" | "live") => {
    if (mode === i.mode) return;
    if (mode === "live" && !i.configured) setConfiguring(true);
    else patch.mutate({ mode });
  };
  const complete = meta.fields.every((f) => config[f.key]?.trim());
  const err = patch.error ?? sync.error;

  return (
    <Card className="space-y-3 p-4" data-testid={`integration-${i.provider}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{meta.name}</h3>
          <p className="text-xs text-muted">
            {i.last_sync_at ? `Last synced ${relTime(i.last_sync_at)}` : "Never synced"} · status {i.status}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={i.configured ? "success" : "neutral"}>{i.configured ? "Credentials stored" : "Not configured"}</Badge>
          <div role="radiogroup" aria-label={`${meta.name} mode`} className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
            {(["mock", "live"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={i.mode === m}
                disabled={!canManage || patch.isPending}
                onClick={() => chooseMode(m)}
                className={cn("rounded-md px-3 py-1 text-xs capitalize", i.mode === m ? "bg-surface font-semibold shadow-sm" : "text-muted hover:text-text")}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {configuring && (
        <form
          className="space-y-3 rounded-lg bg-surface-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (complete) patch.mutate({ mode: "live", config });
          }}
        >
          <p className="text-xs text-muted">Live mode needs credentials. They are encrypted at rest and never shown again.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {meta.fields.map((f) => (
              <div key={f.key} className="space-y-1">
                <Label htmlFor={`${i.id}-${f.key}`}>{f.label}</Label>
                <Input
                  id={`${i.id}-${f.key}`}
                  type={f.secret ? "password" : "text"}
                  autoComplete="off"
                  required
                  placeholder={f.placeholder}
                  value={config[f.key] ?? ""}
                  onChange={(e) => setConfig((c) => ({ ...c, [f.key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button type="submit" size="sm" variant="accent" disabled={!complete || patch.isPending}>
              {patch.isPending ? "Saving…" : "Save and go live"}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setConfiguring(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {canManage && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={sync.isPending} onClick={() => sync.mutate()}>
            <RefreshCw className={sync.isPending ? "animate-spin" : ""} /> {sync.isPending ? "Syncing…" : "Sync now"}
          </Button>
          {i.mode === "live" && !configuring && (
            <Button size="sm" variant="ghost" onClick={() => setConfiguring(true)}>
              Update credentials
            </Button>
          )}
        </div>
      )}

      {err && (
        <p role="alert" className="text-sm text-danger">
          {err instanceof ApiError ? err.message : "Request failed."}
        </p>
      )}
      {sync.data && (
        <div className="rounded-lg border border-border p-3 text-xs" aria-live="polite">
          <p className="font-medium">
            {sync.data.created} created · {sync.data.updated} updated · {sync.data.events} events
          </p>
          {sync.data.details.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted">
              {sync.data.details.map((d, n) => (
                <li key={n}>{d}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

export default function IntegrationsPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["integrations"], queryFn: async () => unwrap(await api.GET("/api/v1/integrations")) });
  const canManage = me.data?.permissions.includes("integrations:manage") ?? false;
  return (
    <SettingsShell title="Integrations" description="Mock mode uses built-in sample data; live mode connects to your real tools.">
      {!canManage && <p className="text-sm text-muted">Your role can view integrations but not change or sync them.</p>}
      {q.isLoading && <SkeletonLoader rows={6} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title="No integrations available" />}
      <div className="space-y-3">
        {q.data?.map((i) => (
          <ProviderCard key={i.id} i={i} canManage={canManage} />
        ))}
      </div>
    </SettingsShell>
  );
}
