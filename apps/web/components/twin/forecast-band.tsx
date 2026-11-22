import { daysBetween, shortDate } from "@/lib/format";

/** P50 / P80 / P95 on a timeline against the target date. */
export function ForecastBand({
  p50,
  p80,
  p95,
  target,
  label,
}: {
  p50: string;
  p80: string;
  p95: string;
  target?: string | null;
  label?: string;
}) {
  const points = [p50, p80, p95, ...(target ? [target] : [])];
  const min = points.reduce((a, b) => (a < b ? a : b));
  const max = points.reduce((a, b) => (a > b ? a : b));
  const span = Math.max(daysBetween(min, max), 1);
  const pos = (d: string) => `${4 + (daysBetween(min, d) / span) * 92}%`;
  const late = target ? daysBetween(target, p80) : 0;
  return (
    <div aria-label={`${label ?? "Forecast"}: P50 ${shortDate(p50)}, P80 ${shortDate(p80)}, P95 ${shortDate(p95)}${target ? `, target ${shortDate(target)}` : ""}`}>
      {label && <p className="mb-1 text-xs font-medium text-muted">{label}</p>}
      <div className="relative h-10">
        <div className="absolute top-4 h-2 w-full rounded-full bg-surface-2" />
        <div
          className="absolute top-4 h-2 rounded-full bg-accent/30"
          style={{ left: pos(p50), width: `calc(${pos(p95)} - ${pos(p50)})` }}
        />
        {[
          ["P50", p50],
          ["P80", p80],
          ["P95", p95],
        ].map(([k, d]) => (
          <div key={k} className="absolute top-2.5 -translate-x-1/2 text-center" style={{ left: pos(d!) }}>
            <div className={k === "P80" ? "mx-auto h-5 w-1 rounded bg-accent" : "mx-auto h-5 w-0.5 rounded bg-accent/60"} />
          </div>
        ))}
        {target && (
          <div className="absolute top-0 -translate-x-1/2" style={{ left: pos(target) }}>
            <div className="mx-auto h-9 w-0.5 border-l-2 border-dashed border-text" />
          </div>
        )}
      </div>
      <div className="mt-1 grid grid-cols-4 gap-2 text-xs">
        <span>P50 <strong className="tabular-nums">{shortDate(p50)}</strong></span>
        <span>P80 <strong className="tabular-nums">{shortDate(p80)}</strong></span>
        <span>P95 <strong className="tabular-nums">{shortDate(p95)}</strong></span>
        {target && (
          <span className={late > 0 ? "text-danger" : "text-success"}>
            Target {shortDate(target)} {late > 0 ? `(+${late}d)` : "(on track)"}
          </span>
        )}
      </div>
    </div>
  );
}
