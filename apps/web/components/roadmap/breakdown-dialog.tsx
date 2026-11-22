"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ListTree, Sparkles } from "lucide-react";
import { useId, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ErrorState, SkeletonLoader } from "@/components/ui/states";
import { TwinLabel } from "@/components/twin/twin-label";
import { api, unwrap } from "@/lib/api/client";
import { AcceptAll, SuggestionCards, useSuggestionsById } from "@/components/roadmap/suggestion-list";

/** ProposedStory.similar is untyped; shape from ml/effort.py. */
type Similar = { key: string; title: string; actual_days: number };

function SuggestionsBlock({ ids }: { ids: string[] }) {
  const qs = useSuggestionsById(ids);
  const loaded = qs.flatMap((q) => (q.data ? [q.data] : []));
  return (
    <section aria-labelledby="bd-sugg" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="bd-sugg" className="text-sm font-semibold">Create these stories</h3>
        <AcceptAll items={loaded} label="Create all" />
      </div>
      <SuggestionCards ids={ids} />
    </section>
  );
}

export function BreakdownDialog() {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [epicId, setEpicId] = useState("");
  const [text, setText] = useState("");
  const epics = useQuery({ queryKey: ["epics"], queryFn: async () => unwrap(await api.GET("/api/v1/epics")), enabled: open });
  const run = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/planning/breakdown", { body: { epic_id: epicId || null, text: text.trim() || null } })),
  });
  const data = run.data;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <ListTree /> Break down an epic
        </Button>
      </DialogTrigger>
      <DialogContent
        title="Epic breakdown"
        description="The twin proposes stories with estimates from similar past work. Nothing is created until you accept."
        className="w-[min(880px,94vw)]"
      >
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            run.mutate();
          }}
        >
          <div className="space-y-1">
            <Label htmlFor={`${id}-epic`}>Epic</Label>
            <Select id={`${id}-epic`} className="w-full" value={epicId} onChange={(e) => setEpicId(e.target.value)}>
              <option value="">{epics.isLoading ? "Loading epics…" : "Choose an epic"}</option>
              {epics.data?.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.key} · {e.title}
                </option>
              ))}
            </Select>
            {epics.isError && <p role="alert" className="text-xs text-danger">{(epics.error as Error).message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-text`}>Extra context (optional)</Label>
            <Textarea id={`${id}-text`} rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Constraints, scope notes, or a pasted brief" />
          </div>
          <Button type="submit" variant="accent" disabled={(!epicId && !text.trim()) || run.isPending}>
            <Sparkles /> {run.isPending ? "Breaking down…" : "Propose stories"}
          </Button>
        </form>
        <div className="mt-5 space-y-5" aria-live="polite">
          {run.isPending && <SkeletonLoader rows={6} className="p-0" />}
          {run.isError && <ErrorState error={run.error} onRetry={() => run.mutate()} />}
          {data && data.stories.length === 0 && <p className="text-sm text-muted">No stories proposed. Add more context and try again.</p>}
          {data && data.stories.length > 0 && (
            <section aria-labelledby="bd-stories" className="space-y-3">
              <div className="flex items-center gap-2">
                <h3 id="bd-stories" className="text-sm font-semibold">Proposed stories ({data.stories.length})</h3>
                <TwinLabel />
              </div>
              {data.stories.map((s, i) => (
                <Card key={i} className="space-y-2 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h4 className="text-sm font-medium">{s.title}</h4>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone="neutral">{s.type}</Badge>
                      <Badge tone="accent">{s.story_points} pts</Badge>
                      <Badge tone="neutral" aria-label={`Estimate ${s.estimate_days} days, 80 percent interval ${s.p10_days} to ${s.p90_days} days`}>
                        {s.estimate_days}d <span className="opacity-80">(80%: {s.p10_days}–{s.p90_days}d)</span>
                      </Badge>
                    </div>
                  </div>
                  {s.description && <p className="text-xs text-muted">{s.description}</p>}
                  {s.acceptance_criteria.length > 0 && (
                    <div>
                      <p className="text-xs font-medium">Acceptance criteria</p>
                      <ul className="ml-4 list-disc text-xs">
                        {s.acceptance_criteria.map((a, j) => (
                          <li key={j}>{a}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {s.similar.length > 0 && (
                    <div>
                      <p className="text-xs font-medium">Similar past items</p>
                      <ul className="text-xs text-muted">
                        {(s.similar as unknown as Similar[]).map((x) => (
                          <li key={x.key}>
                            <span className="font-mono">{x.key}</span> {x.title} · took {x.actual_days}d
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Card>
              ))}
            </section>
          )}
          {data && data.suggestion_ids.length > 0 && <SuggestionsBlock ids={data.suggestion_ids} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
