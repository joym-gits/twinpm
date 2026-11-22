import { AppChrome } from "@/components/layout/app-chrome";
import { Sidebar } from "@/components/layout/sidebar";

export default async function AppLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ org: string }>;
}) {
  const { org } = await params;
  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        Skip to content
      </a>
      <Sidebar org={org} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppChrome org={org}>{children}</AppChrome>
      </div>
    </div>
  );
}
