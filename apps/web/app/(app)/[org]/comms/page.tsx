"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { DecisionLog } from "@/components/comms/decision-log";
import { Extractor } from "@/components/comms/extractor";
import { MeetingPrep } from "@/components/comms/meeting-prep";
import { StatusReport } from "@/components/comms/status-report";
import { EmptyState, Skeleton } from "@/components/ui/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Schemas } from "@/lib/api/client";
import { useMe, useProgramId } from "@/lib/auth/use-me";
import { useUi } from "@/lib/store";

const TOOLS = [
  { value: "status", label: "Status report" },
  { value: "extract", label: "Transcript extractor" },
  { value: "decisions", label: "Decision log" },
  { value: "prep", label: "Meeting prep" },
] as const;

export default function CommsPage() {
  const me = useMe();
  const programId = useProgramId();
  const twinName = `${me.data?.user.name.split(" ")[0] ?? "Your"}'s twin`;
  const [tool, setTool] = useState<string>("status");
  const [decision, setDecision] = useState<Schemas["DecisionOut"]>();
  const setPageContext = useUi((s) => s.setPageContext);
  const onSelectDecision = useCallback((d: Schemas["DecisionOut"] | undefined) => setDecision(d), []);

  useEffect(() => {
    setPageContext({
      screen: "comms",
      tool,
      ...(tool === "decisions" && decision && { decision: { id: decision.id, title: decision.title } }),
    });
  }, [tool, decision, setPageContext]);

  if (me.isLoading) return <Skeleton className="h-96" />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;

  return (
    <div className="space-y-6">
      <PageHeader title="Comms Studio" description="Status reports, meeting outcomes and decisions, drafted by your twin and approved by you." />
      <Tabs value={tool} onValueChange={setTool} className="space-y-6">
        <TabsList aria-label="Comms tools" className="flex-wrap">
          {TOOLS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="status" forceMount className="data-[state=inactive]:hidden">
          <StatusReport programId={programId} twinName={twinName} />
        </TabsContent>
        <TabsContent value="extract" forceMount className="data-[state=inactive]:hidden">
          <Extractor programId={programId} twinName={twinName} />
        </TabsContent>
        <TabsContent value="decisions" forceMount className="data-[state=inactive]:hidden">
          <DecisionLog onSelect={onSelectDecision} />
        </TabsContent>
        <TabsContent value="prep" forceMount className="data-[state=inactive]:hidden">
          <MeetingPrep programId={programId} twinName={twinName} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
