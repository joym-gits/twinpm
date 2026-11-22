"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { CitationChip } from "@/components/twin/citation-chip";
import { api, unwrap, type Schemas } from "@/lib/api/client";
import { cn, formatDate } from "@/lib/utils";

type Decision = Schemas["DecisionOut"];
/** DecisionOut.options is untyped in the contract; the seed and extractor write this shape. */
interface DecisionOption {
  name?: string;
  pros?: string;
  cons?: string;
}

export function usePeople() {
  return useQuery({ queryKey: ["people"], queryFn: async () => unwrap(await api.GET("/api/v1/people")) });
}

function SourceDoc({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ["document", id],
    queryFn: async () => unwrap(await api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
  });
  return <CitationChip c={{ type: "document", id, label: q.data?.title ?? "Source document" }} />;
}

function Detail({ d }: { d: Decision }) {
  const people = usePeople();
  const byId = new Map((people.data ?? []).map((p) => [p.id, p]));
  const options = d.options as DecisionOption[];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{d.title}</CardTitle>
          <CardDescription>Decided {formatDate(d.decided_at)}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {d.context && (
          <section className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Context</h3>
            <p className="whitespace-pre-wrap">{d.context}</p>
          </section>
        )}
        {options.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Options considered</h3>
            <ul className="grid gap-2 md:grid-cols-2">
              {options.map((o, i) => {
                const chosen = o.name === d.chosen_option;
                return (
                  <li key={o.name ?? i} className={cn("rounded-lg border p-3", chosen ? "border-accent" : "border-border")}>
                    <p className="flex items-center gap-2 font-medium">
                      {o.name ?? `Option ${i + 1}`}
                      {chosen && <Badge tone="accent">Chosen</Badge>}
                    </p>
                    {o.pros && (
                      <p className="mt-1 text-xs">
                        <span className="font-medium text-success">Pros:</span> {o.pros}
                      </p>
                    )}
                    {o.cons && (
                      <p className="mt-0.5 text-xs">
                        <span className="font-medium text-danger">Cons:</span> {o.cons}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <section className="space-y-1">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Chosen option</h3>
          <p className="font-medium">{d.chosen_option || "Not recorded"}</p>
        </section>
        {d.rationale && (
          <section className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Rationale</h3>
            <p className="whitespace-pre-wrap">{d.rationale}</p>
          </section>
        )}
        <section className="space-y-1">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Participants</h3>
          {people.isError ? (
            <ErrorState error={people.error} onRetry={() => void people.refetch()} />
          ) : d.participants.length === 0 ? (
            <p className="text-muted">None recorded</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {d.participants.map((id) => {
                const p = byId.get(id);
                return (
                  <li key={id}>
                    <Badge>{p ? `${p.name}, ${p.title}` : people.isLoading ? "Loading…" : "Unknown person"}</Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        {d.source_document_id && (
          <section className="space-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Source</h3>
            <SourceDoc id={d.source_document_id} />
          </section>
        )}
      </CardContent>
    </Card>
  );
}

export function DecisionLog({ onSelect }: { onSelect?: (d: Decision | undefined) => void }) {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  useEffect(() => {
    const t = setTimeout(() => setQ(input.trim()), 250);
    return () => clearTimeout(t);
  }, [input]);
  const list = useQuery({
    queryKey: ["decisions", q],
    queryFn: async () => unwrap(await api.GET("/api/v1/decisions", { params: { query: { q: q || null } } })),
  });
  const selected = list.data?.find((d) => d.id === selectedId) ?? list.data?.[0];
  useEffect(() => onSelect?.(selected), [selected, onSelect]);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <Card>
        <CardHeader>
          <div className="w-full space-y-1">
            <Label htmlFor="decision-q">Search decisions</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <Input id="decision-q" type="search" className="pl-8" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Kafka, rollout, pricing…" />
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-2">
          {list.isLoading && <SkeletonLoader rows={5} />}
          {list.isError && <ErrorState error={list.error} onRetry={() => void list.refetch()} />}
          {list.data?.length === 0 && (
            <EmptyState
              title={q ? "No decisions match" : "No decisions logged yet"}
              description={q ? "Try a different word." : "Extract decisions from a meeting transcript to start the log."}
              action={q ? { label: "Clear search", onClick: () => setInput("") } : undefined}
            />
          )}
          <ul className="space-y-1" aria-label="Decisions">
            {list.data?.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  aria-current={d.id === selected?.id}
                  onClick={() => setSelectedId(d.id)}
                  className={cn("w-full rounded-lg px-3 py-2 text-left hover:bg-surface-2", d.id === selected?.id && "bg-surface-2")}
                >
                  <span className="block text-sm font-medium">{d.title}</span>
                  <span className="text-xs text-muted">
                    {formatDate(d.decided_at)}
                    {d.chosen_option && ` · ${d.chosen_option}`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      {selected ? <Detail d={selected} /> : !list.isLoading && !list.isError && <Card><EmptyState title="Select a decision" /></Card>}
    </div>
  );
}
