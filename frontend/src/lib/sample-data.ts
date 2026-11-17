/**
 * SAMPLE DATA for the design prototype (Stage 1). None of it is a market price, a filing, a
 * trade or a result: every screen that shows it carries a DEMO badge, and live mode never uses it.
 *
 * It is generated from a fixed seed, so the server and the browser render the same numbers, and
 * the totals are derived from the parts (portfolio value = holdings + cash, allocations sum to
 * 100%), so the prototype is internally consistent.
 */

import type { BotId } from "./bots.ts";

export const SAMPLE_AS_OF = "2026-11-16T15:00:00Z";
const AS_OF_MS = Date.parse(SAMPLE_AS_OF);
const MINUTE = 60_000;

/** Small deterministic PRNG (mulberry32). */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A random walk of `n` points from `start` to exactly `end`. */
export function walk(seed: number, n: number, start: number, end: number, volatility: number): number[] {
  const next = rng(seed);
  const raw = [0];
  for (let i = 1; i < n; i++) raw.push(raw[i - 1] + (next() - 0.5) * 2);
  const last = raw[n - 1];
  const span = Math.max(Math.abs(start), Math.abs(end), 1);
  return raw.map((r, i) => {
    const t = n === 1 ? 1 : i / (n - 1);
    const drift = start + (end - start) * t;
    const noise = (r - last * t) * volatility * span * 0.01;
    return i === n - 1 ? end : drift + noise;
  });
}

export interface Point {
  t: string;
  v: number;
}

function timed(values: number[], stepMinutes: number): Point[] {
  const n = values.length;
  return values.map((v, i) => ({
    t: new Date(AS_OF_MS - (n - 1 - i) * stepMinutes * MINUTE).toISOString(),
    v,
  }));
}

// --- portfolio ---

export interface Holding {
  symbol: string;
  name: string;
  kind: "crypto" | "stock";
  quantity: number;
  price: number;
  change24hPct: number;
  color: string;
}

const HOLDING_INPUT: Holding[] = [
  { symbol: "BTC", name: "Bitcoin", kind: "crypto", quantity: 0.42, price: 96_420, change24hPct: 2.84, color: "#ff8a3d" },
  { symbol: "ETH", name: "Ethereum", kind: "crypto", quantity: 6.1, price: 3_412.5, change24hPct: 1.92, color: "#6e7bff" },
  { symbol: "SOL", name: "Solana", kind: "crypto", quantity: 85, price: 186.4, change24hPct: 6.71, color: "#a46bff" },
  { symbol: "AAPL", name: "Apple", kind: "stock", quantity: 30, price: 231.6, change24hPct: 0.42, color: "#38c8ff" },
  { symbol: "NVDA", name: "NVIDIA", kind: "stock", quantity: 40, price: 148.2, change24hPct: -0.84, color: "#36e3a1" },
  { symbol: "LINK", name: "Chainlink", kind: "crypto", quantity: 260, price: 18.9, change24hPct: -2.15, color: "#ff5fa2" },
];

export const STARTING_BALANCE = 100_000;
const CASH = 21_840.55;

export interface HoldingView extends Holding {
  value: number;
  dayChange: number;
  allocationPct: number;
}

const holdingValues = HOLDING_INPUT.map((h) => {
  const value = h.quantity * h.price;
  return { ...h, value, dayChange: value - value / (1 + h.change24hPct / 100) };
});
const invested = holdingValues.reduce((s, h) => s + h.value, 0);
const totalValue = invested + CASH;

export const HOLDINGS: HoldingView[] = holdingValues
  .map((h) => ({ ...h, allocationPct: (h.value / totalValue) * 100 }))
  .sort((a, b) => b.value - a.value);

export const PORTFOLIO = {
  totalValue,
  invested,
  cash: CASH,
  cashPct: (CASH / totalValue) * 100,
  dailyPnl: holdingValues.reduce((s, h) => s + h.dayChange, 0),
  get dailyPnlPct() {
    return (this.dailyPnl / (totalValue - this.dailyPnl)) * 100;
  },
  totalReturnPct: (totalValue / STARTING_BALANCE - 1) * 100,
  startingBalance: STARTING_BALANCE,
  openPositions: HOLDING_INPUT.length,
};

