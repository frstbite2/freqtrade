"use client";

import { Building2, ExternalLink, Search } from "lucide-react";
import { useState } from "react";
import { Chip, LiveBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { EmptyState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { ago, usd, utcDateTime } from "@/lib/format";
import { type Remote, usePlatform } from "@/lib/platform";
import { type HoldingChange, type Manager, type ManagerChanges, type Ownership, type OwnershipFiling, changeText, shares } from "@/lib/sec";
import { NoWatchlist, TickerPicker, useTicker } from "./ticker-picker";

const STATUS_TONE = { new: "mint", increased: "mint", reduced: "rose", exited: "rose", unchanged: "neutral", unclear: "gold" } as const;
const STATUSES = ["all", "new", "increased", "reduced", "exited", "unchanged", "unclear"] as const;

export function InstitutionalView() {
  return (
    <div className="space-y-6">
      <LargeHolders />
      <Managers />
      <SecurityLookup />
    </div>
  );
}

function Problem({ result, what }: { result: Remote<unknown>; what: string }) {
  if (result.state === "offline") return <OfflineState what={what} />;
  if (result.state !== "unavailable") return null;
  return (
    <EmptyState icon={<Building2 className="size-5 text-sky" aria-hidden />} title={result.status === 404 ? "Unavailable or not comparable" : "Could not load"}>
      {result.message}
    </EmptyState>
  );
}

/* ---------- 13D / 13G ---------- */

function LargeHolders() {
  const { ticker, tickers, setTicker, jobs } = useTicker();
  const result = usePlatform<Ownership>(ticker ? `api/v1/ownership/${ticker}/holders` : null);
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader
        title="Large holders (13D and 13G)"
        subtitle="Each filer's latest disclosed stake above 5%, as of its event date"
        right={<LiveBadge />}
      />
      <div className="mb-4">
        <TickerPicker ticker={ticker} tickers={tickers} onPick={setTicker} />
      </div>
      {ticker === null ? (
        <NoWatchlist jobs={jobs} />
      ) : result.state === "loading" ? (
        <SkeletonRows rows={4} />
      ) : result.state !== "ok" ? (
        <Problem result={result} what="13D/13G data" />
      ) : (
        <>
          {(result.data.holders ?? []).length === 0 ? (
            <p className="text-sm text-ink-3">No 13D or 13G filings in the ingested history for {result.data.issuer}.</p>
          ) : (
            <ul className="grid gap-3 md:grid-cols-2">
              {(result.data.holders ?? []).map((h) => (
                <HolderCard key={h.accession} h={h} />
              ))}
            </ul>
          )}
          <Coverage o={result.data} />
        </>
      )}
    </section>
  );
}

function HolderCard({ h }: { h: OwnershipFiling }) {
  const change = changeText(h);
  return (
    <li className="rounded-2xl border border-line bg-black/15 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink" title={h.holder}>{h.holder}</p>
          <p className="text-xs text-ink-3">{h.form}</p>
        </div>
        <p className="tabular shrink-0 font-display text-2xl font-bold text-ink">{h.percent === null ? "—" : `${Number(h.percent).toFixed(1)}%`}</p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Chip tone={h.schedule === "13D" ? "violet" : "sky"}>{h.schedule === "13D" ? "13D · may seek influence" : "13G · passive"}</Chip>
        {h.above_5_percent === false && <Chip tone="gold">now below 5%</Chip>}
      </div>
      <p className="tabular mt-2 text-xs text-ink-2">
        {h.structured || h.shares !== null ? `${shares(h.shares)} shares` : "Figures only in the filing document (filed before structured 13D/13G data)"}
        {h.event_date && ` as of ${h.event_date}`}
      </p>
      {change && <p className="mt-0.5 text-xs text-ink-3">{change}</p>}
      <p className="mt-2 text-[11px] text-ink-3">
        Public {utcDateTime(h.accepted_at)} ·{" "}
        <a href={h.filing_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-ink-2 hover:text-ink">
          filing <ExternalLink className="size-3" aria-hidden />
        </a>
      </p>
    </li>
  );
}

function Coverage({ o }: { o: Ownership }) {
  return (
    <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
      {o.issuer} · filings since {o.history_since} · ingested {ago(o.last_ingested_at, Date.now())}
      {o.missing_filings > 0 && <span className="text-gold"> · {o.missing_filings} filing(s) could not be read</span>}. {o.disclaimer}
    </p>
  );
}

/* ---------- 13F managers ---------- */

function Managers() {
  const list = usePlatform<{ managers: Manager[]; disclaimer: string }>("api/v1/institutional/managers");
  const [chosen, setChosen] = useState<number | null>(null);
  const managers = list.state === "ok" ? [...list.data.managers].sort((a, b) => a.name.localeCompare(b.name)) : [];
  const newest = managers.reduce<string | null>((m, x) => (x.latest_period && (!m || x.latest_period > m) ? x.latest_period : m), null);
  // Default to a manager that has filed the newest quarter, since only those can be compared.
  const cik = chosen ?? managers.find((m) => m.latest_period === newest)?.cik ?? null;

  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Tracked managers (13F)" subtitle="Quarterly holdings, compared quarter over quarter" right={<LiveBadge />} />
      {list.state === "loading" ? (
        <SkeletonRows rows={5} />
      ) : list.state !== "ok" ? (
        <Problem result={list} what="13F data" />
      ) : managers.length === 0 ? (
        <EmptyState title="No managers ingested">The 13F job has not stored any filings yet.</EmptyState>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,18rem)_1fr]">
          <ul className="grid max-h-[34rem] gap-1 overflow-y-auto pr-1 sm:grid-cols-2 lg:grid-cols-1">
            {managers.map((m) => (
              <li key={m.cik}>
                <button
                  type="button"
                  onClick={() => setChosen(m.cik)}
                  aria-pressed={cik === m.cik}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${cik === m.cik ? "border-sky/40 bg-sky/10" : "border-transparent hover:border-line hover:bg-white/[0.03]"}`}
                >
                  <span className="block truncate text-sm font-medium text-ink">{m.name}</span>
                  <span className={`block text-xs ${m.latest_period === newest ? "text-ink-3" : "text-gold/80"}`}>
                    Latest quarter {m.latest_period ?? "none"}{m.latest_period !== newest && " · not yet filed for " + newest}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {cik !== null && <Changes key={cik} cik={cik} />}
        </div>
      )}
      {list.state === "ok" && <p className="mt-4 text-[11px] leading-relaxed text-ink-3">{list.data.disclaimer}</p>}
    </section>
  );
}

function Changes({ cik }: { cik: number }) {
  const result = usePlatform<ManagerChanges>(`api/v1/institutional/managers/${cik}/changes?limit=2000`);
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("all");
  const [more, setMore] = useState(false);
  if (result.state === "loading") return <SkeletonRows rows={6} />;
  if (result.state !== "ok") return <Problem result={result} what="13F changes" />;
  const c = result.data;
  const counts = Object.fromEntries(STATUSES.map((s) => [s, s === "all" ? c.changes.length : c.changes.filter((x) => x.status === s).length]));
  const rows = c.changes.filter((x) => status === "all" || x.status === status);
  return (
    <div className="min-w-0">
      <p className="font-display text-lg font-semibold text-ink">{c.institution}</p>
      <p className="text-xs text-ink-3">
        Quarter ended {c.period} vs {c.previous_period} · disclosed {utcDateTime(c.disclosed_at)} · {c.total} positions compared
      </p>
      <div className="-mx-1 my-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {STATUSES.filter((s) => counts[s] > 0).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            aria-pressed={status === s}
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium capitalize transition-all ${status === s ? "bg-white/10 text-ink shadow-[0_0_0_1px_rgb(255_255_255/0.15)]" : "text-ink-3 hover:text-ink"}`}
          >
            {s} {counts[s]}
          </button>
        ))}
      </div>
      <ul className="divide-y divide-line">
        {rows.slice(0, more ? undefined : 12).map((x) => (
          <ChangeRow key={`${x.cusip}-${x.title_of_class}`} x={x} />
        ))}
      </ul>
      {!more && rows.length > 12 && (
        <button type="button" onClick={() => setMore(true)} className="mt-3 text-sm font-medium text-ink-2 hover:text-ink">
          Show {rows.length - 12} more
        </button>
      )}
      <p className="mt-3 text-[11px] leading-relaxed text-ink-3">
        Holdings as of the quarter end, disclosed up to 45 days later: not current holdings. Values are as reported in the filing.
        {c.option_rows_not_shown > 0 && ` ${c.option_rows_not_shown} option rows not shown.`}
        {c.confidential_positions_omitted && " Some positions were filed confidentially and are omitted."}
      </p>
    </div>
  );
}

