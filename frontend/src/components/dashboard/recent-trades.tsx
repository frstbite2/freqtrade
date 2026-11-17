"use client";

import { ArrowDownLeft, ArrowUpRight, Receipt } from "lucide-react";
import { DemoBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState } from "@/components/ui/states";
import { TokenIcon } from "@/components/ui/token-icon";
import { BOTS } from "@/lib/bots";
import { useDataMode } from "@/lib/data-mode";
import { price, signedUsd, utcDateTime } from "@/lib/format";
import { TICKERS, TRADES } from "@/lib/sample-data";

export function RecentTrades() {
  const { mode } = useDataMode();
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Recent simulated trades" subtitle="Paper trades placed by the bots" right={mode === "demo" ? <DemoBadge /> : undefined} />
      {mode !== "demo" ? (
        <EmptyState icon={<Receipt className="size-5 text-ember" aria-hidden />} title="No simulated trades yet">
          The bots place paper trades once their strategies (Milestone 6) and the simulated broker
          (Milestone 7) exist.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {TRADES.map((t) => {
            const bot = BOTS.find((b) => b.id === t.bot)!;
            const color = TICKERS.find((x) => x.symbol === t.symbol)?.color ?? "#a46bff";
            const buy = t.side === "buy";
            return (
              <li key={t.id} className="flex items-center gap-3 rounded-2xl border border-line bg-black/15 p-3 transition-colors hover:border-line-strong">
                <span className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${buy ? "bg-mint/15 text-mint" : "bg-rose/15 text-rose"}`}>
                  {buy ? <ArrowDownLeft className="size-4" aria-hidden /> : <ArrowUpRight className="size-4" aria-hidden />}
                </span>
                <TokenIcon symbol={t.symbol} color={color} size={30} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">
                    {buy ? "Bought" : "Sold"} {t.quantity} {t.symbol} at {price(t.price)}
                  </span>
                  <span className="block truncate text-xs text-ink-3">
                    <span style={{ color: bot.g1 }}>{bot.name}</span> · {utcDateTime(t.time)}
                  </span>
                </span>
                {t.pnl !== undefined && (
                  <span className={`tabular shrink-0 text-sm font-semibold ${t.pnl >= 0 ? "text-mint" : "text-rose"}`}>{signedUsd(t.pnl)}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
