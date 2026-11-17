"use client";

import { AreaChart } from "@/components/charts/area-chart";
import { TickerPicker, useTicker } from "@/components/sec/ticker-picker";
import { FreshBadge } from "@/components/ui/badges";
import { Delta } from "@/components/ui/delta";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { LineChart } from "lucide-react";
import { ago, price, utcDate, utcDateTime } from "@/lib/format";
import { type Bars, type Quote, closes, periodChange, quoteView } from "@/lib/market";
import { type PlatformStatus, type Remote, usePlatform } from "@/lib/platform";

/** Live mode: real daily bars and the latest quote, once the backend has Alpaca keys. */
export function LiveAssetChart() {
  const status = usePlatform<PlatformStatus>("api/v1/status");
  const configured = status.state === "ok" && status.data.providers_configured.alpaca;
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Asset chart" subtitle={configured ? "Daily bars from Alpaca, through the platform API" : undefined} />
      {configured ? <Configured /> : <LiveMarketState />}
    </section>
  );
}

function Configured() {
  const { ticker, tickers, setTicker } = useTicker();
  const bars = usePlatform<Bars>(ticker ? `api/v1/market/${ticker}/bars?timeframe=1d` : null);
  const quote = usePlatform<Quote>(ticker ? `api/v1/market/${ticker}/quote` : null);
  return (
    <div className="space-y-4">
      <TickerPicker ticker={ticker} tickers={tickers} onPick={setTicker} />
      {ticker && <QuoteLine ticker={ticker} quote={quote} />}
      {bars.state === "loading" ? (
        <SkeletonRows rows={3} />
      ) : bars.state !== "ok" ? (
        <Problem r={bars} />
      ) : bars.data.bars.length === 0 ? (
        <EmptyState title="No bars">The provider returned no daily bars for {ticker} in this range.</EmptyState>
      ) : (
        <Chart b={bars.data} />
      )}
      <p className="text-[11px] leading-relaxed text-ink-3">
        Live verification pending: the Alpaca connection has not yet been checked against real responses. Prices are
        never filled in when the provider fails; the reason is shown instead.
      </p>
    </div>
  );
}

function Problem({ r }: { r: Remote<unknown> }) {
  if (r.state === "offline") return <EmptyState title="Backend not connected">Market data comes from the platform API, which is not reachable.</EmptyState>;
  if (r.state !== "unavailable") return null;
  return <EmptyState title={r.status === 503 ? "Market data unavailable" : "Provider error"}>{r.message}</EmptyState>;
}

function QuoteLine({ ticker, quote }: { ticker: string; quote: Remote<Quote> }) {
  if (quote.state === "loading") return <div className="skeleton h-12" />;
  if (quote.state !== "ok") return <p className="text-sm text-ink-3">Latest quote unavailable{quote.state === "unavailable" ? `: ${quote.message}` : "."}</p>;
  const v = quoteView(quote.data);
  const age = ago(quote.data.ts, Date.now());
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-ink-3">{ticker} latest quote (bid/ask midpoint)</p>
        <p className="tabular font-display text-2xl font-bold text-ink">{v.state === "unusable" || v.mid === null ? "—" : price(v.mid)}</p>
      </div>
      <div className="text-right text-xs text-ink-3">
        {v.state === "current" ? <FreshBadge state="current" age={age} /> : v.state === "stale" ? <FreshBadge state="stale" age={age} /> : <FreshBadge state="unavailable" />}
        <p className="mt-1">
          {v.state === "current" && `Spread ${v.spreadPct.toFixed(2)}% · `}
          {v.state === "stale" && "Not a live price (normal outside market hours) · "}
          {v.state === "unusable" && `Not usable: ${v.reason} · `}
          quoted {utcDateTime(quote.data.ts)}
        </p>
      </div>
    </div>
  );
}

function Chart({ b }: { b: Bars }) {
  const pts = closes(b);
  const change = periodChange(pts);
  const up = (change ?? 0) >= 0;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-ink-3">
        <span>
          {pts.length} daily closes to {utcDate(pts[pts.length - 1].t)} · {b.adjustment === "raw" ? "not adjusted for splits or dividends" : `${b.adjustment} adjusted`}
        </span>
        {change !== null && <Delta value={change} />}
      </div>
      <AreaChart data={pts} from="#38c8ff" to={up ? "#36e3a1" : "#ff5c7a"} height={240} formatValue={price} formatTime={utcDate} ariaLabel={`${b.symbol} daily closes from ${b.source}`} />
      {(b.warnings.length > 0 || b.rejected.length > 0) && (
        <p className="mt-2 text-xs text-gold/90">
          {b.rejected.length > 0 && `${b.rejected.length} bar(s) failed integrity checks and are not shown. `}
          {b.warnings.join(" ")}
        </p>
      )}
    </div>
  );
}

/** Live mode: real market data needs Alpaca keys on the backend. Says which piece is missing. */
export function LiveMarketState() {
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