export type Timeframe = "1D" | "1W" | "1M" | "3M" | "1Y";
export const TIMEFRAMES: Timeframe[] = ["1D", "1W", "1M", "3M", "1Y"];

const TIMEFRAME_SHAPE: Record<Timeframe, { n: number; step: number; startFactor: number; vol: number; seed: number }> = {
  "1D": { n: 96, step: 15, startFactor: 0, vol: 0.35, seed: 11 },
  "1W": { n: 84, step: 120, startFactor: 0.952, vol: 0.9, seed: 12 },
  "1M": { n: 90, step: 480, startFactor: 0.917, vol: 1.6, seed: 13 },
  "3M": { n: 90, step: 1440, startFactor: 0.874, vol: 2.4, seed: 14 },
  "1Y": { n: 104, step: 5040, startFactor: STARTING_BALANCE / totalValue, vol: 3.2, seed: 15 },
};

export function portfolioSeries(tf: Timeframe): Point[] {
  const s = TIMEFRAME_SHAPE[tf];
  const start = tf === "1D" ? totalValue - PORTFOLIO.dailyPnl : totalValue * s.startFactor;
  return timed(walk(s.seed, s.n, start, totalValue, s.vol), s.step);
}

// --- bots (demo statistics only) ---

export type BotStatus = "active" | "analyzing" | "idle";

export interface BotDemo {
  status: BotStatus;
  monitoring: string[];
  pnl: number;
  pnlPct: number;
  winRatePct: number;
  trades: number;
  spark: Point[];
  lastAction: string;
}

const BOT_INPUT: Record<BotId, Omit<BotDemo, "spark"> & { seed: number }> = {
  "grok-sniper": { status: "active", monitoring: ["SOL", "AVAX", "NVDA"], pnl: 3_284.1, pnlPct: 13.1, winRatePct: 61, trades: 47, lastAction: "Watching SOL range high", seed: 21 },
  "momentum-hunter": { status: "analyzing", monitoring: ["BTC", "ETH", "AMD"], pnl: 2_051.75, pnlPct: 8.2, winRatePct: 57, trades: 32, lastAction: "Scoring trend strength on BTC", seed: 22 },
  "dip-hunter": { status: "idle", monitoring: ["LINK", "AAPL", "DOGE"], pnl: -412.3, pnlPct: -1.6, winRatePct: 48, trades: 21, lastAction: "No oversold setups right now", seed: 23 },
  "whale-watcher": { status: "analyzing", monitoring: ["BTC", "ETH", "SOL"], pnl: 1_190.4, pnlPct: 4.8, winRatePct: 55, trades: 18, lastAction: "Tracking a large ETH transfer", seed: 24 },
  insider: { status: "active", monitoring: ["NVDA", "AAPL", "MSFT"], pnl: 1_746.2, pnlPct: 7.0, winRatePct: 63, trades: 26, lastAction: "Reviewing a Form 4 purchase", seed: 25 },
};

export const BOT_DEMO: Record<BotId, BotDemo> = Object.fromEntries(
  Object.entries(BOT_INPUT).map(([id, b]) => {
    const { seed, ...rest } = b;
    return [id, { ...rest, spark: timed(walk(seed, 40, 0, b.pnlPct, 2.2), 1080) }];
  }),
) as Record<BotId, BotDemo>;

// --- activity feed ---

export type ActivityKind = "signal" | "insider" | "risk" | "whale" | "system" | "ownership";

export interface Activity {
  id: string;
  kind: ActivityKind;
  asset: string;
  title: string;
  bot?: BotId;
  time: string;
  source: string;
  evidence: string[];
  explanation: string;
  severity: "info" | "notable" | "warning";
}

const ago = (minutes: number) => new Date(AS_OF_MS - minutes * MINUTE).toISOString();

