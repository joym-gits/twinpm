"use client";

import { Tabs as T } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;

export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return (
    <T.List
      className={cn("inline-flex gap-1 rounded-lg bg-surface-2 p-1 text-sm", className)}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "rounded-md px-3 py-1.5 text-muted transition-colors data-[state=active]:bg-surface data-[state=active]:font-medium data-[state=active]:text-text data-[state=active]:shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export const TabsContent = T.Content;
