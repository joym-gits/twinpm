import { cn } from "@/lib/utils";

export function healthTone(score: number): { label: string; color: string; text: string } {
  if (score >= 80) return { label: "Healthy", color: "var(--color-success)", text: "text-success" };
  if (score >= 60) return { label: "At risk", color: "var(--color-warning)", text: "text-warning" };
  return { label: "Critical", color: "var(--color-danger)", text: "text-danger" };
}

/** Semi-circular gauge for a 0–100 health score with an optional 7-day delta. */
export function HealthGauge({
  score,
  delta,
  size = 200,
}: {
  score: number;
  delta?: number | null;
  size?: number;
}) {
  const r = 80;
  const c = Math.PI * r;
  const filled = Math.max(0, Math.min(100, score)) / 100;
  const tone = healthTone(score);
  return (
    <figure className="flex flex-col items-center" aria-label={`Program health ${Math.round(score)} out of 100, ${tone.label}`}>
      <svg width={size} height={size * 0.6} viewBox="0 0 200 120" role="img" aria-hidden>
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--surface-2)" strokeWidth="16" strokeLinecap="round" />
        <path
          d="M20 100 A80 80 0 0 1 180 100"
          fill="none"
          stroke={tone.color}
          strokeWidth="16"
          strokeLinecap="round"
          strokeDasharray={`${c * filled} ${c}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
        <text x="100" y="92" textAnchor="middle" className="fill-[var(--text)]" fontSize="38" fontWeight="700">
          {Math.round(score)}
        </text>
      </svg>
      <figcaption className="-mt-1 flex items-center gap-2 text-sm">
        <span className={cn("font-medium", tone.text)}>{tone.label}</span>
        {delta !== undefined && delta !== null && (
          <span className={cn("tabular-nums", delta < 0 ? "text-danger" : "text-success")}>
            {delta < 0 ? "↓" : "↑"}
            {Math.abs(Math.round(delta))} this week
          </span>
        )}
      </figcaption>
    </figure>
  );
}
