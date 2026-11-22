import { cn } from "@/lib/utils";

export interface DriverLike {
  feature: string;
  label: string;
  contribution: number;
  value?: number | string | null;
}

/** SHAP-style factors as horizontal bars, largest first. */
export function DriverList({ drivers, className }: { drivers: DriverLike[]; className?: string }) {
  if (!drivers.length) return <p className="text-xs text-muted">No contributing factors recorded.</p>;
  const max = Math.max(...drivers.map((d) => Math.abs(d.contribution)), 1e-6);
  return (
    <ul className={cn("space-y-2", className)} aria-label="Contributing factors">
      {drivers.map((d) => {
        const width = `${Math.max(6, (Math.abs(d.contribution) / max) * 100)}%`;
        return (
          <li key={d.feature + d.label}>
            <div className="mb-0.5 flex justify-between gap-3 text-xs">
              <span>{d.label}</span>
              <span className="tabular-nums text-muted">+{d.contribution.toFixed(2)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-surface-2">
              <div className="h-1.5 rounded-full bg-warning" style={{ width }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