export const ACTIVITY: Activity[] = [
  {
    id: "a1", kind: "signal", asset: "SOL", title: "Unusual volume detected", bot: "grok-sniper", time: ago(3), severity: "notable",
    source: "Technical analysis engine (sample)",
    evidence: ["15-min volume 3.4x its 20-bar average", "Price pressing a 6-day range high", "Spread steady: no sign of a thin book"],
    explanation: "Heavy volume while price tests the top of its range often comes before a breakout attempt. It is a setup to watch, not a prediction.",
  },
  {
    id: "a2", kind: "signal", asset: "BTC", title: "Momentum strengthening", bot: "momentum-hunter", time: ago(11), severity: "info",
    source: "Technical analysis engine (sample)",
    evidence: ["ADX(14) rose from 21 to 28", "Price above the 20, 50 and 200-period EMAs", "Third higher low this week"],
    explanation: "Trend-strength readings are rising and the moving averages are stacked upward: the conditions trend-following strategies look for.",
  },
  {
    id: "a3", kind: "insider", asset: "NVDA", title: "Notable executive purchase detected", bot: "insider", time: ago(26), severity: "notable",
    source: "SEC EDGAR Form 4 (sample filing)",
    evidence: ["Open-market purchase (code P), not a grant or option exercise", "Director bought 12,000 shares", "Filed two days after the trade, as Form 4 requires"],
    explanation: "Open-market purchases by insiders are delayed public disclosures. They are one input among many, never a sign of anything improper.",
  },
  {
    id: "a4", kind: "risk", asset: "Portfolio", title: "Volatility above normal threshold", time: ago(42), severity: "warning",
    source: "Risk monitor (sample)",
    evidence: ["SOL 20-day volatility at 78% annualised (threshold 65%)", "SOL is 13.6% of the portfolio"],
    explanation: "When an asset moves more than usual, the same position carries more risk. Position sizes for new trades would shrink until volatility settles.",
  },
  {
    id: "a5", kind: "signal", asset: "ETH", title: "Potential support retest", bot: "dip-hunter", time: ago(58), severity: "info",
    source: "Technical analysis engine (sample)",
    evidence: ["Price within 1.2% of a support level tested three times", "RSI(14) at 41, falling", "Volume declining into the level"],
    explanation: "Price is drifting back to a level where buyers stepped in before. Whether it holds is unknown; a reversal setup needs confirmation.",
  },
  {
    id: "a6", kind: "whale", asset: "ETH", title: "Large transfer to an exchange", bot: "whale-watcher", time: ago(73), severity: "notable",
    source: "On-chain monitor (sample; no provider connected)",
    evidence: ["18,400 ETH moved from a long-dormant wallet", "Destination tagged as an exchange deposit address"],
    explanation: "Large deposits to exchanges can precede selling, but transfers have many innocent explanations. Treated as context, not a signal on its own.",
  },
  {
    id: "a7", kind: "system", asset: "SEC", title: "Filing ingestion completed", time: ago(95), severity: "info",
    source: "Scheduler (sample)",
    evidence: ["5 watchlist companies checked", "3 new Form 4 filings stored", "0 failures"],
    explanation: "The scheduler checked SEC EDGAR for new filings on the watchlist and stored what it found.",
  },
];

// --- trades (demo) ---

export interface Trade {
  id: string;
  time: string;
  bot: BotId;
  side: "buy" | "sell";
  symbol: string;
  quantity: number;
  price: number;
  pnl?: number;
}

export const TRADES: Trade[] = [
  { id: "t1", time: ago(18), bot: "grok-sniper", side: "buy", symbol: "SOL", quantity: 25, price: 183.9 },
  { id: "t2", time: ago(64), bot: "momentum-hunter", side: "buy", symbol: "BTC", quantity: 0.05, price: 95_880 },
  { id: "t3", time: ago(132), bot: "dip-hunter", side: "sell", symbol: "LINK", quantity: 120, price: 19.42, pnl: -38.4 },
  { id: "t4", time: ago(210), bot: "insider", side: "buy", symbol: "NVDA", quantity: 15, price: 147.1 },
  { id: "t5", time: ago(305), bot: "grok-sniper", side: "sell", symbol: "AVAX", quantity: 60, price: 41.2, pnl: 212.6 },
  { id: "t6", time: ago(410), bot: "whale-watcher", side: "buy", symbol: "ETH", quantity: 1.2, price: 3_368 },
];

