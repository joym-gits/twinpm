"use client";

import { useMutation } from "@tanstack/react-query";
import { CalendarCheck } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { EmptyState, ErrorState, SkeletonLoader } from "@/components/ui/states";
import { Citations, type CitationLike } from "@/components/twin/citation-chip";
import { TwinLabel } from "@/components/twin/twin-label";
import { usePeople } from "@/components/comms/decision-log";
import { api, unwrap } from "@/lib/api/client";

/** `/comms/meeting-prep` returns an untyped dict in the contract; shape mirrors services/comms.py. */
interface Brief {
  purpose: string;
  context: string[];
  talking_points: string[];
  decisions_needed: string[];
  related_decisions: { title: string; chosen?: string; decided?: string }[];
  citations: CitationLike[];
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      <ul className="list-disc space-y-0.5 pl-5 text-sm">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </section>
  );
}

export function MeetingPrep({ programId, twinName }: { programId: string; twinName: string }) {
  const [title, setTitle] = useState("");
  const [attendees, setAttendees] = useState<string[]>([]);
  const people = usePeople();
  const prep = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/comms/meeting-prep", { body: { meeting_title: title, attendee_ids: attendees, program_id: programId } }),
      ) as unknown as Brief,
  });
  const toggle = (id: string) => setAttendees((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
  const b = prep.data;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Meeting prep</CardTitle>
            <CardDescription>A one-page brief: purpose, context, talking points per attendee and decisions to make.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              prep.mutate();
            }}
          >
            <div className="space-y-1">
              <Label htmlFor="meeting-title">Meeting title</Label>
              <Input id="meeting-title" value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} maxLength={200} required />
            </div>
            <fieldset className="space-y-1">
              <legend className="text-xs font-medium text-muted">
                Attendees <span className="font-normal">({attendees.length} selected, up to 20)</span>
              </legend>
              {people.isLoading && <SkeletonLoader rows={4} className="p-0" />}
              {people.isError && <ErrorState error={people.error} onRetry={() => void people.refetch()} />}
              {people.data?.length === 0 && <p className="text-sm text-muted">No people in this org yet.</p>}
              <div className="max-h-64 space-y-0.5 overflow-y-auto rounded-lg border border-border p-1">
                {people.data?.map((p) => {
                  const checked = attendees.includes(p.id);
                  return (
                    <label key={p.id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2">
                      <input
                        type="checkbox"
                        className="accent-[var(--accent)]"
                        checked={checked}
                        disabled={!checked && attendees.length >= 20}
                        onChange={() => toggle(p.id)}
                      />
                      <span>{p.name}</span>
                      <span className="truncate text-xs text-muted">{p.title}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <Button type="submit" variant="accent" disabled={prep.isPending || title.trim().length < 3}>
              <CalendarCheck /> {prep.isPending ? "Preparing…" : "Prepare brief"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        {prep.isIdle && <EmptyState icon={CalendarCheck} title="No brief yet" description="Name the meeting and pick who is coming." />}
        {prep.isPending && <SkeletonLoader rows={6} />}
        {prep.isError && <ErrorState error={prep.error} onRetry={() => prep.mutate()} />}
        {b && (
          <>
            <CardHeader>
              <div>
                <CardTitle>{title}</CardTitle>
                <TwinLabel who={twinName} verb="Prepared by" />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <section className="space-y-1">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Purpose</h3>
                <p className="text-sm">{b.purpose}</p>
              </section>
              <Section title="Context" items={b.context} />
              <Section title="Talking points" items={b.talking_points} />
              <Section title="Decisions needed" items={b.decisions_needed} />
              {b.related_decisions.length > 0 && (
                <Section title="Related decisions" items={b.related_decisions.map((d) => (d.chosen ? `${d.title}: ${d.chosen}` : d.title))} />
              )}
              <Citations items={b.citations ?? []} max={10} />
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
