import {
  Activity,
  Bot,
  Building2,
  FlaskConical,
  Landmark,
  LayoutDashboard,
  type LucideIcon,
  Settings,
  ShieldCheck,
  Wallet,
  Workflow,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  short?: string; // for the mobile tab bar
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/bots", label: "AI Bots", short: "Bots", icon: Bot },
  { href: "/markets", label: "Markets", icon: Activity },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/insider", label: "Insider Intelligence", icon: Landmark },
  { href: "/institutional", label: "Institutional Tracking", icon: Building2 },
  { href: "/strategies", label: "Strategies", icon: Workflow },
  { href: "/backtesting", label: "Backtesting", icon: FlaskConical },
  { href: "/risk", label: "Risk Management", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

/** The four destinations on the mobile tab bar; the rest live in the menu. */
export const MOBILE_TABS = ["/", "/bots", "/markets", "/portfolio"];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
