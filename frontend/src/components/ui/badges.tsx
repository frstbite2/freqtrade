import { CircleSlash, Clock3, FlaskConical } from "lucide-react";
import type { ReactNode } from "react";

/** Marks every sample value. Never removed while a value comes from sample-data.ts. */
export function DemoBadge({ className = "" }: { className?: string }) {
  return (
    <span
      title="Sample value for the design prototype. Not a market price or trading result."
      className={`inline-flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gold ${className}`}
    >
      <FlaskConical className="size-3" aria-hidden />
      Demo
    </span>
  );
}

export function LiveBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-mint/30 bg-mint/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-mint ${className}`}
    >
      <span className="relative flex size-1.5">
        <span className="absolute inline-flex size-full animate-pulse-ring rounded-full bg-mint" />
        <span className="relative inline-flex size-1.5 rounded-full bg-mint" />
      </span>
      Live
    </span>
  );
}

export function Chip({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "violet" | "ember" | "mint" | "rose" | "sky" | "gold";
  className?: string;
}) {
  const tones = {
    neutral: "border-line-strong bg-white/5 text-ink-2",
    violet: "border-violet/30 bg-violet/10 text-violet",
    ember: "border-ember/30 bg-ember/10 text-ember",
    mint: "border-mint/30 bg-mint/10 text-mint",
    rose: "border-rose/30 bg-rose/10 text-rose",
    sky: "border-sky/30 bg-sky/10 text-sky",
    gold: "border-gold/30 bg-gold/10 text-gold",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

const STATUS = {
  active: { label: "Active", dot: "bg-mint", text: "text-mint", ring: true },
  analyzing: { label: "Analyzing", dot: "bg-sky", text: "text-sky", ring: true },
  idle: { label: "Idle", dot: "bg-ink-3", text: "text-ink-3", ring: false },
  offline: { label: "Not running", dot: "bg-ink-3/60", text: "text-ink-3", ring: false },
} as const;

export type StatusKind = keyof typeof STATUS;

export function StatusDot({ status, label }: { status: StatusKind; label?: string }) {
  const s = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-2 text-xs font-medium ${s.text}`}>
      <span className="relative flex size-2">
        {s.ring && <span className={`absolute inline-flex size-full animate-pulse-ring rounded-full ${s.dot}`} />}
        <span className={`relative inline-flex size-2 rounded-full ${s.dot}`} />
      </span>
      {label ?? s.label}
    </span>
  );
}

/**
 * Real data and how fresh it is: LIVE (on schedule), STALE (the ingestion job is overdue, data
 * shown with its age) or UNAVAILABLE (nothing ingested). Never used for sample values.
 */
export function FreshBadge({ state, age }: { state: "current" | "stale" | "unknown" | "unavailable"; age?: string }) {
  if (state === "unavailable")
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-white/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
        <CircleSlash className="size-3" aria-hidden /> Unavailable
      </span>
    );
  if (state === "stale")
    return (
      <span title="Real data, but the ingestion job is overdue: this may not include the newest filings." className="inline-flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gold">
        <Clock3 className="size-3" aria-hidden /> Stale{age && <span className="normal-case tracking-normal"> · {age}</span>}
      </span>
    );
  return (
    <span title={state === "current" ? "Real data, ingested on schedule." : "Real data; this backend reports no schedule to judge freshness."} className="inline-flex items-center gap-1.5 rounded-full border border-mint/30 bg-mint/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-mint">
      <span className="relative flex size-1.5">
        {state === "current" && <span className="absolute inline-flex size-full animate-pulse-ring rounded-full bg-mint" />}
        <span className="relative inline-flex size-1.5 rounded-full bg-mint" />
      </span>
      Live{age && <span className="normal-case tracking-normal"> · {age}</span>}
    </span>
  );
}
