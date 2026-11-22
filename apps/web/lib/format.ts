export type RiskLevel = "Low" | "Medium" | "High" | "Critical";

export function riskLevel(p: number): RiskLevel {
  if (p >= 0.8) return "Critical";
  if (p >= 0.6) return "High";
  if (p >= 0.35) return "Medium";
  return "Low";
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function daysBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000);
}

export function relTime(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;
