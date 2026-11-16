"use client";

import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import { SectionHeader } from "@/components/ui/section";
import { OfflineState, SkeletonRows } from "@/components/ui/states";
import { LiveBadge } from "@/components/ui/badges";
import { type PlatformStatus, usePlatform } from "@/lib/platform";

const LABELS: Record<string, string> = {
  sec_edgar: "SEC EDGAR (filings)",
  alpaca: "Alpaca (market data, paper broker)",
  polygon: "Polygon",
  finnhub: "Finnhub (news)",
  alpha_vantage: "Alpha Vantage",
  fmp: "Financial Modeling Prep",
  tradier: "Tradier (options)",
  coinbase: "Coinbase",
  api_auth: "API authentication",
};

/** Real: which data providers the backend has credentials for. Shown in both modes. */
export function SourceStatus({ only }: { only?: string[] }) {
  const status = usePlatform<PlatformStatus>("api/v1/status");
  return (
    <section className="card p-5 sm:p-6">
      <SectionHeader title="Data sources" subtitle="Read from the platform API just now" right={<LiveBadge />} />
      {status.state === "loading" ? (
        <SkeletonRows rows={3} />
      ) : status.state === "offline" ? (
        <OfflineState what="Data-source status" />
      ) : status.state === "unavailable" ? (
        <p className="text-sm text-ink-3">The platform API answered {status.message}.</p>
      ) : (
        <ul className="space-y-2">
          {Object.entries(status.data.providers_configured)
            .filter(([k]) => !only || only.includes(k))
            .map(([k, ok]) => (
              <li key={k} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-black/15 px-3 py-2.5 text-sm">
                <span className="text-ink-2">{LABELS[k] ?? k}</span>
                {ok ? (
                  <span className="inline-flex items-center gap-1.5 text-mint"><CheckCircle2 className="size-4" aria-hidden /> Configured</span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-ink-3"><XCircle className="size-4" aria-hidden /> Not configured</span>
                )}
              </li>
            ))}
          <li className="flex items-center gap-2 pt-1 text-xs text-ink-3">
            <CircleDashed className="size-3.5" aria-hidden /> Trading mode reported by the backend: <span className="font-semibold text-mint">{status.data.trading_mode}</span>
          </li>
        </ul>
      )}
    </section>
  );
}
