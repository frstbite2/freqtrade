"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "./logo";
import { MOBILE_TABS, NAV, isActive } from "./nav";
import { NavList, PaperOnlyCard } from "./sidebar";

/** Below the lg breakpoint: a bottom tab bar for the main pages, and a slide-in menu for all. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const tabs = NAV.filter((n) => MOBILE_TABS.includes(n.href));

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-3 bottom-3 z-40 flex items-center justify-around rounded-2xl border border-line-strong bg-night/85 px-1 py-1.5 shadow-[0_20px_50px_-20px_rgb(0_0_0/0.9)] backdrop-blur-xl lg:hidden"
        style={{ paddingBottom: "max(0.375rem, env(safe-area-inset-bottom))" }}
      >
        {tabs.map(({ href, label, short, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex min-w-14 flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 text-[10px] font-medium transition-colors ${active ? "text-ink" : "text-ink-3"}`}
            >
              <span className={`flex size-8 items-center justify-center rounded-xl transition-all ${active ? "bg-gradient-to-br from-violet/40 to-ember/30 shadow-[0_0_18px_-2px_#a46bff]" : ""}`}>
                <Icon className="size-[18px]" />
              </span>
              {short ?? label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex min-w-14 flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 text-[10px] font-medium text-ink-3"
          aria-label="Open menu"
        >
          <span className="flex size-8 items-center justify-center rounded-xl">
            <Menu className="size-[18px]" />
          </span>
          More
        </button>
      </nav>

      <div
        className={`fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        aria-label="Menu"
        aria-hidden={!open}
        className={`fixed inset-y-0 left-0 z-50 flex w-[82%] max-w-xs flex-col gap-6 border-r border-line-strong bg-night/95 px-4 py-5 backdrop-blur-xl transition-transform duration-300 lg:hidden ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between px-1">
          <Logo />
          <button type="button" onClick={() => setOpen(false)} className="rounded-xl p-2 text-ink-3 hover:bg-white/5 hover:text-ink" aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <NavList onNavigate={() => setOpen(false)} />
        </div>
        <PaperOnlyCard />
      </aside>
    </>
  );
}
