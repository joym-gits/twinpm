"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CommandPalette } from "@/components/layout/command-palette";
import { Topbar } from "@/components/layout/topbar";
import { AskTwin } from "@/components/twin/ask-twin";
import { AuditDrawer, EntityPanel } from "@/components/twin/side-panels";
import { SkeletonLoader } from "@/components/ui/states";
import { ApiError } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { useLiveEvents } from "@/lib/hooks/use-live-events";
import { useUi } from "@/lib/store";

/** Client chrome around every app page: auth gate, shortcuts, palette, drawers, live events. */
export function AppChrome({ org, children }: { org: string; children: React.ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const live = useLiveEvents();
  const [palette, setPalette] = useState(false);
  const twinOpen = useUi((s) => s.twinOpen);
  const setTwinOpen = useUi((s) => s.setTwinOpen);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      } else if (e.key.toLowerCase() === "j") {
        e.preventDefault();
        setTwinOpen(!twinOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [twinOpen, setTwinOpen]);

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace(`/login?next=/${org}/command-center`);
    if (me.data && me.data.org.slug !== org) router.replace(`/${me.data.org.slug}/command-center`);
  }, [me.error, me.data, org, router]);

  if (!me.data) return <SkeletonLoader rows={8} className="p-8" />;
  return (
    <>
      <Topbar org={org} live={live} onPalette={() => setPalette(true)} />
      <main id="main" className="flex-1 p-6">
        {children}
      </main>
      <CommandPalette org={org} open={palette} setOpen={setPalette} />
      <AskTwin />
      <EntityPanel />
      <AuditDrawer />
    </>
  );
}
