"use client";

import { ExternalLink, FileSearch } from "lucide-react";
import { useState } from "react";
import { Chip } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { ago, usd, utcDateTime } from "@/lib/format";
import { type Remote, usePlatform } from "@/lib/platform";
import type { Jobs } from "@/lib/sec";
import { type InsiderScore, type InsiderTransactions, type InsiderTx, categoryLabel, role, shares } from "@/lib/sec";
import { Fresh } from "./fresh";
import { NoWatchlist, TickerPicker, useTicker } from "./ticker-picker";

const COMPONENT_LABEL: Record<string, string> = {
  purchase_value: "Purchase value",
  seniority: "Seniority of buyers",
  cluster: "Several insiders buying",
  ownership_change: "Growth in buyers' holdings",
  buyer_history: "Buyers' track record of buying",
  announcement_timing: "Timing around announcements",
  value_vs_market_cap: "Size versus market value",
};

export function InsiderView() {
  const { ticker, tickers, setTicker, jobs } = useTicker();
  return (
    <div className="space-y-6">
      <section className="card p-4 sm:p-5">
        <TickerPicker ticker={ticker} tickers={tickers} onPick={setTicker} />
      </section>
      {ticker === null ? (
        <section className="card p-6">
          <NoWatchlist jobs={jobs} />
        </section>
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[1fr_1.6fr]">
          <ScoreCard ticker={ticker} jobs={jobs} />
          <Transactions ticker={ticker} jobs={jobs} />
        </div>
      )}
    </div>
  );
}

/** Not ingested is "unavailable", which must never read as "no insider activity". */
function NotIngested({ result, what }: { result: Remote<unknown>; what: string }) {
  if (result.state === "offline") return <OfflineState what={what} />;
  if (result.state !== "unavailable") return null;
  return (
    <EmptyState icon={<FileSearch className="size-5 text-gold" aria-hidden />} title={result.status === 404 ? "Unavailable" : "Could not load"}>
      {result.message}
    </EmptyState>
  );
}

function ScoreCard({ ticker, jobs }: { ticker: string; jobs: Remote<Jobs> }) {
  const result = usePlatform<InsiderScore>(`api/v1/insider/${ticker}/score`);
  return (
    <section className="card glow-ring flex flex-col p-5 sm:p-6" style={{ ["--g1" as string]: "#ffc65c", ["--g2" as string]: "#ff8a3d" }}>
      <SectionHeader title={`${ticker} insider score`} subtitle="Research ranking of disclosed open-market buying" right={result.state === "loading" ? undefined : <Fresh ingestedAt={result.state === "ok" ? result.data.last_ingested_at : null} job="insider" jobs={jobs} />} />
      {result.state === "loading" ? (
        <SkeletonRows rows={5} />
      ) : result.state !== "ok" ? (
        <NotIngested result={result} what="Insider data" />
      ) : (
        <Score s={result.data} />
      )}
    </section>
  );
}

