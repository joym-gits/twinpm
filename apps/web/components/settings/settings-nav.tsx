"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, SkeletonLoader } from "@/components/ui/states";
import { useMe } from "@/lib/auth/use-me";
import { cn } from "@/lib/utils";

export const SETTINGS_PAGES = [
  { segment: "persona", label: "Persona" },
  { segment: "autonomy", label: "Autonomy" },
  { segment: "learning", label: "Twin learning" },
  { segment: "integrations", label: "Integrations" },
  { segment: "members", label: "Members & roles", admin: true },
  { segment: "ai-usage", label: "AI usage", admin: true },
  { segment: "api-tokens", label: "API tokens" },
] as const;

const ADMIN_PERM = "members:manage";

export function SettingsNav() {
  const { org } = useParams<{ org: string }>();
  const pathname = usePathname();
  const me = useMe();
  const isAdmin = me.data?.permissions.includes(ADMIN_PERM) ?? false;
  return (
    <nav aria-label="Settings sections" className="md:w-48 md:shrink-0">
      <ul className="flex gap-1 overflow-x-auto md:flex-col">
        {SETTINGS_PAGES.filter((p) => !("admin" in p) || isAdmin).map((p) => {
          const href = `/${org}/settings/${p.segment}`;
          const active = pathname === href;
          return (
            <li key={p.segment}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block whitespace-nowrap rounded-lg px-3 py-1.5 text-sm",
                  active ? "bg-surface-2 font-medium text-text" : "text-muted hover:bg-surface-2 hover:text-text",
                )}
              >
                {p.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Settings page frame: header, sub-nav and an admin gate for admin-only sections. */
export function SettingsShell({ title, description, admin = false, children }: { title: string; description?: string; admin?: boolean; children: React.ReactNode }) {
  const me = useMe();
  const allowed = !admin || (me.data?.permissions.includes(ADMIN_PERM) ?? false);
  return (
    <div>
      <PageHeader title="Settings" />
      <div className="flex flex-col gap-6 md:flex-row">
        <SettingsNav />
        <section aria-labelledby="settings-h" className="min-w-0 flex-1 space-y-4">
          <div>
            <h2 id="settings-h" className="text-base font-semibold">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {me.isLoading ? (
            <SkeletonLoader rows={4} />
          ) : allowed ? (
            children
          ) : (
            <EmptyState icon={Lock} title="Admins only" description="Ask an org admin for access to this section." />
          )}
        </section>
      </div>
    </div>
  );
}
