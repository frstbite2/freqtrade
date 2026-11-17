// REAL DATA: fixtures are unmodified platform API responses built from SEC EDGAR filings
// (see src/lib/fixtures/README.md).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { changeText, insiderDisclosures, readableProblem, newestFirst, ownershipDisclosure, role, watchlist, type InsiderTransactions, type Jobs, type Ownership } from "./sec.ts";

const load = <T>(name: string): T => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8")) as T;
const gme = load<InsiderTransactions>("insider-signals-GME.json");
const cvna = load<Ownership>("ownership-filings-CVNA.json");

test("the watchlist is read from the scheduler's last runs", () => {
  assert.deepEqual(watchlist(load<Jobs>("jobs.json")), ["AAPL", "NKE", "INTC", "GME", "CVNA"]);
  assert.deepEqual(watchlist({ enabled: true, jobs: {}, recent_runs: [] }), []);
});

test("an insider signal keeps its public time, evidence and filing link", () => {
  const t = gme.transactions[0];
  const d = insiderDisclosures("GME", [t])[0];
  assert.equal(d.time, t.accepted_at);
  assert.equal(d.url, t.filing_url);
  assert.match(d.title, t.signal === "discretionary_buy" ? / bought / : / sold /);
  assert.ok(d.evidence.some((e) => e.includes(t.accession)));
  assert.match(d.explanation, /never evidence of wrongdoing|not evidence of wrongdoing/);
});

test("only signals reach the feed fixture, and 13D/13G items say what the schedule means", () => {
  assert.ok(gme.transactions.every((t) => t.signal !== null));
  const f = cvna.filings![0];
  const d = ownershipDisclosure("CVNA", f);
  assert.equal(d.kind, "ownership");
  assert.ok(d.evidence[0].startsWith(`${f.schedule}: `));
  assert.match(d.explanation, /not current holdings/);
});

test("changes are reported, never invented", () => {
  const withChange = cvna.filings!.find((f) => f.change);
  if (withChange) assert.match(changeText(withChange) ?? "", /since the \d{4}-\d{2}-\d{2} filing/);
  assert.equal(changeText({ ...cvna.filings![0], change: null }), null);
});

test("the merged feed is newest first", () => {
  const items = [...insiderDisclosures("GME", gme.transactions), ...cvna.filings!.map((f) => ownershipDisclosure("CVNA", f))];
  const feed = newestFirst(items, 6);
  assert.equal(feed.length, 6);
  for (let i = 1; i < feed.length; i++) assert.ok(feed[i - 1].time >= feed[i].time);
});

test("roles read naturally", () => {
  assert.equal(role({ position: null, is_director: true, is_officer: false, is_ten_percent_owner: false }), "Director");
  assert.equal(role({ position: "Chief Financial Officer", is_director: false, is_officer: true, is_ten_percent_owner: true }), "Chief Financial Officer, 10% owner");
});

test("lots from one filing, person and direction become one item with exact totals", () => {
  const t = gme.transactions[0];
  const lots = [t, { ...t, shares: "1000.000000", value: "20000.00", price: "20.000000", transaction_date: "2026-10-14" }];
  const [d] = insiderDisclosures("GME", lots);
  const expected = Number(t.shares) + 1000;
  assert.match(d.title, new RegExp(`${expected.toLocaleString("en-US")} shares in 2 trades`));
  assert.ok(d.evidence[1].includes(" to 2026-10-14"));
  assert.equal(insiderDisclosures("GME", [t, { ...t, accession: "other" }]).length, 2);
});

test("problem strings get readable times", () => {
  assert.equal(readableProblem("insider: overdue since 2026-11-14T18:39:22.643942+00:00"), "insider: overdue since Nov 14, 18:39 UTC");
});
