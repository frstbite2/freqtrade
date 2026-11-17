"use client";

import { FileSearch } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Item } from "@/components/dashboard/activity-feed";
import { LiveBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { ago } from "@/lib/format";
import { fetchPlatform } from "@/lib/platform";
import { type Disclosure, type InsiderTransactions, type Jobs, type Ownership, insiderDisclosures, newestFirst, ownershipDisclosure, watchlist } from "@/lib/sec";

type Feed =
  | { state: "loading" }
  | { state: "offline" }
  | { state: "none"; reason: string }
  | { state: "ok"; items: Disclosure[]; tickers: string[]; unavailable: string[]; ingested: string | null };

const FILTERS = [
  { id: "all", label: "All" },
  { id: "insider", label: "Insider trades" },
  { id: "ownership", label: "13D/13G" },
] as const;

/** Real: the newest SEC disclosures for the scheduler's watchlist. Not AI signals: raw, delayed filings. */
export function SecDisclosures({ limit = 6 }: { limit?: number }) {
  const [feed, setFeed] = useState<Feed>({ state: "loading" });
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const jobs = await fetchPlatform<Jobs>("api/v1/jobs?history=0");
      if (cancelled) return;
      if (jobs.state === "offline") return setFeed({ state: "offline" });
      if (jobs.state !== "ok") return setFeed({ state: "none", reason: "This backend has no ingestion scheduler yet, so there is no watchlist to read." });
      const tickers = watchlist(jobs.data);
      if (!tickers.length) return setFeed({ state: "none", reason: "The scheduler has not completed a run yet, so no filings are stored." });
      const results = await Promise.all(
        tickers.map(async (t) => {
          const [ins, own] = await Promise.all([
            fetchPlatform<InsiderTransactions>(`api/v1/insider/${t}/transactions?signals_only=true&limit=${limit}`),
            fetchPlatform<Ownership>(`api/v1/ownership/${t}/filings?limit=${limit}`),
          ]);
          return { t, ins, own };
        }),
      );
      if (cancelled) return;
      const items: Disclosure[] = [];
      const unavailable: string[] = [];
      const ingested: string[] = [];
      for (const { t, ins, own } of results) {
        if (ins.state === "ok") {
          items.push(...insiderDisclosures(t, ins.data.transactions));
          ingested.push(ins.data.last_ingested_at);
        } else unavailable.push(`${t} insider`);
        if (own.state === "ok") {
          items.push(...(own.data.filings ?? []).map((f) => ownershipDisclosure(t, f)));
          ingested.push(own.data.last_ingested_at);
        } else unavailable.push(`${t} 13D/13G`);
      }
      setFeed({ state: "ok", items, tickers, unavailable, ingested: ingested.sort()[0] ?? null });
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const shown = feed.state === "ok" ? newestFirst(feed.items.filter((a) => filter === "all" || a.kind === filter), limit) : [];

  return (
    <section className="card flex flex-col p-5 sm:p-6">
      <SectionHeader
        title="SEC disclosures"
        subtitle={feed.state === "ok" ? `Newest filings for ${feed.tickers.join(", ")}` : "Newest filings on the watchlist"}
        right={<LiveBadge />}
      />
      {feed.state === "loading" ? (
        <SkeletonRows rows={4} />
      ) : feed.state === "offline" ? (
        <OfflineState what="SEC filing data" />
      ) : feed.state === "none" ? (
        <EmptyState icon={<FileSearch className="size-5 text-sky" aria-hidden />} title="No filing data yet">{feed.reason}</EmptyState>
      ) : (
        <>
          <div className="-mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                aria-pressed={filter === f.id}
                className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-all ${filter === f.id ? "bg-white/10 text-ink shadow-[0_0_0_1px_rgb(255_255_255/0.15)]" : "text-ink-3 hover:text-ink"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="text-sm text-ink-3">No disclosures of this kind are stored for the watchlist.</p>
          ) : (
            <ol className="relative space-y-2">
              {shown.map((a, i) => (
                <Item key={a.id} a={a} index={i} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} />
              ))}
            </ol>
          )}
          <p className="mt-auto pt-3 text-[11px] leading-relaxed text-ink-3">
            Insider items are open-market trades only. Times are when each filing became public.
            {feed.ingested && <> Oldest ingestion {ago(feed.ingested, Date.now())}.</>}
            {feed.unavailable.length > 0 && <> Unavailable: {feed.unavailable.join(", ")}.</>}{" "}
            <Link href="/insider" className="text-ink-2 underline-offset-2 hover:text-ink hover:underline">Explore filings</Link>
          </p>
        </>
      )}
    </section>
  );
}
