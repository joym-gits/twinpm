"use client";

import { FileText } from "lucide-react";
import { useUi } from "@/lib/store";

export interface CitationLike {
  type: string;
  id: string;
  label: string;
}

export function CitationChip({ c }: { c: CitationLike }) {
  const openEntity = useUi((s) => s.openEntity);
  return (
    <button
      type="button"
      onClick={() => openEntity(c)}
      className="inline-flex max-w-56 items-center gap-1 truncate rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-muted hover:border-accent hover:text-accent"
      aria-label={`Open source: ${c.type.replace("_", " ")} ${c.label}`}
    >
      <FileText className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{c.label}</span>
    </button>
  );
}

export function Citations({ items, max = 6 }: { items: CitationLike[]; max?: number }) {
  const seen = new Set<string>();
  const unique = items.filter((c) => (seen.has(c.type + c.id) ? false : (seen.add(c.type + c.id), true)));
  if (!unique.length) return null;
  return (
    <div className="flex flex-wrap gap-1" aria-label="Sources">
      {unique.slice(0, max).map((c) => (
        <CitationChip key={c.type + c.id} c={c} />
      ))}
      {unique.length > max && <span className="text-[11px] text-muted">+{unique.length - max} more</span>}
    </div>
  );
}