function ChangeRow({ x }: { x: HoldingChange }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2.5 text-sm">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-ink">{x.issuer_name}</span>
          <Chip tone={STATUS_TONE[x.status as keyof typeof STATUS_TONE] ?? "neutral"} className="capitalize">{x.status}</Chip>
        </div>
        <p className="tabular truncate text-xs text-ink-3">
          {x.title_of_class} · {shares(x.previous_shares)} → {shares(x.shares)} sh
          {x.change_pct !== null && x.status !== "new" && x.status !== "exited" && ` (${x.change_pct > 0 ? "+" : ""}${x.change_pct.toFixed(1)}%)`}
        </p>
        {x.note && <p className="truncate text-xs text-gold/80">{x.note}</p>}
      </div>
      <p className="tabular shrink-0 text-right text-ink">{usd(Number(x.value), 0)}</p>
    </li>
  );
}

/* ---------- 13F by security ---------- */

interface Match {
  cusip: string;
  title_of_class: string;
  issuer_name: string;
  rows: number;
}

interface SecurityReport {
  issuer_name: string;
  period: string;
  previous_period: string;
  score: number;
  explanation: string;
  counts: Record<string, number>;
  managers_compared: number;
  managers_not_comparable: Record<string, string>;
  holders: (HoldingChange & { institution: string; disclosed_at: string })[];
  disclaimer: string;
}

