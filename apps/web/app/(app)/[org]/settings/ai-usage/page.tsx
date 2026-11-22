"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useState } from "react";
import { SettingsShell } from "@/components/settings/settings-nav";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, unwrap } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";

/** The endpoint is typed as a free-form dict; this mirrors the backend's admin.ai_usage response. */
interface Usage {
  calls: number;
  cost_usd: number;
  by_purpose: { purpose: string; model: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: number; avg_latency_ms: number; errors: number }[];
}

const usd = (v: number) => v.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const num = (v: number) => v.toLocaleString();

export default function AiUsagePage() {
  const me = useMe();
  const isAdmin = me.data?.permissions.includes("members:manage") ?? false;
  const [days, setDays] = useState(30);
  const q = useQuery({
    queryKey: ["ai-usage", days],
    enabled: isAdmin,
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/ai-usage", { params: { query: { days } } })) as unknown as Usage,
  });
  const d = q.data;
  const tokens = d?.by_purpose.reduce((n, r) => n + r.input_tokens + r.output_tokens, 0) ?? 0;
  return (
    <SettingsShell title="AI usage" description="Model calls, tokens and estimated cost by purpose." admin>
      {me.data?.demo_mode && (
        <div role="note" className="flex gap-2 rounded-lg border border-accent/30 bg-accent/5 p-3 text-xs">
          <Info className="size-4 shrink-0 text-accent" aria-hidden />
          <p>Demo mode is on: calls are served by the built-in &ldquo;demo&rdquo; model, so cost is always $0.</p>
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="usage-days">Period</Label>
        <Select id="usage-days" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </Select>
      </div>
      {q.isLoading && <SkeletonLoader rows={5} />}
      {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <dl className="grid gap-3 sm:grid-cols-3">
            <Card className="p-4">
              <dt className="text-xs text-muted">Calls</dt>
              <dd className="text-2xl font-semibold tabular-nums">{num(d.calls)}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-xs text-muted">Tokens</dt>
              <dd className="text-2xl font-semibold tabular-nums">{num(tokens)}</dd>
            </Card>
            <Card className="p-4">
              <dt className="text-xs text-muted">Estimated cost</dt>
              <dd className="text-2xl font-semibold tabular-nums">{usd(d.cost_usd)}</dd>
            </Card>
          </dl>
          <Card className="px-2">
            {d.by_purpose.length === 0 ? (
              <EmptyState title="No AI calls in this period" />
            ) : (
              <Table aria-label="AI usage by purpose" data-testid="ai-usage-table">
                <THead>
                  <TR>
                    <TH>Purpose</TH>
                    <TH>Model</TH>
                    <TH className="text-right">Calls</TH>
                    <TH className="text-right">Input tokens</TH>
                    <TH className="text-right">Output tokens</TH>
                    <TH className="text-right">Cost</TH>
                    <TH className="text-right">Avg latency</TH>
                    <TH className="text-right">Errors</TH>
                  </TR>
                </THead>
                <TBody>
                  {[...d.by_purpose]
                    .sort((a, b) => b.calls - a.calls)
                    .map((r) => (
                      <TR key={r.purpose + r.model}>
                        <TD>{r.purpose.replace(/_/g, " ")}</TD>
                        <TD className="font-mono text-xs">{r.model}</TD>
                        <TD className="text-right tabular-nums">{num(r.calls)}</TD>
                        <TD className="text-right tabular-nums">{num(r.input_tokens)}</TD>
                        <TD className="text-right tabular-nums">{num(r.output_tokens)}</TD>
                        <TD className="text-right tabular-nums">{usd(r.cost_usd)}</TD>
                        <TD className="text-right tabular-nums">{Math.round(r.avg_latency_ms)} ms</TD>
                        <TD className={`text-right tabular-nums ${r.errors ? "text-danger" : ""}`}>{r.errors}</TD>
                      </TR>
                    ))}
                </TBody>
              </Table>
            )}
          </Card>
        </>
      )}
    </SettingsShell>
  );
}
