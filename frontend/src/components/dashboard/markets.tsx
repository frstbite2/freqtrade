"use client";

import { LineChart, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { AreaChart } from "@/components/charts/area-chart";
import { Sparkline } from "@/components/charts/sparkline";
import { DemoBadge } from "@/components/ui/badges";
import { Delta } from "@/components/ui/delta";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { TokenIcon } from "@/components/ui/token-icon";
import { useDataMode } from "@/lib/data-mode";
import { compact, price, signedPct, utcTime } from "@/lib/format";
import { type PlatformStatus, usePlatform } from "@/lib/platform";
import { MARKET_PULSE, TICKERS, type Ticker } from "@/lib/sample-data";

/** Live mode: real market data needs Alpaca keys on the backend. Says which piece is missing. */
function LiveMarketState() {
  const status = usePlatform<PlatformStatus>("api/v1/status");
  if (status.state === "loading") return <SkeletonRows rows={3} />;
  if (status.state === "offline") return <OfflineState what="Market data" />;
  if (status.state === "unavailable")
    return <EmptyState title="Market data unavailable">The platform API answered {status.message}.</EmptyState>;
  const alpaca = status.data.providers_configured.alpaca;
  return (
    <EmptyState icon={<LineChart className="size-5 text-sky" aria-hidden />} title={alpaca ? "Market data connects in Stage 2" : "Market data is not configured"}>
      {alpaca
        ? "The backend has Alpaca keys. Live quotes and charts are wired to it in Stage 2."
        : "The backend has no Alpaca API keys, so it serves no prices. It says \"unavailable\" rather than showing made-up numbers."}
    </EmptyState>
  );
}

export function MarketOverview() {
  const { mode } = useDataMode();
  const p = MARKET_PULSE;
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Market overview" subtitle="Breadth and movers across the watchlist" right={mode === "demo" ? <DemoBadge /> : undefined} />
      {mode !== "demo" ? (
        <LiveMarketState />
      ) : (
        <div className="space-y-5">
          <div>
            <div className="mb-2 flex justify-between text-xs">
              <span className="font-medium text-mint">{p.advancers} rising</span>
              <span className="text-ink-3">avg {signedPct(p.averageChangePct)}</span>
              <span className="font-medium text-rose">{p.decliners} falling</span>
            </div>
            <div className="flex h-2.5 gap-1 overflow-hidden rounded-full">
              <div className="rounded-full bg-gradient-to-r from-mint/60 to-mint shadow-[0_0_14px_#36e3a1]" style={{ flex: p.advancers }} />
              <div className="rounded-full bg-gradient-to-r from-rose to-rose/60 shadow-[0_0_14px_#ff5c7a]" style={{ flex: p.decliners }} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Mover label="Top gainer" t={p.topGainer} />
            <Mover label="Top loser" t={p.topLoser} />
          </div>
        </div>
      )}
    </section>
  );
}

function Mover({ label, t }: { label: string; t: Ticker }) {
  return (
    <div className="rounded-2xl border border-line bg-black/20 p-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-3">{label}</p>
      <div className="mt-2 flex items-center gap-2.5">
        <TokenIcon symbol={t.symbol} color={t.color} size={32} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">{t.symbol}</p>
          <Delta value={t.change24hPct} />
        </div>
      </div>
      <Sparkline values={t.series.map((s) => s.v)} width={140} height={34} className="mt-2 h-8 w-full" />
    </div>
  );
}

export function Watchlist({
  initialQuery = "",
  selected,
  onSelect,
  limit,
}: {
  initialQuery?: string;
  selected?: string;
  onSelect?: (symbol: string) => void;
  limit?: number;
}) {
  const { mode } = useDataMode();
  const [query, setQuery] = useState(initialQuery);
  const [kind, setKind] = useState<"all" | "crypto" | "stock">("all");
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return TICKERS.filter((t) => (kind === "all" || t.kind === kind) && (!q || t.symbol.toLowerCase().includes(q) || t.name.toLowerCase().includes(q)));
  }, [query, kind]);

  return (
    <section className="card flex flex-col p-5 sm:p-6">
      <SectionHeader title="Watchlist" subtitle="Search tokens and stocks" right={mode === "demo" ? <DemoBadge /> : undefined} />
      {mode !== "demo" ? (
        <LiveMarketState />
      ) : (
        <>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row">
            <label className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="BTC, Solana, NVDA…"
                aria-label="Filter the watchlist"
                className="h-10 w-full rounded-xl border border-line bg-white/[0.04] pl-9 pr-3 text-sm text-ink placeholder:text-ink-3 focus:border-violet/50 focus:outline-none"
              />
            </label>
            <div className="flex rounded-xl border border-line bg-white/[0.03] p-1 text-xs font-semibold">
              {(["all", "crypto", "stock"] as const).map((k) => (
                <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k}
                  className={`flex-1 rounded-lg px-3 py-1.5 capitalize transition-colors ${kind === k ? "bg-white/10 text-ink" : "text-ink-3 hover:text-ink"}`}>
                  {k === "stock" ? "Stocks" : k}
                </button>
              ))}
            </div>
          </div>
          {rows.length === 0 ? (
            <EmptyState title="No matches">Nothing on the watchlist matches “{query}”.</EmptyState>
          ) : (
            <ul className="-mx-2 divide-y divide-line">
              {rows.slice(0, limit).map((t) => (
                <li key={t.symbol}>
                  <button
                    type="button"
                    onClick={() => onSelect?.(t.symbol)}
                    className={`flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors ${selected === t.symbol ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"}`}
                  >
                    <TokenIcon symbol={t.symbol} color={t.color} size={32} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-ink">{t.symbol}</span>
                      <span className="block truncate text-xs text-ink-3">{t.name}</span>
                    </span>
                    <Sparkline values={t.series.map((s) => s.v)} width={80} height={28} className="hidden h-7 w-20 sm:block" />
                    <span className="w-24 text-right">
                      <span className="tabular block text-sm font-medium text-ink">{price(t.price)}</span>
                      <Delta value={t.change24hPct} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

export function AssetChart({ symbol }: { symbol: string }) {
  const { mode } = useDataMode();
  const t = TICKERS.find((x) => x.symbol === symbol) ?? TICKERS[0];
  if (mode !== "demo")
    return (
      <section className="card p-5 sm:p-6">
        <SectionHeader title="Asset chart" />
        <LiveMarketState />
      </section>
    );
  const up = t.change24hPct >= 0;
  return (
    <section className="card glow-ring p-5 sm:p-6" style={{ ["--g1" as string]: t.color, ["--g2" as string]: up ? "#36e3a1" : "#ff5c7a" }}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <TokenIcon symbol={t.symbol} color={t.color} size={44} />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-display text-xl font-bold text-ink">{t.name}</h2>
              <DemoBadge />
            </div>
            <p className="text-sm text-ink-3">{t.symbol} · {t.kind === "crypto" ? "Crypto" : "Stock"} · 24h volume {compact(t.volume24h)}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="tabular font-display text-2xl font-bold text-ink">{price(t.price)}</p>
          <Delta value={t.change24hPct} size="md" />
        </div>
      </div>
      <AreaChart data={t.series} from={t.color} to={up ? "#36e3a1" : "#ff5c7a"} height={260} formatValue={price} formatTime={utcTime} ariaLabel={`${t.name} sample price, last 24 hours`} />
    </section>
  );
}
