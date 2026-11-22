"use client";

import { useMutation } from "@tanstack/react-query";
import { FileText, Scale, Square, Target } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { TwinLabel } from "@/components/twin/twin-label";
import { api, unwrap } from "@/lib/api/client";
import { streamSse } from "@/lib/api/sse";
import type { Theme } from "@/components/strategy/theme-charts";

/** These endpoints return untyped dicts in the contract; shapes mirror services/strategy.py. */
interface Critique {
  assumptions: string[];
  counter_arguments: string[];
  validation_experiments: string[];
  citations: CitationLike[];
}
interface Okrs {
  objectives: { objective: string; key_results: string[] }[];
  citations: CitationLike[];
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="space-y-1.5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </section>
  );
}

function DevilsAdvocate({ documentId, text, twinName }: { documentId: string | null; text: string; twinName: string }) {
  const critique = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/strategy/devils-advocate", {
          body: documentId ? { document_id: documentId } : { text },
        }),
      ) as unknown as Critique,
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Devil&apos;s advocate</CardTitle>
          <CardDescription>Challenges the draft in the editor: hidden assumptions, counter-arguments, cheap experiments.</CardDescription>
        </div>
        <Button size="sm" variant="outline" disabled={!text.trim() || critique.isPending} onClick={() => critique.mutate()}>
          <Scale /> {critique.isPending ? "Challenging…" : "Challenge this draft"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {!text.trim() && !critique.data && <p className="text-sm text-muted">Draft or paste a PRD in the editor first.</p>}
        {critique.isPending && <SkeletonLoader rows={4} className="p-0" />}
        {critique.isError && <ErrorState error={critique.error} onRetry={() => critique.mutate()} />}
        {critique.data && (
          <>
            <TwinLabel who={twinName} verb="Challenged by" />
            <List title="Assumptions" items={critique.data.assumptions} />
            <List title="Counter-arguments" items={critique.data.counter_arguments} />
            <List title="Validation experiments" items={critique.data.validation_experiments} />
            <Citations items={critique.data.citations ?? []} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function PrdStudio({ theme, twinName }: { theme?: Theme; twinName: string }) {
  const [idea, setIdea] = useState(theme?.label ?? "");
  const [draft, setDraft] = useState("");
  const [streamed, setStreamed] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [citations, setCitations] = useState<CitationLike[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => setIdea(theme?.label ?? ""), [theme?.id, theme?.label]);
  useEffect(() => () => abort.current?.abort(), []);

  async function run() {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setDraft("");
    setStreamed("");
    setDocumentId(null);
    setCitations([]);
    setWarnings([]);
    setError(null);
    setStreaming(true);
    let text = "";
    try {
      await streamSse(
        "/api/v1/strategy/prd",
        { idea, theme_id: theme?.id ?? null },
        (ev) => {
          if (ev.event === "token") {
            text += String(ev.data.text ?? "");
            setDraft(text);
          } else if (ev.event === "citation") setCitations((c) => [...c, ev.data as unknown as CitationLike]);
          else if (ev.event === "done") {
            setDocumentId((ev.data.document_id as string) ?? null);
            setWarnings((ev.data.warnings as string[]) ?? []);
            setStreamed(text);
          } else if (ev.event === "error") setError(String(ev.data.message ?? "The draft failed."));
        },
        ctrl.signal,
      );
    } catch (e) {
      if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "The draft failed.");
    } finally {
      setStreaming(false);
    }
  }

  // Critique the saved document only while the editor still matches it.
  const critiqueDoc = documentId && draft === streamed ? documentId : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Draft a PRD</CardTitle>
            <CardDescription>{theme ? `Grounded in the "${theme.label}" theme, its quotes and program objectives.` : "Describe the idea; select a theme to ground it in feedback."}</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run();
            }}
          >
            <div className="min-w-60 flex-1 space-y-1">
              <Label htmlFor="prd-idea">Idea</Label>
              <Input id="prd-idea" value={idea} onChange={(e) => setIdea(e.target.value)} minLength={3} maxLength={500} required />
            </div>
            <Button type="submit" variant="accent" disabled={streaming || idea.trim().length < 3}>
              <FileText /> {streaming ? "Drafting…" : theme ? "Draft PRD from this theme" : "Draft PRD"}
            </Button>
            {streaming && (
              <Button type="button" variant="ghost" onClick={() => abort.current?.abort()}>
                <Square /> Stop
              </Button>
            )}
          </form>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label htmlFor="prd-draft">PRD draft (markdown, editable)</Label>
              {(streaming || draft) && <TwinLabel who={twinName} />}
            </div>
            <Textarea
              id="prd-draft"
              rows={18}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              readOnly={streaming}
              aria-busy={streaming}
              className="font-mono text-xs leading-relaxed"
              placeholder="The streamed draft appears here. You can also paste your own PRD to challenge it."
            />
          </div>
          {warnings.length > 0 && (
            <ul className="space-y-0.5 text-xs text-warning" aria-label="Warnings">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          <Citations items={citations} max={8} />
          {documentId && <p className="text-xs text-muted">Saved as a PRD document.</p>}
        </CardContent>
      </Card>
      <DevilsAdvocate documentId={critiqueDoc} text={draft} twinName={twinName} />
    </div>
  );
}

export function OkrPanel({ programId, twinName }: { programId: string; twinName: string }) {
  const okrs = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/strategy/okrs/draft", { body: { program_id: programId } })) as unknown as Okrs,
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>OKR draft</CardTitle>
          <CardDescription>Objectives from the launch forecast and the top opportunity themes.</CardDescription>
        </div>
        <Button size="sm" variant="outline" disabled={okrs.isPending} onClick={() => okrs.mutate()}>
          <Target /> {okrs.isPending ? "Drafting…" : okrs.data ? "Redraft OKRs" : "Draft OKRs"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {okrs.isIdle && <EmptyState icon={Target} title="No OKRs drafted yet" description="Draft a starting set, then refine it with your team." action={{ label: "Draft OKRs", onClick: () => okrs.mutate() }} />}
        {okrs.isPending && <SkeletonLoader rows={4} className="p-0" />}
        {okrs.isError && <ErrorState error={okrs.error} onRetry={() => okrs.mutate()} />}
        {okrs.data && (
          <>
            <TwinLabel who={twinName} />
            <ol className="space-y-3">
              {okrs.data.objectives.map((o, i) => (
                <li key={o.objective} className="rounded-lg border border-border p-3">
                  <h3 className="text-sm font-medium">
                    O{i + 1}. {o.objective}
                  </h3>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-sm text-muted">
                    {o.key_results.map((kr) => (
                      <li key={kr}>{kr}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
            <Citations items={okrs.data.citations ?? []} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
