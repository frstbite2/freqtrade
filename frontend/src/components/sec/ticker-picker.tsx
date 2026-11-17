"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, OfflineState } from "@/components/ui/states";
import { type Remote, usePlatform } from "@/lib/platform";
import { type Jobs, watchlist } from "@/lib/sec";

const TICKER = /^[A-Za-z0-9.-]{1,16}$/;

/** Watchlist chips (read from the scheduler) plus a box for any other ticker the backend may hold. */
export function useTicker(): { ticker: string | null; tickers: string[]; setTicker: (t: string) => void; jobs: Remote<Jobs> } {
  const jobs = usePlatform<Jobs>("api/v1/jobs?history=0");
  const tickers = jobs.state === "ok" ? watchlist(jobs.data) : [];
  const [chosen, setChosen] = useState<string | null>(null);
  return { ticker: chosen ?? tickers[0] ?? null, tickers, setTicker: (t) => setChosen(t.toUpperCase()), jobs };
}

/** Why there is no ticker to show yet: the real reason, not a guess. */
export function NoWatchlist({ jobs }: { jobs: Remote<Jobs> }) {
  if (jobs.state === "loading") return <div className="skeleton h-24" aria-label="Loading" />;
  if (jobs.state === "offline") return <OfflineState what="SEC filing data" />;
  return (
    <EmptyState title="No watchlist yet">
      {jobs.state === "unavailable"
        ? "This backend has no ingestion scheduler (it arrives with the Milestone 5 branch, PR #2). Type a ticker above to check one."
        : "The ingestion scheduler has not completed a run, so no company is ingested yet. Type a ticker above to check one."}
    </EmptyState>
  );
}

export function TickerPicker({ ticker, tickers, onPick }: { ticker: string | null; tickers: string[]; onPick: (t: string) => void }) {
  const [text, setText] = useState("");
  const [bad, setBad] = useState(false);
  useEffect(() => setBad(false), [text]);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tickers.map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onPick(t)}
          aria-pressed={ticker === t}
          className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition-all ${ticker === t ? "bg-white/10 text-ink shadow-[0_0_0_1px_rgb(255_255_255/0.18)]" : "text-ink-3 hover:text-ink"}`}
        >
          {t}
        </button>
      ))}
      <form
        className="relative ml-auto w-full sm:w-44"
        onSubmit={(e) => {
          e.preventDefault();
          if (!TICKER.test(text.trim())) return setBad(true);
          onPick(text.trim());
          setText("");
        }}
      >
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Other ticker"
          aria-label="Look up another ticker"
          aria-invalid={bad}
          className={`h-9 w-full rounded-xl border bg-white/[0.04] pl-8 pr-3 text-sm uppercase text-ink placeholder:normal-case placeholder:text-ink-3 focus:outline-none ${bad ? "border-rose/60" : "border-line focus:border-violet/50"}`}
        />
      </form>
    </div>
  );
}
