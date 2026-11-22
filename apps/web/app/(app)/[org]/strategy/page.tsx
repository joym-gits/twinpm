"use client";

import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
import { RefreshCw, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { OkrPanel, PrdStudio } from "@/components/strategy/prd-studio";
import { OpportunityTable, ThemeTreemap } from "@/components/strategy/theme-charts";
import { ThemeDetail } from "@/components/strategy/theme-detail";
import { ApiError, api, authFetch, unwrap } from "@/lib/api/client";
import { useMe, useProgramId } from "@/lib/auth/use-me";
import { useUi } from "@/lib/store";

async function importCsv(file: File): Promise<number> {
  const body = new FormData();
  body.append("file", file);
  const res = await authFetch(new Request("/api/v1/feedback/import", { method: "POST", body, credentials: "include" }));
  const json = (await res.json().catch(() => ({}))) as { imported?: number; error?: { code?: string; message?: string } };
  if (!res.ok) throw new ApiError(res.status, json.error?.code ?? `http_${res.status}`, json.error?.message ?? "Import failed");
  return json.imported ?? 0;
}

export default function StrategyPage() {
  const me = useMe();
  const programId = useProgramId();
  const twinName = `${me.data?.user.name.split(" ")[0] ?? "Your"}'s twin`;
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedId, setSelectedId] = useState<string>();

  const themes = useQuery({
    queryKey: ["themes"],
    queryFn: async () => unwrap(await api.GET("/api/v1/strategy/themes")),
  });
  const recompute = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/strategy/themes/recompute")),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["themes"] }),
  });
  const upload = useMutation({
    mutationFn: importCsv,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });

  const list = themes.data ?? [];
  const selected = list.find((t) => t.id === selectedId) ?? list[0];
  const setPageContext = useUi((s) => s.setPageContext);
  useEffect(() => {
    setPageContext({ screen: "strategy", ...(selected && { theme: { id: selected.id, label: selected.label } }) });
  }, [selected, setPageContext]);

  if (me.isLoading) return <Skeleton className="h-96" />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;

  const recomputeStatus = recompute.data as { status?: string } | undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Strategy"
        description="Customer feedback clustered into themes, scored transparently, and turned into PRDs and OKRs."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              aria-label="Feedback CSV file"
              tabIndex={-1}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button variant="outline" size="sm" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
              <Upload /> {upload.isPending ? "Importing…" : "Import feedback CSV"}
            </Button>
            <Button variant="outline" size="sm" disabled={recompute.isPending} onClick={() => recompute.mutate()}>
              <RefreshCw className={recompute.isPending ? "animate-spin" : ""} /> {recompute.isPending ? "Recomputing…" : "Recompute themes"}
            </Button>
          </>
        }
      />
      <div aria-live="polite" className="text-xs">
        {upload.isSuccess && <p className="text-success">Imported {upload.data} feedback items. Recompute themes to re-cluster them.</p>}
        {upload.isError && <p role="alert" className="text-danger">{(upload.error as Error).message}</p>}
        {recompute.isSuccess && (
          <p className="text-muted">{recomputeStatus?.status === "queued" ? "Re-clustering queued on the worker; themes refresh when it finishes." : "Themes recomputed."}</p>
        )}
        {recompute.isError && <p role="alert" className="text-danger">{(recompute.error as Error).message}</p>}
      </div>

      {themes.isLoading && <Card className="p-5"><Skeleton className="h-72" /></Card>}
      {themes.isError && <Card><ErrorState error={themes.error} onRetry={() => void themes.refetch()} /></Card>}
      {themes.isSuccess && list.length === 0 && (
        <Card>
          <EmptyState
            title="No themes yet"
            description="Import customer feedback as CSV, then recompute themes to cluster it."
            action={{ label: "Import feedback CSV", onClick: () => fileRef.current?.click() }}
          />
        </Card>
      )}

      {selected && (
        <>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Themes</CardTitle>
                  <CardDescription>Sized by feedback volume, coloured by average sentiment. Click a tile to select it.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <ThemeTreemap themes={list} selectedId={selected.id} onSelect={setSelectedId} />
              </CardContent>
            </Card>
            <ThemeDetail theme={selected} programId={programId} />
          </div>
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Opportunity scores</CardTitle>
                <CardDescription>Score = weighted sum of the breakdown (weights shown in headers) × 100.</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="px-2">
              <OpportunityTable themes={list} selectedId={selected.id} onSelect={setSelectedId} />
            </CardContent>
          </Card>
        </>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <PrdStudio theme={selected} twinName={twinName} />
        <OkrPanel programId={programId} twinName={twinName} />
      </div>
    </div>
  );
}
