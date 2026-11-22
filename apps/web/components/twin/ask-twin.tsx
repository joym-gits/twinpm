"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ChevronRight, Loader2, Send, Sparkles, Wrench } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { Markdown } from "@/components/twin/markdown";
import { SuggestionCard } from "@/components/twin/suggestion-card";
import { TwinLabel } from "@/components/twin/twin-label";
import { api, unwrap } from "@/lib/api/client";
import { streamSse } from "@/lib/api/sse";
import { useMe } from "@/lib/auth/use-me";
import { useUi } from "@/lib/store";

interface TraceStep {
  kind: "agent" | "tool" | "result";
  label: string;
  detail?: string;
}

interface Turn {
  role: "user" | "assistant";
  text: string;
  trace: TraceStep[];
  citations: CitationLike[];
  approvalIds: string[];
  streaming?: boolean;
  error?: string;
}

const SUGGESTED = [
  "What should I do?",
  "What is the biggest risk to the launch?",
  "Why did we choose Kafka over SQS?",
  "Who is overloaded right now?",
];

function ApprovalList({ ids, twinName }: { ids: string[]; twinName: string }) {
  const q = useQuery({
    queryKey: ["suggestions", "by-ids", ids],
    enabled: ids.length > 0,
    queryFn: async () => Promise.all(ids.map(async (id) => unwrap(await api.GET("/api/v1/suggestions/{suggestion_id}", { params: { path: { suggestion_id: id } } })))),
  });
  if (!q.data) return null;
  return (
    <div className="space-y-2" aria-label="Actions waiting for approval">
      <p className="text-xs font-medium text-warning">{q.data.filter((s) => s.status === "pending").length} waiting for your approval</p>
      {q.data.map((s) => (
        <SuggestionCard key={s.id} s={s} twinName={twinName} compact />
      ))}
    </div>
  );
}

