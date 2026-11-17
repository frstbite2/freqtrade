/**
 * SEC filing data from the platform API: response types and pure helpers for display.
 * Every record keeps the time it became public (accepted_at); disclosures are delayed and are
 * never evidence of wrongdoing or of current holdings.
 */

import { usd, utcDateTime } from "./format.ts";
import type { Activity } from "./sample-data.ts";

export interface InsiderTx {
  insider: string;
  position: string | null;
  is_director: boolean;
  is_officer: boolean;
  is_ten_percent_owner: boolean;
  form: string;
  security: string;
  code: string;
  category: string;
  signal: "discretionary_buy" | "discretionary_sell" | null;
  plan_10b5_1: boolean;
  issues: string[];
  transaction_date: string;
  shares: string;
  price: string | null;
  value: string | null;
  shares_after: string | null;
  ownership: string | null;
  accepted_at: string;
  accession: string;
  filing_url: string;
}

interface Coverage {
  ticker: string;
  cik: number;
  history_since: string;
  last_ingested_at: string;
  missing_filings: number;
  disclaimer: string;
}

export interface InsiderTransactions extends Coverage {
  total: number;
  transactions: InsiderTx[];
}

export interface ScoreComponent {
  name: string;
  points: number;
  max_points: number;
  available: boolean;
  detail: string;
}

export interface InsiderScore extends Coverage {
  as_of: string;
  window_days: number;
  score: number;
  explanation: string;
  components: ScoreComponent[];
  coverage: number;
  discretionary_buys: { transactions: number; insiders: number; value: string };
  discretionary_sells: { transactions: number; insiders: number; value: string };
  not_counted: Record<string, number>;
}

export interface OwnershipFiling {
  accession: string;
  form: string;
  schedule: "13D" | "13G";
  schedule_meaning: string;
  holder: string;
  event_date: string | null;
  accepted_at: string;
  shares: string | null;
  percent: string | null;
  above_5_percent: boolean | null;
  /** False for filings before December 2024: no machine-readable figures, only the document. */
  structured: boolean;
  filing_url: string;
  change: { since_filed_date: string; shares: string | null; percent_points: string | null; notes: string[] } | null;
}

export interface Ownership extends Coverage {
  issuer: string;
  holders?: OwnershipFiling[];
  filings?: OwnershipFiling[];
  total?: number;
}

export interface JobRun {
  job: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  targets: Record<string, unknown> | null;
}

export interface Jobs {
  enabled: boolean;
  jobs: Record<string, { every_minutes: number; targets: number; last_run: JobRun | null; next_due: string }>;
  recent_runs: JobRun[];
}

export interface JobHealth {
  every_minutes: number;
  targets: number;
  last_run: { started_at: string; finished_at: string | null; status: string } | null;
  last_success: { started_at: string; finished_at: string | null } | null;
  last_failure: { started_at: string; error?: string | null } | null;
  running: unknown;
  interrupted: boolean;
  next_due: string | null;
  overdue: boolean;
}

export interface IngestionHealth {
  status: "healthy" | "degraded" | "unhealthy" | "disabled";
  scheduler?: string;
  checked_at: string;
  problems: string[];
  database: string;
  ingesting_now?: boolean | null;
  jobs?: Record<string, JobHealth>;
}

export interface Manager {
  cik: number;
  name: string;
  history_since: string;
  last_ingested_at: string;
  latest_period: string | null;
  missing_filings: number;
}

export interface HoldingChange {
  cusip: string;
  issuer_name: string;
  title_of_class: string;
  previous_shares: string | null;
  shares: string | null;
  status: string;
  change_pct: number | null;
  value: string;
  note: string;
}

export interface ManagerChanges {
  institution: string;
  manager_cik: number;
  period: string;
  previous_period: string;
  disclosed_at: string;
  filings: string[];
  confidential_positions_omitted: boolean;
  option_rows_not_shown: number;
  total: number;
  changes: HoldingChange[];
  disclaimer: string;
}

/** The tickers the scheduler ingests, read from the last insider and 13D/13G runs. Empty if none ran. */
export function watchlist(jobs: Jobs): string[] {
  const names = ["insider", "beneficial"].flatMap((j) => Object.keys(jobs.jobs[j]?.last_run?.targets ?? {}));
  return [...new Set(names)];
}

export const CATEGORY: Record<string, string> = {
  open_market_purchase: "Open-market purchase",
  open_market_sale: "Open-market sale",
  acquisition_from_issuer: "Grant or award",
  disposition_to_issuer: "Returned to the company",
  tax_withholding: "Tax withholding",
  option_exercise: "Option exercise",
  conversion: "Conversion",
  gift: "Gift",
  inheritance: "Inheritance",
  planned_purchase: "10b5-1 plan purchase",
  planned_sale: "10b5-1 plan sale",
  third_party_managed: "Managed by a third party",
  sale_to_cover_taxes: "Sale to cover taxes",
  non_open_market_purchase: "Private purchase",
  non_open_market_sale: "Private sale",
  sale_linked_to_exercise: "Sale after exercise",
  derivative_purchase: "Derivative purchase",
  derivative_sale: "Derivative sale",
  holding: "Holding report",
  other: "Other",
  unknown: "Unclassified",
};

export function categoryLabel(category: string): string {
  return CATEGORY[category] ?? category.replaceAll("_", " ");
}

