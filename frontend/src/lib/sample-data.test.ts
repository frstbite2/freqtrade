// Checks the SAMPLE data's internal consistency (it is demo data, not market data).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ACTIVITY,
  BOT_DEMO,
  HOLDINGS,
  MARKET_PULSE,
  PORTFOLIO,
  TICKERS,
  TIMEFRAMES,
  portfolioSeries,
  walk,
} from "./sample-data.ts";

const close = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;

test("portfolio totals are derived from the holdings", () => {
  const invested = HOLDINGS.reduce((s, h) => s + h.value, 0);
  assert.ok(close(PORTFOLIO.totalValue, invested + PORTFOLIO.cash));
  const allocated = HOLDINGS.reduce((s, h) => s + h.allocationPct, 0) + PORTFOLIO.cashPct;
  assert.ok(close(allocated, 100));
  assert.ok(close(PORTFOLIO.dailyPnl, HOLDINGS.reduce((s, h) => s + h.dayChange, 0)));
  assert.ok(close(PORTFOLIO.totalReturnPct, (PORTFOLIO.totalValue / PORTFOLIO.startingBalance - 1) * 100));
});

test("every chart ends at the value it illustrates", () => {
  for (const tf of TIMEFRAMES) {
    const series = portfolioSeries(tf);
    assert.ok(close(series[series.length - 1].v, PORTFOLIO.totalValue), tf);
    assert.ok(series.every((p, i) => i === 0 || p.t > series[i - 1].t), `${tf} timestamps ascend`);
  }
  for (const [id, bot] of Object.entries(BOT_DEMO)) {
    assert.ok(close(bot.spark[bot.spark.length - 1].v, bot.pnlPct), id);
  }
  for (const t of TICKERS) assert.ok(close(t.series[t.series.length - 1].v, t.price), t.symbol);
});

test("the sample data is deterministic", () => {
  assert.deepEqual(walk(7, 20, 1, 2, 1), walk(7, 20, 1, 2, 1));
  assert.deepEqual(portfolioSeries("1M"), portfolioSeries("1M"));
});

test("every sample signal carries a timestamp, source, evidence and explanation", () => {
  for (const a of ACTIVITY) {
    assert.ok(!Number.isNaN(Date.parse(a.time)), a.id);
    assert.ok(a.source.length > 0 && a.evidence.length > 0 && a.explanation.length > 20, a.id);
  }
});

test("market breadth is computed from the watchlist", () => {
  assert.equal(MARKET_PULSE.advancers + MARKET_PULSE.decliners, TICKERS.length);
  assert.equal(MARKET_PULSE.topGainer.symbol, "SOL");
});
