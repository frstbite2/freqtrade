/**
 * Market data from the platform API (Alpaca behind it). LIVE VERIFICATION PENDING: the backend's
 * Alpaca adapter has not yet been checked against real responses, and neither has this view.
 */

import type { Point } from "./sample-data.ts";

export interface Bar {
  ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface Bars {
  symbol: string;
  timeframe: string;
  adjustment: string;
  source: string;
  bars: Bar[];
  rejected: unknown[];
  warnings: string[];
}

export interface Quote {
  symbol: string;
  source: string;
  ts: string;
  age_seconds: number;
  bid_price: string;
  ask_price: string;
  usable: boolean;
  problems: string[];
}

export function closes(b: Bars): Point[] {
  return b.bars.map((x) => ({ t: x.ts, v: Number(x.close) }));
}

/** Change from the first to the last close, in percent; null with fewer than two bars. */
export function periodChange(points: Point[]): number | null {
  if (points.length < 2 || points[0].v === 0) return null;
  return ((points[points.length - 1].v - points[0].v) / points[0].v) * 100;
}

export type QuoteView =
  | { state: "current"; mid: number; spreadPct: number }
  | { state: "stale"; mid: number | null }
  | { state: "unusable"; reason: string };

/** The backend flags quotes; only a usable one is shown as a current price. */
export function quoteView(q: Quote): QuoteView {
  const bid = Number(q.bid_price), ask = Number(q.ask_price);
  const mid = bid > 0 && ask >= bid ? (bid + ask) / 2 : null;
  if (q.usable && mid !== null) return { state: "current", mid, spreadPct: ((ask - bid) / mid) * 100 };
  if (q.problems.length === 1 && q.problems[0] === "stale") return { state: "stale", mid };
  return { state: "unusable", reason: q.problems.filter((p) => p !== "stale").join(", ").replaceAll("_", " ") || "not usable" };
}
