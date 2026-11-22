"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { NAV_ITEMS } from "@/components/layout/nav";
import { api, unwrap } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { useUi } from "@/lib/store";

export function CommandPalette({ org, open, setOpen }: { org: string; open: boolean; setOpen: (o: boolean) => void }) {
  const router = useRouter();
  const openTwin = useUi((s) => s.openTwin);
  const openEntity = useUi((s) => s.openEntity);
  const [search, setSearch] = useState("");
  const me = useMe();
  const qc = useQueryClient();
  const canReset =
    !!me.data &&
    me.data.org.slug === "novapay" &&
    (me.data.permissions.includes("admin") || (me.data.demo_mode && me.data.user.role === "tpm"));
  async function resetDemo() {
    await api.POST("/api/v1/admin/reset-demo");
    await qc.invalidateQueries();
    router.push(`/${org}/command-center`);
  }
  const items = useQuery({
    queryKey: ["palette-items"],
    enabled: open,
    queryFn: async () => unwrap(await api.GET("/api/v1/work-items", { params: { query: { open_only: true } } })),
  });
  const epics = useQuery({ queryKey: ["epics"], enabled: open, queryFn: async () => unwrap(await api.GET("/api/v1/epics")) });
  const people = useQuery({ queryKey: ["people"], enabled: open, queryFn: async () => unwrap(await api.GET("/api/v1/people")) });
  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);
  const go = (fn: () => void) => {
    setOpen(false);
    fn();
  };
  const item = "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm aria-selected:bg-surface-2";
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent title="Command palette" description="Navigate, find entities or run actions" className="p-4">
        <Command label="Command palette" className="space-y-2">
          <Command.Input
            value={search}
            onValueChange={setSearch}
            autoFocus
            placeholder="Type a page, work item, epic, person or action…"
            className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm"
          />
          <Command.List className="max-h-80 overflow-y-auto">
            <Command.Empty className="px-2 py-4 text-sm text-muted">No results.</Command.Empty>
            <Command.Group heading="Actions" className="text-xs text-muted">
              <Command.Item className={item} onSelect={() => go(() => openTwin("What should I do?"))}>
                Ask the Twin: What should I do?
              </Command.Item>
              <Command.Item className={item} onSelect={() => go(() => router.push(`/${org}/delegation?rebalance=1`))}>
                Rebalance workload
              </Command.Item>
              <Command.Item className={item} onSelect={() => go(() => router.push(`/${org}/comms`))}>
                Draft an executive update
              </Command.Item>
              <Command.Item className={item} onSelect={() => go(() => router.push(`/${org}/risk`))}>
                Simulate a slip
              </Command.Item>
              {canReset && search.toLowerCase().includes("reset") && (
                <Command.Item className={item} onSelect={() => go(() => void resetDemo())}>
                  Reset demo data (re-seed NovaPay)
                </Command.Item>
              )}
            </Command.Group>
            <Command.Group heading="Pages" className="text-xs text-muted">
              {NAV_ITEMS.map((n) => (
                <Command.Item key={n.segment} className={item} onSelect={() => go(() => router.push(`/${org}/${n.segment}`))}>
                  <n.icon className="size-4" /> {n.label}
                </Command.Item>
              ))}
            </Command.Group>
            {search.length > 1 && (
              <>
                <Command.Group heading="Epics" className="text-xs text-muted">
                  {epics.data?.map((e) => (
                    <Command.Item key={e.id} value={`${e.key} ${e.title}`} className={item} onSelect={() => go(() => openEntity({ type: "epic", id: e.id, label: e.title }))}>
                      {e.title}
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="Work items" className="text-xs text-muted">
                  {items.data?.slice(0, 200).map((w) => (
                    <Command.Item key={w.id} value={`${w.key} ${w.title}`} className={item} onSelect={() => go(() => openEntity({ type: "work_item", id: w.id, label: w.key }))}>
                      <span className="font-mono text-xs">{w.key}</span> {w.title}
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="People" className="text-xs text-muted">
                  {people.data?.map((p) => (
                    <Command.Item key={p.id} value={p.name} className={item} onSelect={() => go(() => openEntity({ type: "person", id: p.id, label: p.name }))}>
                      {p.name} <span className="text-xs text-muted">{p.title}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              </>
            )}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
