"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { SkeletonLoader } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { relTime } from "@/lib/format";

export function ModelCardDrawer({ model = "delay_risk" }: { model?: string }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["model-cards"],
    enabled: open,
    queryFn: async () => unwrap(await api.GET("/api/v1/ml/models")),
  });
  const card = q.data?.find((c) => c.name === model) as Record<string, unknown> | undefined;
  const metrics = (card?.metrics ?? {}) as Record<string, number>;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FlaskConical /> Model card
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent title="Model card" description={model.replace("_", " ")}>
          {q.isLoading && <SkeletonLoader rows={8} />}
          {card && (
            <div className="space-y-4 p-5 text-sm">
              <p>{String(card.purpose)}</p>
              <p className="text-xs text-muted">{String(card.algorithm)}</p>
              <dl className="grid grid-cols-2 gap-2">
                {Object.entries(metrics).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-surface-2 p-2">
                    <dt className="text-[11px] text-muted">{k.replace(/_/g, " ")}</dt>
                    <dd className="font-semibold tabular-nums">{typeof v === "number" ? v : String(v)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-muted">
                Version {String(card.version)} · trained {relTime(String(card.trained_at))} · split {String(card.split)} ·
                data hash {String(card.training_data_hash)}
              </p>
              <div>
                <p className="mb-1 text-xs font-medium">Features</p>
                <div className="flex flex-wrap gap-1">
                  {(card.features as string[]).map((f) => (
                    <span key={f} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">
                      {f}
                    </span>
                  ))}
                </div>
              </div>
              <p className="text-xs text-muted">Synthetic training data. See docs/ML.md for limitations.</p>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
