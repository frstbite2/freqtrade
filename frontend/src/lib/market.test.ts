// MOCK DATA: hand-built in the backend's documented response shape. Alpaca live verification is
// pending (no API keys yet), so nothing here has been checked against real market data.
import assert from "node:assert/strict";
import { test } from "node:test";
import { closes, periodChange, quoteView, type Bars, type Quote } from "./market.ts";

const quote = (over: Partial<Quote>): Quote => ({ symbol: "AAPL", source: "alpaca", ts: "2026-11-17T15:00:00Z", age_seconds: 2, bid_price: "100.00", ask_price: "100.10", usable: true, problems: [], ...over });

test("only a usable quote is a current price", () => {
  const v = quoteView(quote({}));
  assert.equal(v.state, "current");
  if (v.state === "current") assert.ok(Math.abs(v.mid - 100.05) < 1e-9);
  assert.equal(quoteView(quote({ usable: false, problems: ["stale"] })).state, "stale");
  assert.deepEqual(quoteView(quote({ usable: false, problems: ["crossed_market"], bid_price: "101", ask_price: "100" })), { state: "unusable", reason: "crossed market" });
  assert.equal(quoteView(quote({ usable: false, problems: ["non_positive_price", "stale"], bid_price: "0" })).state, "unusable");
});

test("bars become a close series; change needs two bars", () => {
  const b: Bars = { symbol: "AAPL", timeframe: "1d", adjustment: "raw", source: "alpaca", rejected: [], warnings: [], bars: [
    { ts: "2026-11-13T05:00:00Z", open: "1", high: "1", low: "1", close: "200.00", volume: "1" },
    { ts: "2026-11-14T05:00:00Z", open: "1", high: "1", low: "1", close: "210.00", volume: "1" },
  ] };
  const pts = closes(b);
  assert.deepEqual(pts.map((p) => p.v), [200, 210]);
  assert.equal(periodChange(pts), 5);
  assert.equal(periodChange(pts.slice(0, 1)), null);
});