function SecurityLookup() {
  const [query, setQuery] = useState("");
  const [name, setName] = useState<string | null>(null);
  const [cusip, setCusip] = useState<string | null>(null);
  const matches = usePlatform<{ matches: Match[] }>(name ? `api/v1/institutional/search?name=${encodeURIComponent(name)}` : null);
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Who holds a security (13F)" subtitle="Tracked managers' positions in one company, quarter over quarter" right={<LiveBadge />} />
      <form
        className="relative max-w-md"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim().length >= 2) {
            setName(query.trim());
            setCusip(null);
          }
        }}
      >
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Company name, e.g. Apple"
          aria-label="Search 13F holdings by company name"
          className="h-10 w-full rounded-xl border border-line bg-white/[0.04] pl-10 pr-3 text-sm text-ink placeholder:text-ink-3 focus:border-violet/50 focus:outline-none"
        />
      </form>
      {name && (
        <div className="mt-4">
          {matches.state === "loading" ? (
            <SkeletonRows rows={2} />
          ) : matches.state !== "ok" ? (
            <Problem result={matches} what="13F search" />
          ) : matches.data.matches.length === 0 ? (
            <p className="text-sm text-ink-3">No tracked manager reported a security named like &ldquo;{name}&rdquo;.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {matches.data.matches.slice(0, 12).map((m) => (
                <button
                  key={m.cusip}
                  type="button"
                  onClick={() => setCusip(m.cusip)}
                  aria-pressed={cusip === m.cusip}
                  className={`rounded-xl border px-3 py-1.5 text-left text-xs transition-colors ${cusip === m.cusip ? "border-sky/40 bg-sky/10 text-ink" : "border-line text-ink-2 hover:text-ink"}`}
                >
                  <span className="font-semibold">{m.issuer_name}</span> · {m.title_of_class} · {m.cusip}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {cusip && <Security key={cusip} cusip={cusip} />}
    </section>
  );
}

function Security({ cusip }: { cusip: string }) {
  const result = usePlatform<SecurityReport>(`api/v1/institutional/securities/${cusip}`);
  if (result.state === "loading") return <div className="mt-4"><SkeletonRows rows={3} /></div>;
  if (result.state !== "ok") return <div className="mt-4"><Problem result={result} what="13F holders" /></div>;
  const r = result.data;
  const notComparable = Object.keys(r.managers_not_comparable).length;
  return (
    <div className="mt-5 space-y-3">
      <p className="text-sm text-ink-2">{r.explanation}</p>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(r.counts).filter(([, n]) => n > 0).map(([k, n]) => (
          <Chip key={k} tone={STATUS_TONE[k as keyof typeof STATUS_TONE] ?? "neutral"} className="capitalize">{k}: {n}</Chip>
        ))}
        <Chip>{r.managers_compared} compared</Chip>
        {notComparable > 0 && <Chip tone="gold" className="normal-case">{notComparable} not comparable (no filing for both quarters)</Chip>}
      </div>
      {r.holders.length > 0 && (
        <ul className="divide-y divide-line">
          {r.holders.map((h) => (
            <li key={h.institution} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-ink">{h.institution}</span>
                  <Chip tone={STATUS_TONE[h.status as keyof typeof STATUS_TONE] ?? "neutral"} className="capitalize">{h.status}</Chip>
                </div>
                <p className="tabular text-xs text-ink-3">{shares(h.previous_shares)} → {shares(h.shares)} sh · disclosed {utcDateTime(h.disclosed_at)}</p>
              </div>
              <p className="tabular shrink-0 text-ink">{usd(Number(h.value), 0)}</p>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] leading-relaxed text-ink-3">
        Quarter ended {r.period} vs {r.previous_period}. A manager with no filing for both quarters is not comparable, never counted as a sale. {r.disclaimer}
      </p>
    </div>
  );
}
