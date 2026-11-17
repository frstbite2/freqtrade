"use client";

import { ShieldCheck } from "lucide-react";
import { LiveBadge } from "@/components/ui/badges";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section";
import { ErrorState, OfflineState, SkeletonRows } from "@/components/ui/states";
import { usePlatform } from "@/lib/platform";

interface RiskConfig {
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_weekly_loss_pct: number;
  max_drawdown_pct: number;
  max_open_positions: number;
  max_portfolio_exposure_pct: number;
  max_asset_exposure_pct: number;
  consecutive_losses_before_cooldown: number;
  cooldown_minutes: number;
}

/** Each limit, with the ceiling the backend's validation allows, so the gauge shows how tight it is. */
const GAUGES: { key: keyof RiskConfig; label: string; ceiling: number; unit: "%" | "" | "min"; color: string; help: string }[] = [
  { key: "risk_per_trade_pct", label: "Risk per trade", ceiling: 5, unit: "%", color: "#36e3a1", help: "Most of the portfolio a single trade may lose." },
  { key: "max_daily_loss_pct", label: "Daily loss limit", ceiling: 20, unit: "%", color: "#38c8ff", help: "Trading stops for the day past this loss." },
  { key: "max_weekly_loss_pct", label: "Weekly loss limit", ceiling: 40, unit: "%", color: "#6e7bff", help: "Trading stops for the week past this loss." },
  { key: "max_drawdown_pct", label: "Maximum drawdown", ceiling: 60, unit: "%", color: "#a46bff", help: "Fall from the peak that halts all trading." },
  { key: "max_portfolio_exposure_pct", label: "Portfolio exposure", ceiling: 100, unit: "%", color: "#ff8a3d", help: "Share of the portfolio that may be invested at once." },
  { key: "max_asset_exposure_pct", label: "Per-asset exposure", ceiling: 100, unit: "%", color: "#ff5fa2", help: "Share any one asset may take." },
];

export function RiskView() {
  const config = usePlatform<{ risk: RiskConfig }>("api/v1/config");
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Safety"
        title="Risk management"
        subtitle="Hard limits enforced by an independent risk engine. The AI can never override them."
      />
      <section className="card p-5 sm:p-6">
        <SectionHeader title="Configured limits" subtitle="From the backend's risk settings (config/risk.yaml)" right={<LiveBadge />} />
        {config.state === "loading" ? (
          <SkeletonRows rows={3} />
        ) : config.state === "offline" ? (
          <OfflineState what="The risk configuration" />
        ) : config.state === "unavailable" ? (
          <ErrorState title="Risk settings unavailable" detail={`The platform API answered ${config.message}.`} />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {GAUGES.map((g) => (
                <Gauge key={g.key} label={g.label} value={config.data.risk[g.key]} ceiling={g.ceiling} unit={g.unit} color={g.color} help={g.help} />
              ))}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Fact label="Maximum open positions" value={String(config.data.risk.max_open_positions)} />
              <Fact label="Losing trades before a pause" value={String(config.data.risk.consecutive_losses_before_cooldown)} />
              <Fact label="Pause length" value={`${config.data.risk.cooldown_minutes} min`} />
            </div>
          </>
        )}
      </section>
      <section className="card flex items-start gap-3 p-5 text-sm text-ink-3">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-mint" aria-hidden />
        <p>
          How close the portfolio is to each limit appears once the simulated broker exists (Milestone 7).
          Live trading is switched off in the backend and cannot be turned on from here.
        </p>
      </section>
    </div>
  );
}

function Gauge({ label, value, ceiling, unit, color, help }: { label: string; value: number; ceiling: number; unit: string; color: string; help: string }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const frac = Math.min(1, value / ceiling);
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-line bg-black/20 p-4">
      <svg width="88" height="88" viewBox="0 0 88 88" className="shrink-0 -rotate-90" aria-hidden>
        <circle cx="44" cy="44" r={r} fill="none" stroke="rgb(255 255 255 / 0.06)" strokeWidth="8" />
        <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={`${frac * c} ${c}`} style={{ filter: `drop-shadow(0 0 6px ${color})`, transition: "stroke-dasharray 1s ease" }} />
      </svg>
      <div className="min-w-0">
        <p className="text-xs font-medium text-ink-3">{label}</p>
        <p className="tabular font-display text-2xl font-bold text-ink">{value}{unit}</p>
        <p className="mt-0.5 text-xs leading-snug text-ink-3">{help}</p>
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-line bg-black/15 px-4 py-3">
      <p className="text-xs text-ink-3">{label}</p>
      <p className="tabular font-display text-lg font-semibold text-ink">{value}</p>
    </div>
  );
}
