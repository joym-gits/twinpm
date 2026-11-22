"use client";

import { PageHeader } from "@/components/layout/page-header";
import { AtRiskTable } from "@/components/risk/at-risk-table";
import { DependencyGraph } from "@/components/risk/dependency-graph";
import { RiskRegister } from "@/components/risk/risk-register";
import { EmptyState, SkeletonLoader } from "@/components/ui/states";
import { ModelCardDrawer } from "@/components/twin/model-card";
import { useMe, useProgramId } from "@/lib/auth/use-me";

export default function RiskRadarPage() {
  const me = useMe();
  const programId = useProgramId();
  if (me.isLoading) return <SkeletonLoader rows={6} />;
  if (!programId) return <EmptyState title="No program yet" description="Seed the demo or create a program to get started." />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Risk Radar"
        description="Where the program could slip, why the model thinks so, and what a slip would cascade into."
        actions={<ModelCardDrawer model="delay_risk" />}
      />
      <DependencyGraph programId={programId} />
      <AtRiskTable programId={programId} />
      <RiskRegister programId={programId} />
    </div>
  );
}
