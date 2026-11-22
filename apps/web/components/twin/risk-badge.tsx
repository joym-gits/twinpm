import { Badge } from "@/components/ui/badge";
import { riskLevel } from "@/lib/format";

const TONE = { Low: "success", Medium: "warning", High: "danger", Critical: "danger" } as const;
const MARK = { Low: "○", Medium: "◐", High: "●", Critical: "▲" } as const;

/** Delay probability 0–1 as a labelled level. Shape and text carry meaning, not just colour. */
export function RiskBadge({ probability, showValue = true }: { probability: number; showValue?: boolean }) {
  const level = riskLevel(probability);
  return (
    <Badge tone={TONE[level]} aria-label={`${level} risk, ${Math.round(probability * 100)} percent`}>
      <span aria-hidden>{MARK[level]}</span>
      {level}
      {showValue && <span className="tabular-nums opacity-80">{Math.round(probability * 100)}%</span>}
    </Badge>
  );
}
