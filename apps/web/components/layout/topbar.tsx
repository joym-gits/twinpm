"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, LogOut, Radio, Search, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { api, unwrap } from "@/lib/api/client";
import { useMe } from "@/lib/auth/use-me";
import { relTime } from "@/lib/format";
import { useUi } from "@/lib/store";

function Notifications() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => unwrap(await api.GET("/api/v1/notifications", { params: { query: { limit: 15 } } })),
  });
  const read = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.POST("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: id } } })),
    onSettled: () => void qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const unread = q.data?.filter((n) => !n.read_at).length ?? 0;
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications, ${unread} unread`} className="relative">
          <Bell />
          {unread > 0 && (
            <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
              {unread}
            </span>
          )}
        </Button>
      </MenuTrigger>
      <MenuContent className="w-80">
        <MenuLabel>Notifications</MenuLabel>
        {!q.data?.length && <p className="px-2 py-3 text-xs text-muted">You&apos;re all caught up.</p>}
        {q.data?.map((n) => (
          <MenuItem key={n.id} onSelect={() => !n.read_at && read.mutate(n.id)} className="items-start">
            <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-accent"}`} aria-hidden />
            <span className="min-w-0">
              <span className="block truncate text-sm">{n.title}</span>
              <span className="block truncate text-xs text-muted">
                {n.body} · {relTime(n.created_at)}
              </span>
            </span>
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

export function Topbar({ org, live, onPalette }: { org: string; live: boolean; onPalette: () => void }) {
  const me = useMe();
  const router = useRouter();
  const openTwin = useUi((s) => s.openTwin);
  const programs = useQuery({
    queryKey: ["programs"],
    queryFn: async () => unwrap(await api.GET("/api/v1/programs")),
  });
  const initials = (me.data?.user.name ?? "")
    .split(" ")
    .map((x) => x[0])
    .join("")
    .slice(0, 2);
  async function logout() {
    await api.POST("/api/v1/auth/logout");
    router.replace("/login");
  }
  return (
    <header className="flex h-14 items-center gap-3 border-b border-border bg-surface px-5">
      <label className="sr-only" htmlFor="program-switcher">
        Program
      </label>
      <select
        id="program-switcher"
        className="h-8 rounded-lg border border-border bg-surface px-2 text-sm font-medium"
        value={me.data?.default_program_id ?? ""}
        onChange={() => undefined}
      >
        {programs.data?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={onPalette}
        className="flex h-8 w-72 items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 text-sm text-muted hover:border-accent"
      >
        <Search className="size-4" aria-hidden /> Search or jump to…
        <span className="sr-only"> (Ctrl or Command plus K)</span>
        <kbd aria-hidden className="ml-auto rounded border border-border px-1 text-[10px]">⌘K</kbd>
      </button>
      <div className="ml-auto flex items-center gap-1">
        {me.data?.demo_mode && (
          <Badge tone="warning" title="No Anthropic key: deterministic demo responses from live data">
            Demo mode
          </Badge>
        )}
        <span className="flex items-center gap-1 px-2 text-[11px] text-muted" title={live ? "Live updates on" : "Reconnecting"}>
          <Radio className={`size-3 ${live ? "text-success" : "text-muted"}`} aria-hidden />
          {live ? "Live" : "Offline"}
        </span>
        <Button variant="outline" size="sm" onClick={() => openTwin()} aria-label="Ask the Twin (Ctrl or Command plus J)">
          <Sparkles /> Ask the Twin
        </Button>
        <Notifications />
        <ThemeToggle />
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="sm" aria-label={`${initials} user menu`}>
              <span className="grid size-7 place-items-center rounded-full bg-navy-900 text-xs font-semibold text-white">
                {initials}
              </span>
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuLabel>
              {me.data?.user.name} · {me.data?.user.role.replace("_", " ")}
            </MenuLabel>
            <MenuItem onSelect={() => router.push(`/${org}/settings`)}>Settings</MenuItem>
            <MenuSeparator />
            <MenuItem onSelect={() => void logout()}>
              <LogOut className="size-4" /> Sign out
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>
    </header>
  );
}
