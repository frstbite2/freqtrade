"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { Logo } from "./logo";
import { NAV, isActive } from "./nav";

export function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
              active ? "bg-gradient-to-r from-violet/20 to-transparent text-ink" : "text-ink-3 hover:bg-white/5 hover:text-ink"
            }`}
          >
            {active && (
              <span className="absolute inset-y-2 left-0 w-1 rounded-full bg-gradient-to-b from-ember to-violet shadow-[0_0_12px_#a46bff]" />
            )}
            <Icon className={`size-[18px] shrink-0 transition-colors ${active ? "text-violet" : "group-hover:text-ink-2"}`} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function PaperOnlyCard() {
  return (
    <div className="card glow-ring overflow-hidden p-4" style={{ ["--g1" as string]: "#36e3a1", ["--g2" as string]: "#38c8ff" }}>
      <div className="flex items-center gap-2 text-sm font-semibold text-ink">
        <ShieldCheck className="size-4 text-mint" aria-hidden />
        Paper trading only
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-3">
        Simulated balances. No real orders, deposits or withdrawals. A connected Phantom wallet is view-only.
      </p>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col gap-8 border-r border-line bg-night/60 px-4 py-6 backdrop-blur-xl lg:flex">
      <div className="px-2">
        <Logo />
      </div>
      <div className="-mx-1 flex-1 overflow-y-auto px-1">
        <NavList />
      </div>
      <PaperOnlyCard />
    </aside>
  );
}
