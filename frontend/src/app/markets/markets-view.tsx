"use client";

import { useState } from "react";
import { AssetChart, MarketOverview, Watchlist } from "@/components/dashboard/markets";
import { PageHeader } from "@/components/ui/page-header";
import { TICKERS } from "@/lib/sample-data";

export function MarketsView({ initialQuery }: { initialQuery: string }) {
  const match = TICKERS.find((t) => initialQuery && (t.symbol.toLowerCase() === initialQuery.toLowerCase() || t.name.toLowerCase().includes(initialQuery.toLowerCase())));
  const [symbol, setSymbol] = useState(match?.symbol ?? "BTC");
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Markets" title="Market watch" subtitle="Pick an asset to chart it. Hover or drag across the chart to read values." />
      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          <AssetChart symbol={symbol} />
          <MarketOverview />
        </div>
        <Watchlist initialQuery={initialQuery} selected={symbol} onSelect={setSymbol} />
      </div>
    </div>
  );
}