export function AskTwin() {
  const open = useUi((s) => s.twinOpen);
  const setOpen = useUi((s) => s.setTwinOpen);
  const draft = useUi((s) => s.twinDraft);
  const pageContext = useUi((s) => s.pageContext);
  const entity = useUi((s) => s.entity);
  const pathname = usePathname();
  const me = useMe();
  const qc = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const twinName = `${me.data?.user.name.split(" ")[0] ?? "Your"}'s twin`;

  useEffect(() => {
    if (draft) setInput(draft);
  }, [draft]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const ensureConversation = useCallback(async () => {
    if (conversationId) return conversationId;
    const c = unwrap(
      await api.POST("/api/v1/chat/conversations", { body: { program_id: me.data?.default_program_id ?? null, title: null } }),
    );
    setConversationId(c.id);
    return c.id;
  }, [conversationId, me.data?.default_program_id]);

  const update = (fn: (t: Turn) => Turn) =>
    setTurns((prev) => {
      const next = [...prev];
      next[next.length - 1] = fn(next[next.length - 1]!);
      return next;
    });

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    setInput("");
    setTurns((t) => [
      ...t,
      { role: "user", text: content, trace: [], citations: [], approvalIds: [] },
      { role: "assistant", text: "", trace: [], citations: [], approvalIds: [], streaming: true },
    ]);
    try {
      const id = await ensureConversation();
      const ctx = { page: pathname, ...pageContext, ...(entity ? { selected: entity } : {}) };
      await streamSse(`/api/v1/chat/conversations/${id}/messages`, { content, page_context: ctx }, (ev) => {
        const d = ev.data as Record<string, unknown>;
        switch (ev.event) {
          case "agent_started":
            update((t) => ({ ...t, trace: [...t.trace, { kind: "agent", label: String(d.agent) }] }));
            break;
          case "tool_call":
            update((t) => ({ ...t, trace: [...t.trace, { kind: "tool", label: String(d.tool) }] }));
            break;
          case "tool_result":
            update((t) => ({ ...t, trace: [...t.trace, { kind: "result", label: String(d.tool), detail: String(d.summary) }] }));
            break;
          case "token":
            update((t) => ({ ...t, text: t.text + String(d.text) }));
            break;
          case "citation":
            update((t) => ({ ...t, citations: [...t.citations, d as unknown as CitationLike] }));
            break;
          case "approval_required":
            update((t) => ({ ...t, approvalIds: (d.suggestion_ids as string[]) ?? [] }));
            break;
          case "done":
            update((t) => ({ ...t, streaming: false, text: t.text || String(d.text ?? "") }));
            break;
          case "error":
            update((t) => ({ ...t, streaming: false, error: String(d.message ?? "Something went wrong") }));
            break;
        }
      });
    } catch (e) {
      update((t) => ({ ...t, streaming: false, error: (e as Error).message }));
    } finally {
      update((t) => ({ ...t, streaming: false }));
      setBusy(false);
      void qc.invalidateQueries({ queryKey: ["suggestions"] });
    }
  }

  // Follow-up messages (e.g. after approvals resume the graph) arrive via live events.
  const convo = useQuery({
    queryKey: ["conversation", conversationId],
    enabled: !!conversationId && !busy,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/chat/conversations/{conversation_id}", { params: { path: { conversation_id: conversationId! } } })),
  });
  const serverAssistant = convo.data?.messages.filter((m) => m.role === "assistant") ?? [];
  const localAssistant = turns.filter((t) => t.role === "assistant").length;
  const followUps = serverAssistant.slice(localAssistant);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full bg-navy-900 px-4 py-3 text-sm font-medium text-white shadow-xl hover:bg-navy-800"
        aria-label="Ask the Twin (Ctrl or Command plus J)"
      >
        <Sparkles className="size-4" aria-hidden /> Ask the Twin
      </button>
      <Sheet open={open} onOpenChange={setOpen} modal={false}>
        <SheetContent
          overlay={false}
          title="Ask the Twin"
          description={`${twinName} · knows you're on ${pathname.split("/").at(-1)?.replace("-", " ")}`}
          className="w-[min(520px,100vw)]"
          onInteractOutside={(e) => e.preventDefault()}
        >
          <div className="flex h-full flex-col">
            <div className="flex-1 space-y-4 p-5" aria-live="polite">
              {turns.length === 0 && (
                <div className="space-y-3">
                  <p className="text-sm text-muted">Ask about risks, options, people or comms. Every answer cites its sources.</p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED.map((s) => (
                      <Button key={s} size="sm" variant="outline" onClick={() => void send(s)}>
                        {s}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((t, i) =>
                t.role === "user" ? (
                  <div key={i} className="ml-10 rounded-xl bg-navy-900 px-3 py-2 text-sm text-white">
                    {t.text}
                  </div>
                ) : (
                  <div key={i} className="space-y-3" data-testid="twin-answer">
                    {t.trace.length > 0 && (
                      <details open={t.streaming} className="rounded-lg border border-border bg-surface-2 p-2 text-xs">
                        <summary className="cursor-pointer font-medium">
                          Agent trace: {t.trace.filter((s) => s.kind === "agent").map((s) => s.label).join(" → ")}
                        </summary>
                        <ol className="mt-2 space-y-1" data-testid="agent-trace">
                          {t.trace.map((s, j) => (
                            <li key={j} className="flex items-center gap-1.5">
                              {s.kind === "agent" ? (
                                <Bot className="size-3.5 text-accent" aria-hidden />
                              ) : s.kind === "tool" ? (
                                <Wrench className="size-3.5 text-muted" aria-hidden />
                              ) : (
                                <ChevronRight className="size-3.5 text-muted" aria-hidden />
                              )}
                              <span className={s.kind === "agent" ? "font-semibold capitalize" : ""}>{s.label}</span>
                              {s.detail && <span className="truncate text-muted">{s.detail}</span>}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                    {t.text && <Markdown text={t.text} />}
                    {t.streaming && !t.text && (
                      <p className="flex items-center gap-2 text-sm text-muted">
                        <Loader2 className="size-4 animate-spin" aria-hidden /> Thinking…
                      </p>
                    )}
                    {t.error && (
                      <p className="text-sm text-danger" role="alert">
                        {t.error}
                      </p>
                    )}
                    {!t.streaming && t.text && <TwinLabel who={twinName} verb="Answered by" />}
                    <Citations items={t.citations} max={10} />
                    {t.approvalIds.length > 0 && <ApprovalList ids={t.approvalIds} twinName={twinName} />}
                  </div>
                ),
              )}
              {followUps.map((m) => (
                <div key={m.id} className="space-y-2">
                  <Markdown text={m.content} />
                  <TwinLabel who={twinName} verb="Update from" />
                </div>
              ))}
              <div ref={bottom} />
            </div>
            <form
              className="border-t border-border p-3"
              onSubmit={(e) => {
                e.preventDefault();
                void send(input);
              }}
            >
              <label htmlFor="twin-input" className="sr-only">
                Message the twin
              </label>
              <div className="flex gap-2">
                <Textarea
                  id="twin-input"
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                  placeholder="Ask anything about the program…"
                  disabled={busy}
                />
                <Button type="submit" variant="accent" size="icon" disabled={busy || !input.trim()} aria-label="Send">
                  {busy ? <Loader2 className="animate-spin" /> : <Send />}
                </Button>
              </div>
            </form>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