/** Decimal strings from the API, for display only. */
export function shares(text: string | null): string {
  return text === null ? "unknown" : Number(text).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function role(t: Pick<InsiderTx, "position" | "is_director" | "is_officer" | "is_ten_percent_owner">): string {
  const parts = [t.position, t.is_director && !/director/i.test(t.position ?? "") ? "Director" : null, t.is_ten_percent_owner ? "10% owner" : null];
  return parts.filter(Boolean).join(", ") || (t.is_officer ? "Officer" : "Reporting person");
}

/** A real feed item: the Activity shape plus the SEC filing it came from. */
export interface Disclosure extends Activity {
  url: string;
}

const INSIDER_NOTE =
  "Only open-market purchases and sales count as signals; grants, exercises, tax withholding, gifts and plan trades never do. A delayed public disclosure: not evidence of wrongdoing, and not a prediction.";

/**
 * One feed item per filing, person and direction: a Form 4 often splits one decision into many
 * lots, which would otherwise flood the feed. Totals are exact sums of the reported rows.
 */
export function insiderDisclosures(ticker: string, txs: InsiderTx[]): Disclosure[] {
  const groups = new Map<string, InsiderTx[]>();
  for (const t of txs) {
    const key = `${t.accession}|${t.insider}|${t.signal}`;
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }
  return [...groups.values()].map((rows) => {
    const t = rows[0];
    const buy = t.signal === "discretionary_buy";
    const total = rows.reduce((n, r) => n + Number(r.shares), 0);
    const priced = rows.filter((r) => r.value !== null);
    const value = priced.reduce((n, r) => n + Number(r.value), 0);
    const prices = rows.map((r) => (r.price === null ? null : Number(r.price))).filter((x): x is number => x !== null && x > 0);
    const lo = Math.min(...prices), hi = Math.max(...prices);
    const dates = [...new Set(rows.map((r) => r.transaction_date))].sort();
    const n = rows.length;
    return {
      id: `insider-${t.accession}-${t.insider}-${t.signal}`,
      kind: "insider",
      asset: ticker,
      title: `${t.insider} ${buy ? "bought" : "sold"} ${shares(String(total))} shares${n > 1 ? ` in ${n} trades` : ""}`,
      time: t.accepted_at,
      source: `SEC Form ${t.form}, public ${utcDateTime(t.accepted_at)}`,
      evidence: [
        role(t),
        `${categoryLabel(t.category)}${dates.length > 1 ? ` from ${dates[0]} to ${dates[dates.length - 1]}` : ` on ${dates[0]}`}: ${shares(String(total))} shares` +
          (prices.length ? ` at ${lo === hi ? usd(lo) : `${usd(lo)} to ${usd(hi)}`}` : "") +
          (priced.length === n ? ` (${usd(value, 0)})` : ""),
        ...(rows[rows.length - 1].shares_after !== null
          ? [`Holds ${shares(rows[rows.length - 1].shares_after)} shares after the last reported row (${t.ownership === "I" ? "indirectly" : "directly"})`]
          : []),
        `Filing ${t.accession}`,
      ],
      explanation: INSIDER_NOTE,
      severity: buy ? "notable" : "info",
      url: t.filing_url,
    };
  });
}

export function changeText(f: OwnershipFiling): string | null {
  if (!f.change) return null;
  const pp = f.change.percent_points === null ? null : Number(f.change.percent_points);
  const sh = f.change.shares === null ? null : Number(f.change.shares);
  const parts = [
    pp !== null ? `${pp > 0 ? "+" : ""}${pp.toFixed(2)} percentage points` : null,
    sh !== null ? `${sh > 0 ? "+" : ""}${sh.toLocaleString("en-US", { maximumFractionDigits: 0 })} shares` : null,
  ].filter(Boolean);
  return parts.length ? `${parts.join(", ")} since the ${f.change.since_filed_date} filing` : null;
}

export function ownershipDisclosure(ticker: string, f: OwnershipFiling): Disclosure {
  const change = changeText(f);
  return {
    id: `ownership-${f.accession}`,
    kind: "ownership",
    asset: ticker,
    title: `${f.holder} filed ${f.form}${f.percent !== null ? `: ${Number(f.percent).toFixed(1)}%` : ""}`,
    time: f.accepted_at,
    source: `SEC Schedule ${f.schedule}, public ${utcDateTime(f.accepted_at)}`,
    evidence: [
      `${f.schedule}: ${f.schedule_meaning}`,
      `${shares(f.shares)} shares${f.percent !== null ? ` (${Number(f.percent).toFixed(2)}% of the class)` : ""}${f.event_date ? ` as of ${f.event_date}` : ""}`,
      ...(change ? [change] : []),
      `Filing ${f.accession}`,
    ],
    explanation:
      "Holders above 5% must file Schedule 13D (may seek influence) or 13G (passive). A delayed disclosure as of the event date, not current holdings.",
    severity: f.schedule === "13D" ? "notable" : "info",
    url: f.filing_url,
  };
}

/** Backend problem strings carry raw ISO times; show them the way the rest of the page does. */
export function readableProblem(text: string): string {
  return text.replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})/g, (iso) => utcDateTime(iso));
}

/** Newest public disclosures first, across companies and sources. */
export function newestFirst(items: Disclosure[], limit: number): Disclosure[] {
  return [...items].sort((a, b) => b.time.localeCompare(a.time)).slice(0, limit);
}
