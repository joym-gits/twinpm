"use client";

import { useQueries } from "@tanstack/react-query";
import { CheckCheck } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/states";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import { api, unwrap } from "@/lib/api/client";
import { useRespond, type Suggestion } from "@/lib/hooks/use-suggestions";

/**
 * Fetch suggestions by id. Keyed under "suggestion" (singular) on purpose: useRespond's optimistic
 * update maps over every ["suggestions", …] query and expects arrays there.
 */
export function useSuggestionsById(ids: string[]) {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: ["suggestion", id],
      queryFn: async () =>
        unwrap(await api.GET("/api/v1/suggestions/{suggestion_id}", { params: { path: { suggestion_id: id } } })),
    })),
  });
}

/** Accept every pending suggestion, one at a time so the server sees them in order. */
export function AcceptAll({ items, label = "Accept all" }: { items: Suggestion[]; label?: string }) {
  const respond = useRespond();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = items.filter((s) => s.status === "pending");
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      for (const s of pending) await respond.mutateAsync({ id: s.id, action: "accept" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Some approvals failed.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="accent" disabled={busy || pending.length === 0} onClick={() => void run()}>
        <CheckCheck /> {busy ? "Approving…" : `${label} (${pending.length})`}
      </Button>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** One SuggestionCard per id, with loading placeholders. */
export function SuggestionCards({ ids, twinName }: { ids: string[]; twinName?: string }) {
  const qs = useSuggestionsById(ids);
  return (
    <div className="space-y-3">
      {qs.map((q, i) =>
        q.data ? (
          <SuggestionCard key={ids[i]} s={q.data} twinName={twinName} compact />
        ) : q.isError ? (
          <p key={ids[i]} role="alert" className="text-xs text-danger">
            Couldn&apos;t load suggestion: {(q.error as Error).message}
          </p>
        ) : (
          <Skeleton key={ids[i]} className="h-24" />
        ),
      )}
    </div>
  );
}
