"use client";

import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Sheet = D.Root;
export const SheetTrigger = D.Trigger;

/** Right-side drawer. `modal={false}` keeps the page usable behind it. */
export function SheetContent({
  className,
  children,
  title,
  description,
  overlay = true,
  ...props
}: React.ComponentProps<typeof D.Content> & {
  title: string;
  description?: string;
  overlay?: boolean;
}) {
  return (
    <D.Portal>
      {overlay && <D.Overlay className="fixed inset-0 z-40 bg-navy-950/30" />}
      <D.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-[min(480px,100vw)] flex-col border-l border-border bg-surface shadow-2xl",
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <D.Title className="truncate text-sm font-semibold">{title}</D.Title>
            <D.Description className={description ? "mt-0.5 text-xs text-muted" : "sr-only"}>
              {description ?? title}
            </D.Description>
          </div>
          <D.Close className="rounded-md p-1 text-muted hover:bg-surface-2" aria-label="Close panel">
            <X className="size-4" />
          </D.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </D.Content>
    </D.Portal>
  );
}
