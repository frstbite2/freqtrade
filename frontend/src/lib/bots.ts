/**
 * The AI bot identities: what each one is meant to do, and what really exists today.
 * Nothing here is a performance figure. Demo statistics live in sample-data.ts, clearly labelled.
 */

export type BotId = "grok-sniper" | "momentum-hunter" | "dip-hunter" | "whale-watcher" | "insider";

/** Where the real implementation stands. Shown in live mode instead of invented numbers. */
export type BuildState =
  | { kind: "not_built"; milestone: string }
  | { kind: "data_ready"; milestone: string; data: string }
  | { kind: "no_provider"; needs: string };

export interface BotIdentity {
  id: BotId;
  name: string;
  icon: "crosshair" | "rocket" | "anchor" | "waves" | "landmark";
  tagline: string;
  strategy: string;
  focus: string[];
  signals: string[];
  dataSources: string[];
  /** Two gradient stops and a glow colour (as "r g b") for the card. */
  g1: string;
  g2: string;
  glow: string;
  build: BuildState;
}

export const BOTS: BotIdentity[] = [
  {
    id: "grok-sniper",
    name: "Grok Sniper",
    icon: "crosshair",
    tagline: "Early breakout detection",
    strategy: "Breakout momentum",
    focus: ["Early breakouts", "Momentum and volume", "Entry points"],
    signals: ["Range breakouts on rising volume", "Relative-volume spikes", "Volatility contraction then expansion"],
    dataSources: ["Market data (Alpaca)", "Technical analysis engine"],
    g1: "#ff8a3d",
    g2: "#ff5fa2",
    glow: "255 138 61",
    build: { kind: "not_built", milestone: "M6 AI engine" },
  },
  {
    id: "momentum-hunter",
    name: "Momentum Hunter",
    icon: "rocket",
    tagline: "Strong trend tracking",
    strategy: "Trend following",
    focus: ["Strong trends", "Price action and volume", "Trend strength"],
    signals: ["Higher highs and higher lows", "ADX trend strength", "Moving-average alignment"],
    dataSources: ["Market data (Alpaca)", "Technical analysis engine"],
    g1: "#38c8ff",
    g2: "#6e7bff",
    glow: "56 200 255",
    build: { kind: "not_built", milestone: "M6 AI engine" },
  },
  {
    id: "dip-hunter",
    name: "Dip Hunter",
    icon: "anchor",
    tagline: "Oversold reversal scouting",
    strategy: "Mean reversion",
    focus: ["Oversold conditions", "RSI and support levels", "Possible reversals"],
    signals: ["RSI below 30 near support", "Bullish reversal candles", "Volume capitulation"],
    dataSources: ["Market data (Alpaca)", "Technical analysis engine"],
    g1: "#36e3a1",
    g2: "#38c8ff",
    glow: "54 227 161",
    build: { kind: "not_built", milestone: "M6 AI engine" },
  },
  {
    id: "whale-watcher",
    name: "Whale Watcher",
    icon: "waves",
    tagline: "Large-holder flow monitor",
    strategy: "On-chain flow",
    focus: ["Large blockchain transactions", "Accumulation and distribution", "Unusual activity"],
    signals: ["Transfers above a size threshold", "Exchange inflow and outflow", "Wallet clustering"],
    dataSources: ["On-chain data provider (none connected)"],
    g1: "#a46bff",
    g2: "#6e7bff",
    glow: "164 107 255",
    build: { kind: "no_provider", needs: "an on-chain data provider" },
  },
  {
    id: "insider",
    name: "Insider Intelligence",
    icon: "landmark",
    tagline: "SEC filings and ownership",
    strategy: "Disclosure analysis",
    focus: ["SEC insider filings", "Institutional ownership changes", "Notable buying and selling"],
    signals: ["Open-market insider purchases (Form 4)", "13F position changes", "13D/13G stakes above 5%"],
    dataSources: ["SEC EDGAR: Forms 3/4/5, 13F, 13D/13G (live in the backend)"],
    g1: "#ffc65c",
    g2: "#ff8a3d",
    glow: "255 198 92",
    build: {
      kind: "data_ready",
      milestone: "M6 AI engine",
      data: "SEC filings are ingested and scored today; the trading strategy is not built yet.",
    },
  },
];

export function buildLabel(build: BuildState): string {
  switch (build.kind) {
    case "not_built":
      return `Strategy not built yet (${build.milestone})`;
    case "data_ready":
      return `Data live, strategy pending (${build.milestone})`;
    case "no_provider":
      return `Needs ${build.needs}`;
  }
}
