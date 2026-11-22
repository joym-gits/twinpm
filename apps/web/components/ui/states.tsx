import { AlertTriangle, Inbox } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
}: {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <Icon className="size-8 text-muted" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-xs text-muted">{description}</p>}
      {action && (
        <Button size="sm" variant="outline" className="mt-2" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-8 text-center">
      <AlertTriangle className="size-7 text-danger" aria-hidden />
      <p className="text-sm font-medium">Couldn&apos;t load this</p>
      <p className="max-w-sm text-xs text-muted">{message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-2", className)} aria-hidden />;
}

export function SkeletonLoader({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3 p-5", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn("h-4", i % 2 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}
