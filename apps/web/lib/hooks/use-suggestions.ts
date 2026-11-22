"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/lib/api/client";

export type Suggestion = Schemas["SuggestionOut"];

export function useSuggestions(params: { status?: string; type?: string } = { status: "pending" }) {
  return useQuery({
    queryKey: ["suggestions", params],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/suggestions", { params: { query: { ...params, limit: 50 } } })),
  });
}

interface RespondVars {
  id: string;
  action: "accept" | "reject" | "edit";
  edited_payload?: Record<string, unknown>;
  reason?: string;
}

/** Respond with an optimistic status flip; server state reconciles on settle. */
export function useRespond() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: RespondVars) =>
      unwrap(
        await api.POST("/api/v1/suggestions/{suggestion_id}/respond", {
          params: { path: { suggestion_id: v.id } },
          body: { action: v.action, edited_payload: v.edited_payload ?? null, reason: v.reason ?? null },
        }),
      ),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ["suggestions"] });
      const snapshots = qc.getQueriesData<Suggestion[]>({ queryKey: ["suggestions"] });
      const status = v.action === "reject" ? "rejected" : v.action === "edit" ? "edited" : "accepted";
      for (const [key, data] of snapshots) {
        if (data) qc.setQueryData(key, data.map((s) => (s.id === v.id ? { ...s, status } : s)));
      }
      return { snapshots };
    },
    onError: (_e, _v, ctx) => {
      for (const [key, data] of ctx?.snapshots ?? []) qc.setQueryData(key, data);
    },
    onSettled: () => void qc.invalidateQueries(),
  });
}

export function useUndo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.POST("/api/v1/suggestions/{suggestion_id}/undo", { params: { path: { suggestion_id: id } } })),
    onSettled: () => void qc.invalidateQueries(),
  });
}
