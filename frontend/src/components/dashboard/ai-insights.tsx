"use client";

import { BrainCircuit, Sparkles } from "lucide-react";
import { DemoBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState } from "@/components/ui/states";
import { useDataMode } from "@/lib/data-mode";
import { pct, signedPct } from "@/lib/format";
import { HOLDINGS, MARKET_PULSE, PORTFOLIO } from "@/lib/sample-data";

/** Plain-language observations. In the prototype they are computed from the sample data. */
export function AiInsights() {
  const { mode } = useDataMode();
  const crypto = HOLDINGS.filter((h) => h.kind === "crypto").reduce((s, h) => s + h.allocationPct, 0);
  const top = HOLDINGS[0];
  const insights = [
    { tone: "#ff8a3d", title: "Concentration", text: `${pct(crypto)} of the portfolio is in crypto, and ${top.symbol} alone is ${pct(top.allocationPct)}.` },
    { tone: "#36e3a1", title: "Breadth", text: `${MARKET_PULSE.advancers} of ${MARKET_PULSE.advancers + MARKET_PULSE.decliners} watchlist assets are up today; ${MARKET_PULSE.topGainer.symbol} leads at ${signedPct(MARKET_PULSE.topGainer.change24hPct)}.` },
    { tone: "#a46bff", title: "Cash buffer", text: `${pct(PORTFOLIO.cashPct)} sits in cash, room for new positions within the risk limits.` },
  ];
  return (
    <section className="card glow-ring relative overflow-hidden p-5 sm:p-6" style={{ ["--g1" as string]: "#38c8ff", ["--g2" as string]: "#a46bff" }}>
      <div className="pointer-events-none absolute -left-16 -top-16 size-48 rounded-full bg-sky/15 blur-3xl" />
      <SectionHeader
        title="AI insights"
        subtitle="Observations, not predictions"
        eyebrow={<span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-sky"><BrainCircuit className="size-3.5" aria-hidden /> Intelligence engine</span>}
        right={mode === "demo" ? <DemoBadge /> : undefined}
      />
      {mode !== "demo" ? (
        <EmptyState icon={<Sparkles className="size-5 text-sky" aria-hidden />} title="The AI engine is not built yet">
          Insights arrive with Milestone 6. Each will cite the data it rests on.
        </EmptyState>
      ) : (
        <ul className="relative space-y-3">
          {insights.map((i) => (
            <li key={i.title} className="flex gap-3 rounded-2xl border border-line bg-black/20 p-3.5">
              <span className="mt-1 size-2 shrink-0 rounded-full" style={{ background: i.tone, boxShadow: `0 0 10px ${i.tone}` }} />
              <div>
                <p className="text-sm font-semibold text-ink">{i.title}</p>
                <p className="mt-0.5 text-sm leading-relaxed text-ink-2">{i.text}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
