"use client";

import { Bot, Briefcase, PiggyBank, TrendingUp, Wallet } from "lucide-react";
import type { ReactNode } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { DemoBadge } from "@/components/ui/badges";
import { Unavailable } from "@/components/ui/states";
import { BOTS } from "@/lib/bots";
import { useDataMode } from "@/lib/data-mode";
import { signedPct, signedUsd, usd } from "@/lib/format";
import { BOT_DEMO, PORTFOLIO } from "@/lib/sample-data";

function Tile({
  icon,
  label,
  from,
  to,
  children,
  sub,
  demo,
}: {
  icon: ReactNode;
  label: string;
  from: string;
  to: string;
  children: ReactNode;
  sub?: ReactNode;
  demo: boolean;
}) {
  return (
    <div className="card card-hover group overflow-hidden p-4 sm:p-5" style={{ ["--glow" as string]: hexToRgb(to) }}>
      <div className="pointer-events-none absolute -right-8 -top-10 size-28 rounded-full opacity-25 blur-2xl transition-opacity group-hover:opacity-45" style={{ background: to }} />
      <div className="relative flex items-center justify-between">
        <span className="flex size-9 items-center justify-center rounded-xl text-white" style={{ background: `linear-gradient(140deg, ${from}, ${to})`, boxShadow: `0 8px 24px -10px ${to}` }}>
          {icon}
        </span>
        {demo && <DemoBadge />}
      </div>
      <p className="relative mt-4 text-xs font-medium text-ink-3">{label}</p>
      <div className="relative mt-1 min-h-8 font-display text-xl font-bold tracking-tight text-ink sm:text-2xl">{children}</div>
      {sub && <div className="relative mt-1 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

export function StatGrid() {
  const { mode } = useDataMode();
  const demo = mode === "demo";
  const running = Object.values(BOT_DEMO).filter((b) => b.status !== "idle").length;
  const noBroker = "Needs the paper broker (M7)";

  return (
    <section aria-label="Key figures" className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-5">
      <Tile icon={<TrendingUp className="size-4" />} label="Daily profit and loss" from="#36e3a1" to="#38c8ff" demo={demo}
        sub={demo ? signedPct(PORTFOLIO.dailyPnlPct) + " today" : undefined}>
        {demo ? (
          <AnimatedNumber value={PORTFOLIO.dailyPnl} format={(n) => signedUsd(n)} className={PORTFOLIO.dailyPnl >= 0 ? "text-mint" : "text-rose"} />
        ) : (
          <Unavailable reason={noBroker} compact />
        )}
      </Tile>
      <Tile icon={<PiggyBank className="size-4" />} label="Overall return" from="#a46bff" to="#ff5fa2" demo={demo}
        sub={demo ? `from ${usd(PORTFOLIO.startingBalance, 0)} starting balance` : undefined}>
        {demo ? <AnimatedNumber value={PORTFOLIO.totalReturnPct} format={(n) => signedPct(n)} /> : <Unavailable reason={noBroker} compact />}
      </Tile>
      <Tile icon={<Wallet className="size-4" />} label="Available paper balance" from="#ffc65c" to="#ff8a3d" demo={demo}
        sub={demo ? `${PORTFOLIO.cashPct.toFixed(1)}% of the portfolio in cash` : undefined}>
        {demo ? <AnimatedNumber value={PORTFOLIO.cash} format={(n) => usd(n)} /> : <Unavailable reason={noBroker} compact />}
      </Tile>
      <Tile icon={<Bot className="size-4" />} label="Active AI bots" from="#38c8ff" to="#6e7bff" demo={demo}
        sub={demo ? "running or analyzing" : "no strategy is built yet (M6)"}>
        {demo ? `${running} / ${BOTS.length}` : `0 / ${BOTS.length}`}
      </Tile>
      <Tile icon={<Briefcase className="size-4" />} label="Open simulated positions" from="#ff8a3d" to="#ff5fa2" demo={demo}
        sub={demo ? "across crypto and stocks" : undefined}>
        {demo ? PORTFOLIO.openPositions : <Unavailable reason={noBroker} compact />}
      </Tile>
    </section>
  );
}