// --- markets (demo) ---

export interface Ticker {
  symbol: string;
  name: string;
  kind: "crypto" | "stock";
  price: number;
  change24hPct: number;
  volume24h: number;
  color: string;
  series: Point[];
}

const TICKER_INPUT: Omit<Ticker, "series">[] = [
  { symbol: "BTC", name: "Bitcoin", kind: "crypto", price: 96_420, change24hPct: 2.84, volume24h: 38.2e9, color: "#ff8a3d" },
  { symbol: "ETH", name: "Ethereum", kind: "crypto", price: 3_412.5, change24hPct: 1.92, volume24h: 17.6e9, color: "#6e7bff" },
  { symbol: "SOL", name: "Solana", kind: "crypto", price: 186.4, change24hPct: 6.71, volume24h: 5.1e9, color: "#a46bff" },
  { symbol: "AVAX", name: "Avalanche", kind: "crypto", price: 41.85, change24hPct: 4.12, volume24h: 0.92e9, color: "#ff5c7a" },
  { symbol: "LINK", name: "Chainlink", kind: "crypto", price: 18.9, change24hPct: -2.15, volume24h: 0.71e9, color: "#ff5fa2" },
  { symbol: "DOGE", name: "Dogecoin", kind: "crypto", price: 0.3871, change24hPct: -3.4, volume24h: 2.4e9, color: "#ffc65c" },
  { symbol: "NVDA", name: "NVIDIA", kind: "stock", price: 148.2, change24hPct: -0.84, volume24h: 31.4e9, color: "#36e3a1" },
  { symbol: "AAPL", name: "Apple", kind: "stock", price: 231.6, change24hPct: 0.42, volume24h: 12.2e9, color: "#38c8ff" },
  { symbol: "MSFT", name: "Microsoft", kind: "stock", price: 428.9, change24hPct: 1.06, volume24h: 9.8e9, color: "#b6f36a" },
  { symbol: "AMD", name: "AMD", kind: "stock", price: 162.35, change24hPct: 3.27, volume24h: 6.3e9, color: "#ff8a3d" },
  { symbol: "TSLA", name: "Tesla", kind: "stock", price: 251.4, change24hPct: -1.92, volume24h: 22.7e9, color: "#a46bff" },
];

export const TICKERS: Ticker[] = TICKER_INPUT.map((t, i) => ({
  ...t,
  series: timed(walk(100 + i, 48, t.price / (1 + t.change24hPct / 100), t.price, 0.8), 30),
}));

export const MARKET_PULSE = (() => {
  const up = TICKERS.filter((t) => t.change24hPct > 0);
  const sorted = [...TICKERS].sort((a, b) => b.change24hPct - a.change24hPct);
  return {
    advancers: up.length,
    decliners: TICKERS.length - up.length,
    averageChangePct: TICKERS.reduce((s, t) => s + t.change24hPct, 0) / TICKERS.length,
    topGainer: sorted[0],
    topLoser: sorted[sorted.length - 1],
  };
})();

// --- notifications (demo) ---

export interface Notice {
  id: string;
  time: string;
  title: string;
  body: string;
  tone: "violet" | "ember" | "mint" | "rose";
}

export const NOTIFICATIONS: Notice[] = [
  { id: "n1", time: ago(3), title: "Grok Sniper flagged SOL", body: "Unusual volume near a range high.", tone: "ember" },
  { id: "n2", time: ago(26), title: "Insider purchase on NVDA", body: "Director open-market buy (sample filing).", tone: "violet" },
  { id: "n3", time: ago(42), title: "Risk monitor", body: "SOL volatility above threshold.", tone: "rose" },
  { id: "n4", time: ago(95), title: "SEC ingestion finished", body: "3 new filings, no failures.", tone: "mint" },
];
