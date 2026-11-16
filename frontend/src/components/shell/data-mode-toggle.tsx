"use client";

import { useDataMode } from "@/lib/data-mode";

export function DataModeToggle() {
  const { mode, setMode } = useDataMode();
  return (
    <div role="radiogroup" aria-label="Data shown" className="flex rounded-xl border border-line bg-white/[0.03] p-0.5 text-xs font-semibold">
      {(["demo", "live"] as const).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={mode === m}
          onClick={() => setMode(m)}
          title={m === "demo" ? "Sample values for the design prototype, each badged DEMO" : "Only real data from the platform API"}
          className={`rounded-[10px] px-3 py-1.5 capitalize transition-all ${
            mode === m
              ? m === "demo"
                ? "bg-gold/15 text-gold shadow-[0_0_14px_-4px_#ffc65c]"
                : "bg-mint/15 text-mint shadow-[0_0_14px_-4px_#36e3a1]"
              : "text-ink-3 hover:text-ink"
          }`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
