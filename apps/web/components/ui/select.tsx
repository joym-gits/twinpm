"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/** Native select: accessible, keyboard friendly, and themable. */
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "h-9 rounded-lg border border-border bg-surface px-3 pr-8 text-sm disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";
