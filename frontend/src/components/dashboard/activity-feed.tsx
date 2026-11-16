"use client";

import { Activity as ActivityIcon, ChevronRight, FileText, Radar, ShieldAlert, Waves, Zap } from "lucide-react";
import { useState } from "react";
import { DemoBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState } from "@/components/ui/states";
import { useDataMode } from "@/lib/data-mode";
import { utcDateTime, utcTime } from "@/lib/format";
import { ACTIVITY, type Activity, type ActivityKind } from "@/lib/sample-data";

const KIND: Record<ActivityKind, { icon: typeof Zap; color: string; label: string }> = {
  signal: { icon: Zap, color: "#38c8ff", label: "Signal" },
  insider: { icon: FileText, color: "#ffc65c", label: "Insider" },
  risk: { icon: ShieldAlert, color: "#ff5c7a", label: "Risk" },
  whale: { icon: Waves, color: "#a46bff", label: "Whale" },
  system: { icon: Radar, color: "#36e3a1", label: "System" },
};

const FILTERS: { id: "all" | ActivityKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "signal", label: "Signals" },
  { id: "insider", label: "Insider" },
  { id: "risk", label: "Risk" },
  { id: "whale", label: "Whale" },
];

export function ActivityFeed({ limit }: { limit?: number }) {
  const { mode } = useDataMode();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [open, setOpen] = useState<string | null>(null);
  const items = ACTIVITY.filter((a) => filter === "all" || a.kind === filter).slice(0, limit);

  return (
    <section className="card flex flex-col p-5 sm:p-6">
      <SectionHeader
        title="AI activity"
        subtitle="What the intelligence engine noticed, and why"
        right={mode === "demo" ? <DemoBadge /> : undefined}
      />
      {mode !== "demo" ? (
        <EmptyState icon={<ActivityIcon className="size-5 text-sky" aria-hidden />} title="No signals yet">
          Signals come from the intelligence engine (Milestone 6). Every real one will show its time,
          source, evidence and explanation. SEC filing data is already available under Insider Intelligence.
        </EmptyState>
      ) : (
        <>
          <div className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-all ${filter === f.id ? "bg-white/10 text-ink shadow-[0_0_0_1px_rgb(255_255_255/0.15)]" : "text-ink-3 hover:text-ink"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <ol className="relative space-y-2">
            {items.map((a, i) => (
              <Item key={a.id} a={a} index={i} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

function Item({ a, open, onToggle, index }: { a: Activity; open: boolean; onToggle: () => void; index: number }) {
  const k = KIND[a.kind];
  const Icon = k.icon;
  return (
    <li className="animate-rise" style={{ animationDelay: `${index * 50}ms` }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`group flex w-full items-start gap-3 rounded-2xl border p-3 text-left transition-all ${open ? "border-line-strong bg-white/[0.05]" : "border-transparent hover:border-line hover:bg-white/[0.03]"}`}
      >
        <span className="relative mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl" style={{ background: `${k.color}1f`, color: k.color, boxShadow: `inset 0 0 0 1px ${k.color}40` }}>
          <Icon className="size-4" aria-hidden />
          {a.severity !== "info" && <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full" style={{ background: a.severity === "warning" ? "#ff5c7a" : "#ffc65c", boxShadow: "0 0 8px currentColor" }} />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span className="truncate text-sm font-medium text-ink">
              <span className="font-semibold" style={{ color: k.color }}>{a.asset}</span>
              <span className="text-ink-3">: </span>
              {a.title}
            </span>
            <span className="tabular shrink-0 text-[11px] text-ink-3">{utcTime(a.time)}</span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-ink-3">{a.source}</span>
        </span>
        <ChevronRight className={`mt-2 size-4 shrink-0 text-ink-3 transition-transform ${open ? "rotate-90" : "group-hover:translate-x-0.5"}`} aria-hidden />
      </button>
      <div className={`grid transition-all duration-300 ${open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
        <div className="overflow-hidden">
          <div className="mx-3 mb-2 mt-1 space-y-3 rounded-xl border-l-2 pl-4 text-xs" style={{ borderColor: k.color }}>
            <div>
              <p className="mb-1 font-semibold uppercase tracking-wider text-ink-3">Evidence</p>
              <ul className="space-y-1 text-ink-2">
                {a.evidence.map((e) => (
                  <li key={e} className="flex gap-2">
                    <span className="mt-1.5 size-1 shrink-0 rounded-full" style={{ background: k.color }} />
                    {e}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-1 font-semibold uppercase tracking-wider text-ink-3">Explanation</p>
              <p className="leading-relaxed text-ink-2">{a.explanation}</p>
            </div>
            <p className="text-ink-3">
              {k.label} · {utcDateTime(a.time)} · {a.source}
            </p>
          </div>
        </div>
      </div>
    </li>
  );
}
