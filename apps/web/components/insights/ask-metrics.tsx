"use client";

import { useMutation } from "@tanstack/react-query";
import { Sparkles, Wrench } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { Markdown } from "@/components/twin/markdown";
import { api, unwrap } from "@/lib/api/client";
import { useProgramId } from "@/lib/auth/use-me";
import { SeriesChart, type ChartSeries } from "./series-chart";

interface ChartSpec {
  type?: string;
  metric?: string;
  unit?: string;
  title?: string;
  series?: ChartSeries[];
}
interface ToolCall {
  tool?: string;
  args?: Record<string, unknown>;
}

export function AskMetrics() {
  const programId = useProgramId();
  const [question, setQuestion] = useState("");
  const ask = useMutation({
    mutationFn: async (q: string) => unwrap(await api.POST("/api/v1/insights/ask", { body: { question: q, program_id: programId ?? null } })),
  });
  const chart = (ask.data?.chart ?? {}) as ChartSpec;
  const series = chart.series ?? [];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Ask about your metrics</CardTitle>
          <CardDescription>Answers come from a parameterised metric query, never free-form SQL.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (question.trim()) ask.mutate(question.trim());
          }}
        >
          <div className="min-w-64 flex-1 space-y-1">
            <Label htmlFor="ask-q">Question</Label>
            <Input id="ask-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. How has Payments cycle time changed over the last 6 weeks?" maxLength={500} />
          </div>
          <Button type="submit" variant="accent" disabled={!question.trim() || ask.isPending}>
            <Sparkles /> {ask.isPending ? "Asking…" : "Ask"}
          </Button>
        </form>
        {ask.isPending && <Skeleton className="h-64" />}
        {ask.isError && <ErrorState error={ask.error} onRetry={() => ask.mutate(question.trim())} />}
        {ask.data && (
          <div className="space-y-3" aria-live="polite" data-testid="ask-answer">
            <Markdown text={ask.data.narrative} className="text-sm" />
            {series.some((s) => s.data.length) && <SeriesChart series={series} unit={chart.unit ? ` ${chart.unit}` : ""} label={chart.title ?? "Answer chart"} height={240} />}
            <Citations items={ask.data.citations as unknown as CitationLike[]} />
            {(ask.data.tool_calls as ToolCall[]).map((t, i) => (
              <details key={i} className="rounded-lg bg-surface-2 p-3 text-xs">
                <summary className="flex cursor-pointer items-center gap-1.5 font-medium">
                  <Wrench className="size-3.5" aria-hidden /> Used tool <code>{t.tool}</code>
                </summary>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-muted">{JSON.stringify(t.args ?? {}, null, 2)}</pre>
              </details>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
