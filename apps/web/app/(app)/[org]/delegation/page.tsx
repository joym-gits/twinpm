"use client";

import { useQuery } from "@tanstack/react-query";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { AtRiskItems } from "@/components/delegation/candidates";
import { Nudges } from "@/components/delegation/nudges";
import { RebalancePanel } from "@/components/delegation/rebalance";
import { DistributionMonitor, TeamColumns, WorkloadHeatmap } from "@/components/delegation/workload";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, Skeleton, SkeletonLoader } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { useMe, useProgramId } from "@/lib/auth/use-me";

function Workload({ programId }: { programId: string }) {
  const q = useQuery({
    queryKey: ["workload", programId],
    queryFn: async () => unwrap(await api.GET("/api/v1/delegation/workload", { params: { query: { program_id: programId } } })),
  });
  if (q.isLoading)
    return (
      <Card className="p-5">
        <Skeleton className="h-64" />
      </Card>
    );
  if (q.isError || !q.data)
    return (
      <Card>
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Card>
    );
  return (
    <>
      <WorkloadHeatmap data={q.data} />
      <TeamColumns data={q.data} />
      <DistributionMonitor data={q.data} />
    </>
  );
}

export default function DelegationPage() {
  const me = useMe();
  const programId = useProgramId();
  if (me.isLoading) return <SkeletonLoader rows={6} />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Delegation Board"
        description="See who is stretched, who fits each at-risk item, and approve the twin's rebalancing moves."
      />
      <Suspense fallback={<Card><SkeletonLoader rows={4} /></Card>}>
        <RebalancePanel programId={programId} />
      </Suspense>
      <Workload programId={programId} />
      <AtRiskItems programId={programId} />
      <Nudges programId={programId} />
    </div>
  );
}
