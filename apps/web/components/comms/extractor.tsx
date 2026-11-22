"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, Check, ScanText } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, Skeleton, SkeletonLoader } from "@/components/ui/states";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { pct, shortDate } from "@/lib/format";

function Confidence({ value }: { value: number }) {
  return <Badge tone={value >= 0.75 ? "success" : value >= 0.5 ? "warning" : "neutral"}>{pct(value)} confidence</Badge>;
}

function DecisionRow({ d, programId }: { d: Schemas["ExtractedDecision"]; programId: string }) {
  const qc = useQueryClient();
  const log = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/decisions", {
          body: { program_id: programId, title: d.title, chosen_option: d.chosen_option, rationale: d.rationale, context: d.quote },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["decisions"] }),
  });
  return (
    <li className="space-y-1.5 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="text-sm font-medium">{d.title}</h4>
        <Confidence value={d.confidence} />
      </div>
      {d.chosen_option && (
        <p className="text-sm">
          <span className="text-muted">Chosen:</span> {d.chosen_option}
        </p>
      )}
      {d.rationale && <p className="text-sm text-muted">{d.rationale}</p>}
      {d.quote && <blockquote className="border-l-2 border-accent pl-3 text-xs italic">{d.quote}</blockquote>}
      <div className="flex items-center gap-2 pt-1">
        {log.isSuccess ? (
          <span className="flex items-center gap-1 text-xs text-success" role="status">
            <Check className="size-3.5" aria-hidden /> Logged to decision log
          </span>
        ) : (
          <Button size="sm" variant="outline" disabled={log.isPending} onClick={() => log.mutate()}>
            <BookmarkPlus /> {log.isPending ? "Logging…" : "Log decision"}
          </Button>
        )}
        {log.isError && (
          <span role="alert" className="text-xs text-danger">
            {(log.error as Error).message}
          </span>
        )}
      </div>
    </li>
  );
}

function TaskSuggestions({ ids, twinName }: { ids: string[]; twinName: string }) {
  const qs = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["suggestion", id],
      queryFn: async () => unwrap(await api.GET("/api/v1/suggestions/{suggestion_id}", { params: { path: { suggestion_id: id } } })),
    })),
  });
  if (!ids.length) return null;
  return (
    <section aria-labelledby="tasks-h" className="space-y-2">
      <h3 id="tasks-h" className="text-sm font-semibold">
        Proposed tasks <span className="font-normal text-muted">(approve to create them)</span>
      </h3>
      {qs.map((q, i) =>
        q.isLoading ? (
          <Card key={ids[i]} className="p-4">
            <Skeleton className="h-16" />
          </Card>
        ) : q.isError || !q.data ? (
          <Card key={ids[i]}>
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          </Card>
        ) : (
          <SuggestionCard key={ids[i]} s={q.data} twinName={twinName} />
        ),
      )}
    </section>
  );
}

export function Extractor({ programId, twinName }: { programId: string; twinName: string }) {
  const [documentId, setDocumentId] = useState("");
  const [text, setText] = useState("");
  const docs = useQuery({
    queryKey: ["documents", "transcripts"],
    queryFn: async () => {
      const [t, n] = await Promise.all([
        api.GET("/api/v1/documents", { params: { query: { type: "transcript" } } }).then(unwrap),
        api.GET("/api/v1/documents", { params: { query: { type: "meeting_notes" } } }).then(unwrap),
      ]);
      return [...t, ...n].sort((a, b) => (b.occurred_at ?? b.created_at).localeCompare(a.occurred_at ?? a.created_at));
    },
  });
  const extract = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/comms/extract", { body: documentId ? { document_id: documentId } : { transcript_text: text } })),
  });
  const r = extract.data;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Transcript extractor</CardTitle>
            <CardDescription>Pull decisions and action items out of a meeting. Action items become task suggestions for you to approve.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              extract.mutate();
            }}
          >
            <div className="space-y-1">
              <Label htmlFor="doc-pick">Meeting document</Label>
              {docs.isError ? (
                <ErrorState error={docs.error} onRetry={() => void docs.refetch()} />
              ) : (
                <Select id="doc-pick" className="block w-full" value={documentId} disabled={docs.isLoading} onChange={(e) => setDocumentId(e.target.value)}>
                  <option value="">{docs.isLoading ? "Loading documents…" : docs.data?.length ? "Paste a transcript instead" : "No transcripts or notes found"}</option>
                  {docs.data?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title} ({d.type.replace("_", " ")}, {shortDate(d.occurred_at ?? d.created_at)})
                    </option>
                  ))}
                </Select>
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="transcript">Transcript text</Label>
              <Textarea
                id="transcript"
                rows={12}
                maxLength={50000}
                value={text}
                disabled={!!documentId}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste a meeting transcript, or pick a document above."
              />
            </div>
            <Button type="submit" variant="accent" disabled={extract.isPending || (!documentId && !text.trim())}>
              <ScanText /> {extract.isPending ? "Extracting…" : "Extract"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-6">
        {extract.isIdle && (
          <Card>
            <EmptyState icon={ScanText} title="Nothing extracted yet" description="Pick a meeting document or paste a transcript, then extract." />
          </Card>
        )}
        {extract.isPending && (
          <Card>
            <SkeletonLoader rows={6} />
          </Card>
        )}
        {extract.isError && (
          <Card>
            <ErrorState error={extract.error} onRetry={() => extract.mutate()} />
          </Card>
        )}
        {r && (
          <>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Decisions ({r.decisions.length})</CardTitle>
                  <CardDescription>Method: {r.method}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {r.decisions.length === 0 ? (
                  <p className="text-sm text-muted">No decisions found in this meeting.</p>
                ) : (
                  <ul className="space-y-3">
                    {r.decisions.map((d) => (
                      <DecisionRow key={d.title + d.quote} d={d} programId={programId} />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Action items ({r.action_items.length})</CardTitle>
              </CardHeader>
              <CardContent>
                {r.action_items.length === 0 ? (
                  <p className="text-sm text-muted">No action items found in this meeting.</p>
                ) : (
                  <ul className="space-y-2">
                    {r.action_items.map((a) => (
                      <li key={a.title + a.quote} className="rounded-lg border border-border p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="text-sm font-medium">{a.title}</p>
                          <Confidence value={a.confidence} />
                        </div>
                        <p className="mt-1 text-xs text-muted">
                          Owner: {a.owner_name ?? "Unassigned"} · Due: {a.due_date ? shortDate(a.due_date) : "No date"}
                        </p>
                        {a.quote && <blockquote className="mt-1.5 border-l-2 border-accent pl-3 text-xs italic">{a.quote}</blockquote>}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <TaskSuggestions ids={r.suggestion_ids ?? []} twinName={twinName} />
          </>
        )}
      </div>
    </div>
  );
}
