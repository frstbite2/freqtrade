// Unit test on constructed facts plus the real ingestion-health fixture (src/lib/fixtures).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { BOTS } from "./bots.ts";
import { readiness } from "./readiness.ts";
import type { IngestionHealth } from "./sec.ts";

const health = JSON.parse(readFileSync(new URL("./fixtures/health-ingestion.json", import.meta.url), "utf8")) as IngestionHealth;
const bot = (id: string) => BOTS.find((b) => b.id === id)!;
const now = Date.parse("2026-11-17T01:00:00Z");

test("every bot ends with its real strategy state, never a performance figure", () => {
  for (const b of BOTS) {
    const rows = readiness(b, { providers: null, ingestion: null }, now);
    assert.equal(rows.at(-1)!.label, "Strategy");
    assert.equal(rows.at(-1)!.state, "missing");
  }
});

test("stale SEC data is reported as stale, with its age", () => {
  const [sec, market] = readiness(bot("insider"), { providers: { alpaca: false }, ingestion: health }, now);
  assert.deepEqual([sec.state, market.state], ["stale", "missing"]);
  assert.match(sec.detail, /days ago, overdue/);
});

test("configured keys are not claimed as verified", () => {
  const [market] = readiness(bot("grok-sniper"), { providers: { alpaca: true }, ingestion: null }, now);
  assert.equal(market.state, "ready");
  assert.match(market.detail, /verification pending/);
});

test("an unreachable backend is unknown, not missing", () => {
  const [market] = readiness(bot("dip-hunter"), { providers: null, ingestion: null }, now);
  assert.equal(market.state, "unknown");
});
