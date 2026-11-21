"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/components/layout/nav";
import { cn } from "@/lib/utils";

export function Sidebar({ org }: { org: string }) {
  const pathname = usePathname();
  return (
    <aside className="flex w-60 shrink-0 flex-col bg-navy-900 text-navy-50" aria-label="Primary">
      <div className="flex h-14 items-center gap-2 px-5">
        <div className="grid size-7 place-items-center rounded-lg bg-teal-700 text-sm font-bold" aria-hidden>
          T
        </div>
        <span className="font-semibold tracking-tight">TwinPM</span>
      </div>
      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {NAV_ITEMS.map((item) => {
          const href = `/${org}/${item.segment}`;
          const active = pathname.startsWith(href);
          const Icon = item.icon;
          return (
            <Link
              key={item.segment}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active ? "bg-white/10 font-medium text-white" : "text-navy-100 hover:bg-white/5",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <p className="px-5 py-4 text-[11px] leading-snug text-navy-100/70">
        Runs your program the way you would, and shows its reasoning every time.
      </p>
    </aside>
  );
}
