"use client";

import { create } from "zustand";

export interface EntityRef {
  type: string;
  id: string;
  label: string;
}

interface UiState {
  twinOpen: boolean;
  twinDraft: string | null;
  entity: EntityRef | null;
  audit: { entityType?: string; entityId?: string; suggestionId?: string; title: string } | null;
  pageContext: Record<string, unknown>;
  openTwin: (draft?: string) => void;
  setTwinOpen: (open: boolean) => void;
  openEntity: (e: EntityRef | null) => void;
  openAudit: (a: UiState["audit"]) => void;
  setPageContext: (ctx: Record<string, unknown>) => void;
}

/** UI-only state. Server state lives in TanStack Query. */
export const useUi = create<UiState>((set) => ({
  twinOpen: false,
  twinDraft: null,
  entity: null,
  audit: null,
  pageContext: {},
  openTwin: (draft) => set({ twinOpen: true, twinDraft: draft ?? null }),
  setTwinOpen: (open) => set({ twinOpen: open }),
  openEntity: (entity) => set({ entity }),
  openAudit: (audit) => set({ audit }),
  setPageContext: (pageContext) => set({ pageContext }),
}));
