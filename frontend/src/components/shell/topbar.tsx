"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useState } from "react";
import { BackendStatus } from "./backend-status";
import { DataModeToggle } from "./data-mode-toggle";
import { LogoMark } from "./logo";
import { NotificationCenter } from "./notification-center";

export function Topbar() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-void/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <div className="lg:hidden">
          <LogoMark size={30} />
        </div>
        <form
          role="search"
          className="relative hidden max-w-md flex-1 md:block"
          onSubmit={(e) => {
            e.preventDefault();
            router.push(`/markets${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);
          }}
        >
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tokens and stocks…"
            aria-label="Search tokens and stocks"
            className="h-10 w-full rounded-xl border border-line bg-white/[0.04] pl-10 pr-4 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-violet/50 focus:bg-white/[0.06] focus:outline-none"
          />
        </form>
        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <BackendStatus />
          <DataModeToggle />
          <NotificationCenter />
        </div>
      </div>
    </header>
  );
}
