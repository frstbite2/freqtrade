// Pure formatting checks; no data.
import assert from "node:assert/strict";
import { test } from "node:test";
import { ago, price, signedPct, signedUsd, usd, utcTime } from "./format.ts";

test("money and percentages carry their sign", () => {
  assert.equal(usd(1234.5), "$1,234.50");
  assert.equal(signedUsd(1234.5), "+$1,234.50");
  assert.equal(signedUsd(-12), "-$12.00");
  assert.equal(signedUsd(0), "$0.00");
  assert.equal(signedPct(2.4123), "+2.41%");
  assert.equal(signedPct(-0.8), "-0.80%");
});

test("prices under a dollar keep four decimals; times are UTC", () => {
  assert.equal(price(0.51234), "$0.5123");
  assert.equal(price(95123.456), "$95,123.46");
  assert.equal(utcTime("2026-11-16T14:05:00Z"), "14:05 UTC");
});

test("sub-cent prices keep significant digits", () => {
  assert.equal(price(0.0000241), "$0.0000241");
  assert.equal(price(0.5), "$0.5000");
  assert.equal(price(186.4), "$186.40");
});

test("ago reads naturally and never goes negative", () => {
  const now = Date.parse("2026-11-17T01:00:00Z");
  assert.equal(ago("2026-11-17T01:00:20Z", now), "just now");
  assert.equal(ago("2026-11-17T00:15:00Z", now), "45 min ago");
  assert.equal(ago("2026-11-16T15:00:00Z", now), "10 h ago");
  assert.equal(ago("2026-11-14T17:09:24Z", now), "2 days ago");
});
