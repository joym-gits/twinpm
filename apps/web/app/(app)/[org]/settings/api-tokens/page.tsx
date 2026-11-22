"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, ApiError, unwrap, type Schemas } from "@/lib/api/client";
import { relTime, shortDate } from "@/lib/format";

function NewToken({ t, onDismiss }: { t: Schemas["TokenCreated"]; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <Card className="space-y-2 border-accent/40 p-4" role="status">
      <p className="text-sm font-medium">
        Token &ldquo;{t.name}&rdquo; created. Copy it now: it won&apos;t be shown again.
      </p>
      <div className="flex gap-2">
        <Input
          readOnly
          value={t.token}
          aria-label="New API token"
          className="font-mono text-xs"
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button
          variant="outline"
          aria-label={copied ? "Copied" : "Copy token"}
          onClick={() => void navigator.clipboard.writeText(t.token).then(() => setCopied(true))}
        >
          {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="text-xs text-muted">
        Use it as a bearer token for the MCP endpoint at{" "}
        <code className="rounded bg-surface-2 px-1">/mcp</code>, so AI assistants can query your
        program on your behalf with your permissions.
      </p>
      <Button size="sm" variant="ghost" onClick={onDismiss}>
        Done
      </Button>
    </Card>
  );
}

export default function ApiTokensPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["api-tokens"],
    queryFn: async () => unwrap(await api.GET("/api/v1/api-tokens")),
  });
  const create = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/api-tokens", { body: { name: name.trim() } })),
    onSuccess: () => {
      setName("");
      void qc.invalidateQueries({ queryKey: ["api-tokens"] });
    },
  });
  const revoke = useMutation({
    mutationFn: async (id: string) => {
      const r = await api.DELETE("/api/v1/api-tokens/{token_id}", {
        params: { path: { token_id: id } },
      });
      if (!r.response.ok)
        throw new ApiError(
          r.response.status,
          `http_${r.response.status}`,
          "Couldn't revoke the token.",
        );
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["api-tokens"] }),
  });

  return (
    <SettingsShell
      title="API tokens"
      description="Personal tokens for the MCP endpoint and automation. They act with your permissions."
    >
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <div className="min-w-60 flex-1 space-y-1">
          <Label htmlFor="token-name">Token name</Label>
          <Input
            id="token-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Claude Desktop"
            maxLength={100}
          />
        </div>
        <Button type="submit" variant="accent" disabled={!name.trim() || create.isPending}>
          <KeyRound /> {create.isPending ? "Creating…" : "Create token"}
        </Button>
      </form>
      {create.isError && (
        <p role="alert" className="text-sm text-danger">
          {create.error instanceof ApiError ? create.error.message : "Couldn't create the token."}
        </p>
      )}
      {create.data && <NewToken t={create.data} onDismiss={() => create.reset()} />}
      {revoke.isError && (
        <p role="alert" className="text-sm text-danger">
          {revoke.error.message}
        </p>
      )}
      <Card className="px-2">
        {q.isLoading && <SkeletonLoader rows={4} />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && (
          <EmptyState
            title="No tokens yet"
            description="Create one to connect an MCP client at /mcp."
          />
        )}
        {!!q.data?.length && (
          <Table aria-label="API tokens" data-testid="tokens-table">
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Prefix</TH>
                <TH>Created</TH>
                <TH>Last used</TH>
                <TH>Status</TH>
                <TH>
                  <span className="sr-only">Actions</span>
                </TH>
              </TR>
            </THead>
            <TBody>
              {q.data.map((t) => (
                <TR key={t.id}>
                  <TD className="font-medium">{t.name}</TD>
                  <TD className="font-mono text-xs">{t.prefix}…</TD>
                  <TD className="text-xs">{shortDate(t.created_at)}</TD>
                  <TD className="text-xs text-muted">
                    {t.last_used_at ? relTime(t.last_used_at) : "Never"}
                  </TD>
                  <TD>
                    <Badge tone={t.revoked_at ? "neutral" : "success"}>
                      {t.revoked_at ? "Revoked" : "Active"}
                    </Badge>
                  </TD>
                  <TD>
                    {!t.revoked_at && confirming !== t.id && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={revoke.isPending}
                        onClick={() => setConfirming(t.id)}
                      >
                        Revoke
                      </Button>
                    )}
                    {!t.revoked_at && confirming === t.id && (
                      <span
                        className="flex items-center gap-2"
                        role="group"
                        aria-label={`Confirm revoking ${t.name}`}
                      >
                        <span className="text-xs text-muted">
                          Clients using it will stop working.
                        </span>
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={revoke.isPending}
                          onClick={() => {
                            revoke.mutate(t.id);
                            setConfirming(null);
                          }}
                        >
                          Confirm revoke
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                          Cancel
                        </Button>
                      </span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </SettingsShell>
  );
}
