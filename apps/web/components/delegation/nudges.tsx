"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Hourglass, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import { api, unwrap } from "@/lib/api/client";
import { useSuggestions } from "@/lib/hooks/use-suggestions";

export function Nudges({ programId }: { programId: string }) {
  const qc = useQueryClient();
  const list = useSuggestions({ status: "pending", type: "nudge" });
  const run = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/delegation/nudges/run", { params: { query: { program_id: programId } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["suggestions"] }),
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Stalled items</CardTitle>
          <CardDescription>Friendly check-ins the twin drafted for work that stopped moving. Edit the message before sending if you like.</CardDescription>
        </div>
        <Button variant="outline" size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
          <Search /> {run.isPending ? "Looking…" : "Find stalled items"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div aria-live="polite">
          {run.data && (
            <p role="status" className="rounded-lg bg-surface-2 px-3 py-2 text-xs">
              Found <strong>{run.data.stalled}</strong> stalled item{run.data.stalled === 1 ? "" : "s"}, drafted{" "}
              <strong>{run.data.suggestions_created}</strong> nudge{run.data.suggestions_created === 1 ? "" : "s"}
              {run.data.auto_executed > 0 && <>, sent {run.data.auto_executed} automatically under your autonomy settings</>}.
            </p>
          )}
          {run.isError && <ErrorState error={run.error} onRetry={() => run.mutate()} />}
        </div>
        {list.isLoading && <SkeletonLoader rows={3} className="p-0" />}
        {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
        {list.data?.length === 0 && (
          <EmptyState
            icon={Hourglass}
            title="No nudges waiting"
            description="Scan for items with no movement and the twin will draft check-ins for you to approve."
            action={{ label: "Find stalled items", onClick: () => run.mutate() }}
          />
        )}
        {list.data?.map((s) => <SuggestionCard key={s.id} s={s} />)}
      </CardContent>
    </Card>
  );
}
