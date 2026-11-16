"use client";

import { BarChart3 } from "lucide-react";
import { CompareChart } from "@/components/charts/compare-chart";
import { DemoBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState } from "@/components/ui/states";
import { BOTS } from "@/lib/bots";
import { useDataMode } from "@/lib/data-mode";
import { signedPct } from "@/lib/format";
import { BOT_DEMO } from "@/lib/sample-data";

export function StrategyComparison() {
  const { mode } = useDataMode();
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader
        title="Strategy comparison"
        subtitle="Cumulative simulated return per bot. Tap a name to hide or show it."
        right={mode === "demo" ? <DemoBadge /> : undefined}
      />
      {mode !== "demo" ? (
        <EmptyState icon={<BarChart3 className="size-5 text-violet" aria-hidden />} title="Nothing to compare yet">
          Comparisons use verified paper trades and backtests (Milestones 6 to 8). None exist yet.
        </EmptyState>
      ) : (
        <CompareChart
          series={BOTS.map((b) => ({ id: b.id, label: b.name, color: b.g1, values: BOT_DEMO[b.id].spark.map((p) => p.v) }))}
          format={(v) => signedPct(v, 1)}
        />
      )}
    </section>
  );
}
