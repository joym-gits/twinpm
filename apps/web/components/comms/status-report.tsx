"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Hash, Send, Sparkles, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { TwinLabel } from "@/components/twin/twin-label";
import { api, unwrap } from "@/lib/api/client";
import { streamSse } from "@/lib/api/sse";
import { relTime } from "@/lib/format";
import { useRespond } from "@/lib/hooks/use-suggestions";

const CHANNEL = "#checkout-2-0";
const AUDIENCES = [
  { value: "executive", label: "Executive" },
  { value: "engineering", label: "Engineering" },
  { value: "customer", label: "Customer" },
] as const;
type Audience = (typeof AUDIENCES)[number]["value"];
const PERIODS = ["this week", "last two weeks", "this month"];
const RAG_TONE = { red: "danger", amber: "warning", green: "success" } as const;

function RagBadge({ text }: { text: string }) {
  const rag = /Status:\s*\**\s*(Red|Amber|Green)/i.exec(text)?.[1]?.toLowerCase() as keyof typeof RAG_TONE | undefined;
  if (!rag) return null;
  return <Badge tone={RAG_TONE[rag]}>Status: {rag.charAt(0).toUpperCase() + rag.slice(1)}</Badge>;
}

/** `/comms/channel-feed` is an untyped list in the contract; shape mirrors ChatMessageDTO. */
interface ChannelMessage {
  channel: string;
  text: string;
  ts: string;
  user: string | null;
}

function ChannelFeed() {
  const q = useQuery({
    queryKey: ["channel-feed", CHANNEL],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/comms/channel-feed", { params: { query: { channel: CHANNEL } } })) as unknown as ChannelMessage[],
  });
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-1">
            <Hash className="size-4 text-muted" aria-hidden />
            {CHANNEL.slice(1)}
          </CardTitle>
          <CardDescription>Mock Slack channel. Approved reports post here.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {q.isLoading && <SkeletonLoader rows={4} className="p-0" />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.length === 0 && <EmptyState title="No messages yet" description="Approve a status report to post it here." />}
        <ol className="space-y-3" aria-label={`Messages in ${CHANNEL}`}>
          {q.data?.map((m) => (
            <li key={m.ts} className="rounded-lg border border-border p-3">
              <p className="text-xs">
                <span className="font-semibold">{m.user ?? "Unknown"}</span>{" "}
                <span className="text-muted">{relTime(new Date(Number(m.ts) * 1000).toISOString())}</span>
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm">{m.text}</p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

export function StatusReport({ programId, twinName }: { programId: string; twinName: string }) {
  const [audience, setAudience] = useState<Audience>("executive");
  const [period, setPeriod] = useState("this week");
  const [draft, setDraft] = useState("");
  const [original, setOriginal] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [citations, setCitations] = useState<CitationLike[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [suggestionId, setSuggestionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const respond = useRespond();

  useEffect(() => () => abort.current?.abort(), []);

  const suggestion = useQuery({
    queryKey: ["suggestion", suggestionId],
    enabled: !!suggestionId,
    queryFn: async () => unwrap(await api.GET("/api/v1/suggestions/{suggestion_id}", { params: { path: { suggestion_id: suggestionId! } } })),
  });

  async function generate() {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setDraft("");
    setOriginal(null);
    setCitations([]);
    setWarnings([]);
    setSuggestionId(null);
    setError(null);
    respond.reset();
    setStreaming(true);
    let text = "";
    try {
      await streamSse(
        "/api/v1/comms/status-report",
        { program_id: programId, audience, period },
        (ev) => {
          if (ev.event === "token") {
            text += String(ev.data.text ?? "");
            setDraft(text);
          } else if (ev.event === "citation") setCitations((c) => [...c, ev.data as unknown as CitationLike]);
          else if (ev.event === "suggestion_created") setSuggestionId(String(ev.data.id));
          else if (ev.event === "done") {
            const final = typeof ev.data.text === "string" ? ev.data.text : text;
            setDraft(final);
            setOriginal(final);
            setWarnings((ev.data.warnings as string[]) ?? []);
          } else if (ev.event === "error") setError(String(ev.data.message ?? "Generation failed."));
        },
        ctrl.signal,
      );
    } catch (e) {
      if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setStreaming(false);
    }
  }

  const edited = original !== null && draft !== original;
  const s = suggestion.data;
  const sent = respond.isSuccess || (s && s.status !== "pending");

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Status report</CardTitle>
            <CardDescription>Written from live program data in your tone, for the audience you pick.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <span className="block text-xs font-medium text-muted" id="audience-l">
                Audience
              </span>
              <Tabs value={audience} onValueChange={(v) => setAudience(v as Audience)}>
                <TabsList aria-labelledby="audience-l">
                  {AUDIENCES.map((a) => (
                    <TabsTrigger key={a.value} value={a.value}>
                      {a.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            </div>
            <div className="space-y-1">
              <Label htmlFor="period">Period</Label>
              <Select id="period" value={period} onChange={(e) => setPeriod(e.target.value)} className="block">
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </Select>
            </div>
            <Button variant="accent" disabled={streaming} onClick={() => void generate()}>
              <Sparkles /> {streaming ? "Generating…" : "Generate"}
            </Button>
            {streaming && (
              <Button variant="ghost" onClick={() => abort.current?.abort()}>
                <Square /> Stop
              </Button>
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          {!draft && !streaming && !error && (
            <EmptyState title="No draft yet" description="Pick an audience and period, then generate a report to review before it is sent." />
          )}
          {(draft || streaming) && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="report-draft">Draft (editable)</Label>
                <div className="flex items-center gap-2">
                  <RagBadge text={draft} />
                  <TwinLabel who={twinName} />
                </div>
              </div>
              <Textarea
                id="report-draft"
                rows={16}
                value={draft}
                readOnly={streaming}
                aria-busy={streaming}
                onChange={(e) => setDraft(e.target.value)}
                className="leading-relaxed"
              />
              <p className="text-[11px] text-muted">Your edits teach the twin your style.{edited && " Edited."}</p>
              {warnings.length > 0 && (
                <ul className="space-y-0.5 text-xs text-warning" aria-label="Warnings">
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}
              <Citations items={citations} max={8} />
            </div>
          )}
          {suggestionId && !streaming && (
            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
              {suggestion.isLoading && <SkeletonLoader rows={1} className="w-48 p-0" />}
              {suggestion.isError && <ErrorState error={suggestion.error} onRetry={() => void suggestion.refetch()} />}
              {s && !sent && (
                <Button
                  variant="accent"
                  disabled={respond.isPending || !draft.trim()}
                  onClick={() =>
                    respond.mutate(edited ? { id: s.id, action: "edit", edited_payload: { body: draft } } : { id: s.id, action: "accept" })
                  }
                >
                  <Send /> {respond.isPending ? "Sending…" : "Approve & send"}
                </Button>
              )}
              {sent && (
                <p className="flex items-center gap-1 text-sm text-success" role="status">
                  <Check className="size-4" aria-hidden /> Sent to {CHANNEL}
                  {s && s.status !== "pending" && ` (${s.status.replace("_", " ")})`}
                </p>
              )}
              {respond.isError && (
                <p role="alert" className="text-sm text-danger">
                  {(respond.error as Error).message}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
      <ChannelFeed />
    </div>
  );
}
