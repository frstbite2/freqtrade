"use client";

import { Wallet } from "lucide-react";
import { Donut } from "@/components/charts/donut";
import { DemoBadge } from "@/components/ui/badges";
import { Delta } from "@/components/ui/delta";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState } from "@/components/ui/states";
import { TokenIcon } from "@/components/ui/token-icon";
import { useDataMode } from "@/lib/data-mode";
import { pct, price, usd } from "@/lib/format";
import { HOLDINGS, PORTFOLIO } from "@/lib/sample-data";

export function PortfolioPanel() {
  const { mode } = useDataMode();
  if (mode !== "demo") {
    return (
      <section className="card p-5 sm:p-6">
        <SectionHeader title="Portfolio" subtitle="Simulated holdings and allocation" />
        <EmptyState icon={<Wallet className="size-5 text-gold" aria-hidden />} title="No simulated holdings yet">
          Holdings appear when the paper broker (Milestone 7) places simulated trades. Only simulated
          balances will ever be shown: no deposits or withdrawals. A connected Phantom wallet is shown separately, read-only.
        </EmptyState>
      </section>
    );
  }

  const slices = [
    ...HOLDINGS.map((h) => ({ label: h.symbol, value: h.value, color: h.color })),
    { label: "Cash", value: PORTFOLIO.cash, color: "#7d7597" },
  ];

  return (
    <section className="card @container p-5 sm:p-6">
      <SectionHeader title="Portfolio" subtitle="Simulated holdings and allocation" right={<DemoBadge />} />
      <div className="grid gap-6 @5xl:grid-cols-[1.4fr_1fr]">
        <ul className="grid gap-2.5 @lg:grid-cols-2 @3xl:grid-cols-3 @5xl:grid-cols-2">
          {HOLDINGS.map((h) => (
            <li key={h.symbol} className="card card-hover rounded-2xl p-3.5" style={{ ["--glow" as string]: "164 107 255" }}>
              <div className="flex items-center gap-3">
                <TokenIcon symbol={h.symbol} color={h.color} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">{h.name}</p>
                  <p className="tabular truncate text-xs text-ink-3">
                    {h.quantity} {h.symbol} · {price(h.price)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="tabular text-sm font-semibold text-ink">{usd(h.value, 0)}</p>
                  <Delta value={h.change24hPct} />
                </div>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full" style={{ width: `${h.allocationPct}%`, background: `linear-gradient(90deg, ${h.color}88, ${h.color})`, boxShadow: `0 0 10px ${h.color}` }} />
                </div>
                <span className="tabular w-11 text-right text-[11px] font-medium text-ink-3">{pct(h.allocationPct)}</span>
              </div>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-center rounded-2xl border border-line bg-black/20 p-4">
          <Donut
            slices={slices}
            size={196}
            formatValue={(s, total) => pct((s.value / total) * 100)}
            center={(active) => (
              <>
                <span className="text-[11px] font-medium uppercase tracking-wider text-ink-3">{active ? active.label : "Total"}</span>
                <span className="tabular font-display text-lg font-bold text-ink">{usd(active ? active.value : PORTFOLIO.totalValue, 0)}</span>
                {active && <span className="text-xs text-ink-3">{pct((active.value / PORTFOLIO.totalValue) * 100)}</span>}
              </>
            )}
          />
        </div>
      </div>
    </section>
  );
}
