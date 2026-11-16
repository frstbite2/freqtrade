"use client";

import { FlaskConical } from "lucide-react";
import { useDataMode } from "@/lib/data-mode";
import { SAMPLE_AS_OF } from "@/lib/sample-data";
import { utcDateTime } from "@/lib/format";

/** Always visible in demo mode: nothing on screen is mistaken for real data. */
export function DemoBanner() {
  const { mode, setMode } = useDataMode();
  if (mode !== "demo") return null;
  return (
    <div className="mb-6 flex flex-col gap-2 rounded-2xl border border-gold/25 bg-gradient-to-r from-gold/10 via-ember/[0.06] to-transparent px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-start gap-2.5 text-ink-2">
        <FlaskConical className="mt-0.5 size-4 shrink-0 text-gold" aria-hidden />
        <span>
          <span className="font-semibold text-gold">Demo mode.</span> Values marked DEMO are sample data for the design
          preview (as of {utcDateTime(SAMPLE_AS_OF)}): not market prices, filings or trading results.
        </span>
      </p>
      <button type="button" onClick={() => setMode("live")} className="shrink-0 self-start rounded-lg border border-line-strong px-3 py-1 text-xs font-semibold text-ink hover:bg-white/5 sm:self-auto">
        Show live data only
      </button>
    </div>
  );
}
