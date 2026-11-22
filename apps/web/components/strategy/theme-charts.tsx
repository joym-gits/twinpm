"use client";

import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { ResponsiveContainer, Treemap, type TreemapNode } from "recharts";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export type Theme = Schemas["ThemeOut"];

export const BREAKDOWN_KEYS = ["volume", "growth", "severity", "segment_value", "strategic_fit"] as const;
type BreakdownKey = (typeof BREAKDOWN_KEYS)[number];
export const BREAKDOWN_LABEL: Record<BreakdownKey, string> = {
  volume: "Volume",
  growth: "Growth",
  severity: "Severity",
  segment_value: "Segment value",
  strategic_fit: "Strategic fit",
};

/** `ThemeOut.opportunity_score` is an untyped dict in the contract; this is the shape ml/themes.py writes. */
export interface Opportunity {
  score: number;
  breakdown: Partial<Record<BreakdownKey, number>>;
  weights: Partial<Record<BreakdownKey, number>>;
  quotes: string[];
  method?: string;
}

export function opportunity(t: Theme): Opportunity {
  const o = t.opportunity_score as Partial<Opportunity>;
  return { score: Number(o.score ?? 0), breakdown: o.breakdown ?? {}, weights: o.weights ?? {}, quotes: o.quotes ?? [], method: o.method };
}

/** Diverging scale: danger for negative sentiment, accent for positive, surface at neutral. */
export function sentimentFill(s: number): string {
  const amount = Math.round(15 + 45 * Math.min(1, Math.abs(s)));
  return `color-mix(in oklab, ${s < 0 ? "var(--color-danger)" : "var(--accent)"} ${amount}%, var(--surface))`;
}

export const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`;

export function sentimentWord(s: number): string {
  if (s <= -0.25) return "negative";
  if (s >= 0.25) return "positive";
  return "mixed";
}

export function ThemeTreemap({ themes, selectedId, onSelect }: { themes: Theme[]; selectedId?: string; onSelect: (id: string) => void }) {
  const data = themes.map((t) => ({ id: t.id, name: t.label, size: t.size, sentiment: t.avg_sentiment }));
  const tile = (n: TreemapNode) => {
    if (n.depth === 0) return <g />;
    const sentiment = Number(n.sentiment);
    const selected = n.id === selectedId;
    const roomy = n.width > 70 && n.height > 38;
    return (
      <g style={{ cursor: "pointer" }}>
        <rect
          x={n.x}
          y={n.y}
          width={n.width}
          height={n.height}
          rx={6}
          style={{ fill: sentimentFill(sentiment), stroke: selected ? "var(--text)" : "var(--surface)", strokeWidth: selected ? 3 : 2 }}
        />
        {roomy && (
          <>
            <text x={n.x + 8} y={n.y + 18} fontSize={12} fontWeight={600} style={{ fill: "var(--text)" }}>
              {n.name.length > n.width / 7 ? `${n.name.slice(0, Math.max(3, Math.floor(n.width / 7) - 1))}…` : n.name}
            </text>
            <text x={n.x + 8} y={n.y + 33} fontSize={11} style={{ fill: "var(--text)" }}>
              {String(n.size)} items · {signed(sentiment)}
            </text>
          </>
        )}
      </g>
    );
  };
  return (
    <div className="space-y-2">
      <div className="h-72" role="img" aria-label="Theme treemap: tile area is feedback volume, colour is average sentiment. The table below lists the same data.">
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={data}
            dataKey="size"
            nameKey="name"
            isAnimationActive={false}
            content={tile}
            onClick={(n) => typeof n.id === "string" && onSelect(n.id)}
          />
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-muted" aria-hidden>
        <span>Negative sentiment</span>
        <span className="h-2 w-32 rounded-full" style={{ background: `linear-gradient(to right, ${sentimentFill(-1)}, ${sentimentFill(0)}, ${sentimentFill(1)})` }} />
        <span>Positive</span>
        <span className="ml-auto">Area = volume</span>
      </div>
    </div>
  );
}

type SortKey = "label" | "score" | "size" | "avg_sentiment" | BreakdownKey;

function sortValue(t: Theme, k: SortKey): number | string {
  if (k === "label") return t.label.toLowerCase();
  if (k === "size" || k === "avg_sentiment") return t[k];
  if (k === "score") return opportunity(t).score;
  return opportunity(t).breakdown[k] ?? 0;
}

function MiniBar({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex items-center gap-1.5" title={`${label}: ${Math.round(value * 100)}%`}>
      <div className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-muted">{value.toFixed(2)}</span>
    </div>
  );
}

export function OpportunityTable({ themes, selectedId, onSelect }: { themes: Theme[]; selectedId?: string; onSelect: (id: string) => void }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "score", dir: -1 });
  const rows = useMemo(
    () =>
      [...themes].sort((a, b) => {
        const va = sortValue(a, sort.key);
        const vb = sortValue(b, sort.key);
        return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
      }),
    [themes, sort],
  );
  const weights = themes[0] ? opportunity(themes[0]).weights : {};
  const header = (key: SortKey, label: string, className?: string) => {
    const active = sort.key === key;
    const Icon = !active ? ArrowUpDown : sort.dir === 1 ? ArrowUp : ArrowDown;
    return (
      <TH key={key} className={className} aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button
          type="button"
          className="inline-flex items-center gap-1 whitespace-nowrap uppercase hover:text-text"
          onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : key === "label" ? 1 : -1 }))}
        >
          {label}
          <Icon className="size-3" aria-hidden />
        </button>
      </TH>
    );
  };
  return (
    <Table>
      <caption className="sr-only">Opportunity score per theme. Column headers sort the table; select a theme to see its detail.</caption>
      <THead>
        <TR>
          {header("label", "Theme")}
          {header("score", "Score")}
          {header("size", "Items")}
          {header("avg_sentiment", "Sentiment")}
          {BREAKDOWN_KEYS.map((k) => header(k, `${BREAKDOWN_LABEL[k]}${weights[k] ? ` ×${weights[k]}` : ""}`))}
        </TR>
      </THead>
      <TBody>
        {rows.map((t) => {
          const o = opportunity(t);
          const selected = t.id === selectedId;
          return (
            <TR key={t.id} className={cn(selected && "bg-accent/5")}>
              <TD>
                <button type="button" className="text-left font-medium hover:underline" aria-pressed={selected} onClick={() => onSelect(t.id)}>
                  {t.label}
                </button>
              </TD>
              <TD className="font-semibold tabular-nums">{o.score.toFixed(1)}</TD>
              <TD className="tabular-nums">{t.size}</TD>
              <TD>
                <span className="inline-flex items-center gap-1.5 text-xs tabular-nums">
                  <span className="size-2.5 rounded-sm border border-border" style={{ background: sentimentFill(t.avg_sentiment) }} aria-hidden />
                  {signed(t.avg_sentiment)} <span className="text-muted">{sentimentWord(t.avg_sentiment)}</span>
                </span>
              </TD>
              {BREAKDOWN_KEYS.map((k) => (
                <TD key={k}>
                  <MiniBar value={o.breakdown[k] ?? 0} label={BREAKDOWN_LABEL[k]} />
                </TD>
              ))}
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
