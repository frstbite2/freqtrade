"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { AreaChart } from "@/components/charts/area-chart";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { DemoBadge } from "@/components/ui/badges";
import { Delta } from "@/components/ui/delta";
import { EmptyState } from "@/components/ui/states";
import { useDataMode } from "@/lib/data-mode";
import { usd, utcDateTime } from "@/lib/format";
import { PORTFOLIO, TIMEFRAMES, type Timeframe, portfolioSeries } from "@/lib/sample-data";

export function HeroBalance() {
  const { mode } = useDataMode();
  const [tf, setTf] = useState<Timeframe>("1M");
  const series = portfolioSeries(tf);
  const change = series[series.length - 1].v - series[0].v;
  const changePct = (change / series[0].v) * 100;

  return (
    <section
      className="card glow-ring relative overflow-hidden p-5 sm:p-7"
      style={{ ["--g1" as string]: "#a46bff", ["--g2" as string]: "#ff8a3d" }}
      aria-labelledby="balance-title"
    >
      <div className="pointer-events-none absolute -right-24 -top-24 size-80 animate-float rounded-full bg-violet/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-32 left-1/3 size-72 rounded-full bg-ember/10 blur-3xl" />

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 id="balance-title" className="text-sm font-medium text-ink-2">Total simulated portfolio</h1>
            {mode === "demo" && <DemoBadge />}
          </div>
          {mode === "demo" ? (
            <>
              <AnimatedNumber
                value={PORTFOLIO.totalValue}
                format={(n) => usd(n)}
                className="text-gradient mt-2 block font-display text-4xl font-bold tracking-tight sm:text-6xl"
              />
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="flex items-center gap-1.5">
                  <Delta value={change} kind="usd" size="md" />
                  <Delta value={changePct} size="md" className="opacity-80" />
                </span>
                <span className="text-ink-3">over {tf === "1D" ? "today" : `the last ${tf}`}</span>
              </div>
            </>
          ) : (
            <p className="mt-3 max-w-md font-display text-2xl font-semibold text-ink-3">No simulated portfolio yet</p>
          )}
        </div>
        {mode === "demo" && (
          <div role="tablist" aria-label="Chart range" className="flex rounded-xl border border-line bg-white/[0.03] p-1">
            {TIMEFRAMES.map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tf === t}
                onClick={() => setTf(t)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${tf === t ? "bg-gradient-to-br from-violet/50 to-ember/40 text-white shadow-[0_0_16px_-4px_#a46bff]" : "text-ink-3 hover:text-ink"}`}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative mt-6">
        {mode === "demo" ? (
          <AreaChart
            data={series}
            height={240}
            formatValue={(v) => usd(v)}
            formatTime={utcDateTime}
            ariaLabel={`Sample portfolio value over ${tf}`}
          />
        ) : (
          <EmptyState icon={<Sparkles className="size-5 text-violet" aria-hidden />} title="The paper portfolio starts with Milestone 7">
            Balances, profit and loss and this chart come from the simulated broker, which is not built
            yet. Nothing here is estimated or filled in.
          </EmptyState>
        )}
      </div>
    </section>
  );
}
