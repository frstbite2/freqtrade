/**
 * What each bot can really do today, from live backend facts. No performance is ever derived
 * here: trades and P&L appear only once the paper broker (Milestone 7) records them.
 */

import { type BotIdentity, buildLabel } from "./bots.ts";
import { ago } from "./format.ts";
import type { IngestionHealth } from "./sec.ts";

export interface Facts {
  /** providers_configured from GET /api/v1/status; null when the backend could not be read. */
  providers: Record<string, boolean> | null;
  /** GET /api/v1/health/ingestion (a 503 still carries it); null when unavailable. */
  ingestion: IngestionHealth | null;
}

export type Readiness = { label: string; state: "ready" | "stale" | "missing" | "unknown"; detail: string };

export function readiness(bot: BotIdentity, facts: Facts, now: number): Readiness[] {
  const rows = bot.needs.map((need): Readiness => {
    if (need === "market_data") {
      if (!facts.providers) return { label: "Market data", state: "unknown", detail: "backend not reachable" };
      return facts.providers.alpaca
        ? { label: "Market data", state: "ready", detail: "Alpaca keys configured (live verification pending)" }
        : { label: "Market data", state: "missing", detail: "Alpaca keys not configured" };
    }
    if (need === "onchain") return { label: "On-chain data", state: "missing", detail: "no provider connected" };
    const job = facts.ingestion?.jobs?.insider;
    if (!job) return { label: "SEC filings", state: "unknown", detail: "ingestion status unavailable" };
    if (!job.last_success) return { label: "SEC filings", state: "missing", detail: "never ingested" };
    const when = ago(job.last_success.started_at, now);
    return job.overdue
      ? { label: "SEC filings", state: "stale", detail: `last update ${when}, overdue` }
      : { label: "SEC filings", state: "ready", detail: `updated ${when}` };
  });
  return [...rows, { label: "Strategy", state: "missing", detail: buildLabel(bot.build) }];
}
