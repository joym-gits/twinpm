"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { shortDate } from "@/lib/format";

export const SERIES_COLORS = ["var(--accent)", "#2563eb", "#9333ea", "#ea580c", "#db2777", "#65a30d", "#ca8a04", "#0891b2"];

export interface ChartSeries {
  name: string;
  data: { date: string; value: number; anomaly: boolean }[];
}

/** Multi-series line chart. Anomalous points are drawn as triangles, so they don't rely on colour. */
export function SeriesChart({ series, unit = "", label, height = 280 }: { series: ChartSeries[]; unit?: string; label: string; height?: number }) {
  const rows = new Map<string, Record<string, string | number | boolean>>();
  series.forEach((s, i) => {
    for (const p of s.data) {
      const row = rows.get(p.date) ?? { date: p.date };
      row[`s${i}`] = p.value;
      row[`a${i}`] = p.anomaly;
      rows.set(p.date, row);
    }
  });
  const data = [...rows.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const anomalies = series.reduce((n, s) => n + s.data.filter((p) => p.anomaly).length, 0);
  return (
    <figure>
      <div style={{ height }} role="img" aria-label={`${label}. ${series.length} series, ${anomalies} anomalous points marked with triangles.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d) => shortDate(String(d))} fontSize={11} stroke="var(--muted)" minTickGap={24} />
            <YAxis fontSize={11} stroke="var(--muted)" tickFormatter={(v) => `${v}${unit}`} />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--text)" }}
              labelFormatter={(l) => shortDate(String(l))}
              formatter={(v, _n, item) => {
                const key = String(item.dataKey ?? "").slice(1);
                const flagged = (item.payload as Record<string, unknown>)[`a${key}`];
                return [`${Number(v).toFixed(1)}${unit}${flagged ? " ▲ anomaly" : ""}`, series[Number(key)]?.name ?? ""];
              }}
            />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {series.map((s, i) => {
              const color = SERIES_COLORS[i % SERIES_COLORS.length]!;
              return (
                <Line
                  key={s.name}
                  name={s.name}
                  dataKey={`s${i}`}
                  stroke={color}
                  strokeWidth={2}
                  connectNulls
                  isAnimationActive={false}
                  activeDot={{ r: 4 }}
                  dot={(p: { cx?: number; cy?: number; index?: number; payload?: Record<string, unknown> }) => {
                    const k = `${s.name}-${p.index}`;
                    if (!p.payload?.[`a${i}`] || p.cx == null || p.cy == null) return <g key={k} />;
                    const { cx, cy } = p;
                    return <path key={k} d={`M${cx},${cy - 7} L${cx + 6},${cy + 5} L${cx - 6},${cy + 5} Z`} fill="var(--color-danger)" stroke="var(--surface)" strokeWidth={1.5} />;
                  }}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 flex items-center gap-1.5 text-xs text-muted">
        <svg width="12" height="12" viewBox="-6 -7 12 12" aria-hidden>
          <path d="M0,-7 L6,5 L-6,5 Z" fill="var(--color-danger)" />
        </svg>
        Triangle = anomalous point
      </figcaption>
    </figure>
  );
}

export function AnomalyPoints({ series, unit = "" }: { series: ChartSeries[]; unit?: string }) {
  const pts = series.flatMap((s) => s.data.filter((p) => p.anomaly).map((p) => ({ ...p, name: s.name })));
  if (!pts.length) return <p className="text-xs text-muted">No anomalous points in this range.</p>;
  return (
    <ul className="space-y-1 text-xs" aria-label="Anomalous points">
      {pts.map((p) => (
        <li key={p.name + p.date} className="flex gap-2">
          <span aria-hidden className="text-danger">▲</span>
          <span className="tabular-nums">{shortDate(p.date)}</span>
          <span>{p.name}</span>
          <strong className="tabular-nums">
            {p.value.toFixed(1)}
            {unit}
          </strong>
        </li>
      ))}
    </ul>
  );
}