function Score({ s }: { s: InsiderScore }) {
  const now = Date.now();
  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <p className="tabular font-display text-5xl font-bold text-gradient">{s.score.toFixed(1)}</p>
        <p className="pb-2 text-sm text-ink-3">/ 100 · last {s.window_days} days</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5" role="img" aria-label={`Score ${s.score.toFixed(1)} of 100`}>
        <div className="h-full rounded-full bg-gradient-to-r from-gold to-ember" style={{ width: `${Math.min(100, s.score)}%` }} />
      </div>
      <p className="text-sm leading-relaxed text-ink-2">{s.explanation}</p>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <Tally label="Open-market buys" tone="mint" t={s.discretionary_buys} />
        <Tally label="Open-market sells" tone="rose" t={s.discretionary_sells} />
      </div>

      <ul className="space-y-2.5">
        {s.components.map((c) => (
          <li key={c.name} className="text-xs">
            <div className="flex justify-between gap-2">
              <span className={c.available ? "text-ink-2" : "text-ink-3"}>{COMPONENT_LABEL[c.name] ?? c.name}</span>
              <span className="tabular text-ink-3">{c.available ? `${c.points} / ${c.max_points}` : "unavailable"}</span>
            </div>
            <div className={`mt-1 h-1.5 overflow-hidden rounded-full ${c.available ? "bg-white/5" : "border border-dashed border-line-strong"}`}>
              {c.available && <div className="h-full rounded-full bg-gold/80" style={{ width: `${(100 * c.points) / c.max_points}%` }} />}
            </div>
            <p className="mt-0.5 text-ink-3">{c.detail}</p>
          </li>
        ))}
      </ul>

      {Object.keys(s.not_counted).length > 0 && (
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-3">Filed but never counted</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(s.not_counted).map(([k, n]) => (
              <Chip key={k}>{categoryLabel(k)}: {n}</Chip>
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto space-y-1 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-3">
        <p>
          Method coverage {Math.round(s.coverage * 100)}%: components marked unavailable need engines not built yet, so the
          score is scaled over the rest.
        </p>
        <p>
          Filings since {s.history_since} · ingested {ago(s.last_ingested_at, now)} ({utcDateTime(s.last_ingested_at)})
          {s.missing_filings > 0 && <span className="text-gold"> · {s.missing_filings} filing(s) could not be read</span>}
        </p>
        <p>{s.disclaimer}</p>
      </div>
    </div>
  );
}

function Tally({ label, tone, t }: { label: string; tone: "mint" | "rose"; t: { transactions: number; insiders: number; value: string } }) {
  return (
    <div className="rounded-xl border border-line bg-black/15 p-3">
      <p className="text-[11px] uppercase tracking-wider text-ink-3">{label}</p>
      <p className={`tabular mt-0.5 font-display text-lg font-semibold ${tone === "mint" ? "text-mint" : "text-rose"}`}>{usd(Number(t.value), 0)}</p>
      <p className="text-xs text-ink-3">{t.transactions} trades · {t.insiders} insider{t.insiders === 1 ? "" : "s"}</p>
    </div>
  );
}

function Transactions({ ticker, jobs }: { ticker: string; jobs: Remote<Jobs> }) {
  const [signalsOnly, setSignalsOnly] = useState(true);
  const [all, setAll] = useState(false);
  const result = usePlatform<InsiderTransactions>(`api/v1/insider/${ticker}/transactions?signals_only=${signalsOnly}&limit=50`);
  return (
    <section className="card flex min-w-0 flex-col p-5 sm:p-6">
      <SectionHeader
        title="Disclosed transactions"
        subtitle={result.state === "ok" ? `${result.data.total} ${signalsOnly ? "open-market trades" : "rows"}, newest first${result.data.total > 50 ? " (50 shown)" : ""}` : "From Forms 3, 4 and 5"}
        right={
          <div className="flex flex-wrap items-center justify-end gap-2">
          {result.state !== "loading" && <Fresh ingestedAt={result.state === "ok" ? result.data.last_ingested_at : null} job="insider" jobs={jobs} />}
          <div className="flex rounded-xl border border-line bg-white/[0.03] p-0.5 text-xs" role="group" aria-label="Which transactions">
            {[true, false].map((v) => (
              <button
                key={String(v)}
                type="button"
                aria-pressed={signalsOnly === v}
                onClick={() => setSignalsOnly(v)}
                className={`rounded-lg px-2.5 py-1 font-medium ${signalsOnly === v ? "bg-white/10 text-ink" : "text-ink-3 hover:text-ink"}`}
              >
                {v ? "Signals" : "All rows"}
              </button>
            ))}
          </div>
          </div>
        }
      />
      {result.state === "loading" ? (
        <SkeletonRows rows={6} />
      ) : result.state !== "ok" ? (
        <NotIngested result={result} what="Insider transactions" />
      ) : result.data.transactions.length === 0 ? (
        <EmptyState title="No qualifying trades">
          {signalsOnly ? "No open-market purchases or sales are on file in the ingested history. Other filings are under All rows." : "No transactions in the ingested history."}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line">
          {result.data.transactions.slice(0, all ? undefined : 12).map((t, i) => (
            <Row key={`${t.accession}-${i}`} t={t} />
          ))}
          {!all && result.data.transactions.length > 12 && (
            <li className="pt-3">
              <button type="button" onClick={() => setAll(true)} className="text-sm font-medium text-ink-2 hover:text-ink">
                Show {result.data.transactions.length - 12} more
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

function Row({ t }: { t: InsiderTx }) {
  const tone = t.signal === "discretionary_buy" ? "mint" : t.signal === "discretionary_sell" ? "rose" : "neutral";
  return (
    <li className="grid gap-x-4 gap-y-1 py-3 text-sm sm:grid-cols-[1fr_auto]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium text-ink">{t.insider}</span>
          <Chip tone={tone}>{categoryLabel(t.category)}</Chip>
          {t.issues.length > 0 && <Chip tone="gold">excluded: {t.issues[0]}</Chip>}
        </div>
        <p className="truncate text-xs text-ink-3">{role(t)} · {t.security}</p>
      </div>
      <div className="tabular text-left sm:text-right">
        <p className="text-ink">
          {shares(t.shares)} sh{t.price !== null && Number(t.price) > 0 && <span className="text-ink-3"> @ {usd(Number(t.price))}</span>}
        </p>
        <p className="text-xs text-ink-3">{t.value !== null && Number(t.value) > 0 ? usd(Number(t.value), 0) : "no price"}</p>
      </div>
      <p className="text-[11px] text-ink-3 sm:col-span-2">
        Traded {t.transaction_date} · public {utcDateTime(t.accepted_at)} · Form {t.form} ·{" "}
        <a href={t.filing_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-ink-2 hover:text-ink">
          filing <ExternalLink className="size-3" aria-hidden />
        </a>
      </p>
    </li>
  );
}
