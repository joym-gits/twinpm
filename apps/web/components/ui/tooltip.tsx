"use client";

import { Tooltip as T } from "radix-ui";
import * as React from "react";

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <T.Provider delayDuration={200}>
      <T.Root>
        <T.Trigger asChild>{children}</T.Trigger>
        <T.Portal>
          <T.Content
            side={side}
            sideOffset={6}
            className="z-50 max-w-xs rounded-lg bg-navy-900 px-3 py-2 text-xs text-white shadow-lg"
          >
            {content}
            <T.Arrow className="fill-navy-900" />
          </T.Content>
        </T.Portal>
      </T.Root>
    </T.Provider>
  );
}
