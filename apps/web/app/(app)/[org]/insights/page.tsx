"use client";

import { AskMetrics } from "@/components/insights/ask-metrics";
import { AnomalyList, MetricExplorer } from "@/components/insights/metric-explorer";
import { TeamHealthPanel } from "@/components/insights/team-health";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, SkeletonLoader } from "@/components/ui/states";
import { useMe, useProgramId } from "@/lib/auth/use-me";

export default function InsightsPage() {
  const me = useMe();
  const programId = useProgramId();
  if (me.isLoading) return <SkeletonLoader rows={6} />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;
  return (
    <div className="space-y-6">
      <PageHeader title="Insights" description="Delivery metrics, anomalies and team health, with the reasoning behind every flag." />
      <MetricExplorer programId={programId} />
      <div className="grid gap-6 xl:grid-cols-2">
        <AskMetrics />
        <AnomalyList />
      </div>
      <TeamHealthPanel programId={programId} />
    </div>
  );
}
