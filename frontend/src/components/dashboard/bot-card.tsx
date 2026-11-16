"use client";

import { ChevronDown, Radar } from "lucide-react";
import { useState } from "react";
import { Sparkline } from "@/components/charts/sparkline";
import { BotIcon } from "@/components/ui/bot-icon";
import { Chip, DemoBadge, StatusDot } from "@/components/ui/badges";
import { TokenIcon } from "@/components/ui/token-icon";
import { Unavailable } from "@/components/ui/states";
import { type BotIdentity, buildLabel } from "@/lib/bots";
import { useDataMode } from "@/lib/data-mode";
import { signedPct, signedUsd } from "@/lib/format";
import { BOT_DEMO, TICKERS } from "@/lib/sample-data";
import { BotDetails } from "./bot-details";

/** Below this many completed trades a win rate says more about luck than skill, so it is hidden. */
export const MIN_TRADES_FOR_WIN_RATE = 30;

const colorOf = (symbol: string) => TICKERS.find((t) => t.symbol === symbol)?.color ?? "#a46bff";

export function BotCard({ bot, index = 0 }: { bot: BotIdentity; index?: number }) {
  const { mode } = useDataMode();
  const demo = mode === "demo";
  const stats = BOT_DEMO[bot.id];
  const [expanded, setExpanded] = useState(false);
  const [details, setDetails] = useState(false);
  const status = demo ? stats.status : "offline";

  return (
    <article
      className="card card-hover glow-ring flex animate-rise flex-col overflow-hidden p-5"
      style={{ ["--g1" as string]: bot.g1, ["--g2" as string]: bot.g2, ["--glow" as string]: bot.glow, animationDelay: `${index * 70}ms` }}
      aria-labelledby={`bot-${bot.id}`}
    >
      <div className="pointer-events-none absolute -right-10 -top-12 size-40 rounded-full opacity-30 blur-3xl" style={{ background: bot.g1 }} />
      {demo && status === "analyzing" && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px overflow-hidden">
          <div className="h-px w-1/3 animate-scan" style={{ background: `linear-gradient(90deg, transparent, ${bot.g1}, transparent)` }} />
        </div>
      )}

      <header className="relative flex items-start gap-3">
        <div className="relative">
          <BotIcon bot={bot} />
          {demo && status !== "idle" && (
            <span className="absolute -inset-1 animate-pulse-ring rounded-2xl" style={{ boxShadow: `0 0 0 2px ${bot.g1}` }} aria-hidden />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h3 id={`bot-${bot.id}`} className="truncate font-display text-base font-semibold text-ink">{bot.name}</h3>
          <p className="truncate text-xs text-ink-3">{bot.tagline}</p>
        </div>
        {demo ? <DemoBadge /> : null}
      </header>

      <div className="relative mt-4 flex flex-wrap items-center justify-between gap-2">
        <StatusDot status={status} />
        <Chip tone="neutral">{bot.strategy}</Chip>
      </div>

      <div className="relative mt-4">
        <p className="text-[11px] font-medium uppercase tracking-wider text-ink-3">Monitoring</p>
        {demo ? (
          <div className="mt-1.5 flex items-center gap-1.5">
            {stats.monitoring.map((s) => (
              <span key={s} className="flex items-center gap-1.5 rounded-full border border-line bg-white/[0.03] py-0.5 pl-0.5 pr-2.5 text-xs font-medium text-ink-2">
                <TokenIcon symbol={s} color={colorOf(s)} size={20} />
                {s}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-1.5 text-xs text-ink-3">Nothing: the bot is not running.</p>
        )}
      </div>

      <div className="relative mt-4 grid grid-cols-3 gap-2 rounded-2xl border border-line bg-black/20 p-3">
        <Metric label="Sim. P&L">
          {demo ? (
            <span className={stats.pnl >= 0 ? "text-mint" : "text-rose"}>{signedUsd(stats.pnl, 0)}</span>
          ) : (
            <span className="text-ink-3">—</span>
          )}
        </Metric>
        <Metric label="Win rate">
          {demo && stats.trades >= MIN_TRADES_FOR_WIN_RATE ? (
            `${stats.winRatePct}%`
          ) : (
            <span className="text-[11px] font-medium leading-tight text-ink-3" title={`Shown once ${MIN_TRADES_FOR_WIN_RATE}+ verified trades exist`}>
              {demo ? `needs ${MIN_TRADES_FOR_WIN_RATE}+` : "—"}
            </span>
          )}
        </Metric>
        <Metric label="Trades">{demo ? stats.trades : <span className="text-ink-3">0</span>}</Metric>
      </div>

      <div className="relative mt-4 flex h-12 items-end">
        {demo ? (
          <div className="flex w-full items-end justify-between gap-3">
            <Sparkline values={stats.spark.map((p) => p.v)} color={stats.pnlPct >= 0 ? bot.g1 : "#ff5c7a"} width={180} height={44} className="h-11 w-full max-w-[200px]" />
            <span className={`tabular shrink-0 text-sm font-semibold ${stats.pnlPct >= 0 ? "text-mint" : "text-rose"}`}>{signedPct(stats.pnlPct, 1)}</span>
          </div>
        ) : (
          <Unavailable reason={buildLabel(bot.build)} compact />
        )}
      </div>

      {demo && (
        <p className="relative mt-3 flex items-center gap-1.5 truncate text-xs text-ink-2">
          <Radar className="size-3.5 shrink-0" style={{ color: bot.g1 }} aria-hidden />
          {stats.lastAction}
        </p>
      )}

      <div className={`relative grid transition-all duration-300 ${expanded ? "mt-4 grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
        <div className="overflow-hidden">
          <div className="space-y-3 border-t border-line pt-4 text-xs">
            <List title="Looks for" items={bot.focus} color={bot.g1} />
            <List title="Signals" items={bot.signals} color={bot.g2} />
            <p className="rounded-xl border border-line bg-white/[0.03] px-3 py-2 text-ink-3">
              <span className="font-semibold text-ink-2">Real status: </span>
              {buildLabel(bot.build)}
            </p>
          </div>
        </div>
      </div>

      <footer className="relative mt-auto flex items-center gap-2 pt-5">
        <button
          type="button"
          onClick={() => setDetails(true)}
          className="flex-1 rounded-xl px-3 py-2 text-sm font-semibold text-white transition-transform hover:scale-[1.02] active:scale-[0.98]"
          style={{ background: `linear-gradient(120deg, ${bot.g1}, ${bot.g2})`, boxShadow: `0 10px 30px -12px rgb(${bot.glow} / 0.9)` }}
        >
          View details
        </button>
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-label={expanded ? "Show less" : "Show more"}
          className="flex size-9 items-center justify-center rounded-xl border border-line-strong text-ink-2 transition-colors hover:bg-white/5 hover:text-ink"
        >
          <ChevronDown className={`size-4 transition-transform duration-300 ${expanded ? "rotate-180" : ""}`} />
        </button>
      </footer>

      <BotDetails bot={bot} open={details} onClose={() => setDetails(false)} />
    </article>
  );
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-medium uppercase tracking-wider text-ink-3">{label}</p>
      <p className="tabular mt-0.5 font-display text-sm font-semibold leading-tight text-ink">{children}</p>
    </div>
  );
}

function List({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <div>
      <p className="mb-1 font-semibold text-ink-2">{title}</p>
      <ul className="space-y-1 text-ink-3">
        {items.map((i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-1.5 size-1 shrink-0 rounded-full" style={{ background: color }} />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}
