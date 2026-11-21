import {
  Activity,
  BarChart3,
  Compass,
  LayoutDashboard,
  Map,
  MessageSquareText,
  Radar,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  segment: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Command Center", segment: "command-center", icon: LayoutDashboard },
  { label: "Strategy", segment: "strategy", icon: Compass },
  { label: "Roadmap", segment: "roadmap", icon: Map },
  { label: "Delegation", segment: "delegation", icon: Users },
  { label: "Risk Radar", segment: "risk", icon: Radar },
  { label: "Comms Studio", segment: "comms", icon: MessageSquareText },
  { label: "Insights", segment: "insights", icon: BarChart3 },
  { label: "Settings", segment: "settings", icon: Settings },
];

export const TWIN_ICON = Activity;
