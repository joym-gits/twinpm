import { Sparkles } from "lucide-react";

/** Responsible-AI label for anything the twin drafted or did. */
export function TwinLabel({ who = "Your twin", verb = "Drafted by" }: { who?: string; verb?: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-accent">
      <Sparkles className="size-3" aria-hidden />
      {verb} {who}
    </span>
  );
}
