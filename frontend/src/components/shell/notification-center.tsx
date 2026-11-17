"use client";

import { Bell, CheckCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { DemoBadge } from "@/components/ui/badges";
import { EmptyState } from "@/components/ui/states";
import { useDataMode } from "@/lib/data-mode";
import { utcTime } from "@/lib/format";
import { NOTIFICATIONS } from "@/lib/sample-data";

const TONE = { violet: "bg-violet", ember: "bg-ember", mint: "bg-mint", rose: "bg-rose" } as const;

export function NotificationCenter() {
  const { mode } = useDataMode();
  const [open, setOpen] = useState(false);
  const [read, setRead] = useState<Set<string>>(new Set());
  const panel = useRef<HTMLDivElement>(null);
  const items = mode === "demo" ? NOTIFICATIONS : [];
  const unread = items.filter((n) => !read.has(n.id)).length;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!panel.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div ref={panel} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative flex size-10 items-center justify-center rounded-xl border border-line bg-white/[0.03] text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
      >
        <Bell className="size-[18px]" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex size-5 items-center justify-center rounded-full bg-gradient-to-br from-ember to-flare text-[10px] font-bold text-white shadow-[0_0_12px_#ff5fa2]">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <div className="card absolute right-0 top-12 z-50 w-[min(22rem,calc(100vw-2rem))] animate-rise overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="font-display text-sm font-semibold">Notifications</span>
              {mode === "demo" && <DemoBadge />}
            </div>
            {unread > 0 && (
              <button type="button" onClick={() => setRead(new Set(items.map((n) => n.id)))} className="inline-flex items-center gap-1 text-xs text-ink-3 hover:text-ink">
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <EmptyState title="No notifications">Real alerts arrive here once signals and the risk monitor are connected (Stage 2 and 3).</EmptyState>
          ) : (
            <ul className="max-h-96 divide-y divide-line overflow-y-auto">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => setRead((r) => new Set(r).add(n.id))}
                    className={`flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.04] ${read.has(n.id) ? "opacity-55" : ""}`}
                  >
                    <span className={`mt-1.5 size-2 shrink-0 rounded-full ${TONE[n.tone]} shadow-[0_0_8px_currentColor]`} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-ink">{n.title}</span>
                      <span className="block text-xs text-ink-3">{n.body}</span>
                    </span>
                    <span className="tabular shrink-0 text-[11px] text-ink-3">{utcTime(n.time)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
