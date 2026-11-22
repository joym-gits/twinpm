"use client";

import { PageHeader } from "@/components/layout/page-header";
import { BreakdownDialog } from "@/components/roadmap/breakdown-dialog";
import { RoadmapBoard } from "@/components/roadmap/roadmap-board";
import { Simulator } from "@/components/roadmap/simulator";
import { EmptyState, SkeletonLoader } from "@/components/ui/states";
import { useMe, useProgramId } from "@/lib/auth/use-me";

export default function RoadmapPage() {
  const me = useMe();
  const programId = useProgramId();
  if (me.isLoading) return <SkeletonLoader rows={6} />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;
  return (
    <div className="space-y-8">
      <PageHeader
        title="Roadmap"
        description="Prioritise initiatives, test what-ifs against the forecast, and break epics into estimated stories."
        actions={<BreakdownDialog />}
      />
      <RoadmapBoard programId={programId} />
      <Simulator programId={programId} />
    </div>
  );
}
