"use client";

import { Slider as S } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Slider({
  className,
  label,
  ...props
}: React.ComponentProps<typeof S.Root> & { label: string }) {
  return (
    <S.Root className={cn("relative flex h-5 w-full touch-none items-center", className)} {...props}>
      <S.Track className="relative h-1.5 grow rounded-full bg-surface-2">
        <S.Range className="absolute h-full rounded-full bg-accent" />
      </S.Track>
      <S.Thumb
        aria-label={label}
        className="block size-4 rounded-full border-2 border-accent bg-surface shadow"
      />
    </S.Root>
  );
}
