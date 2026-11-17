// Static guard, no data needed: sample values can never be shown as real.
// 1. A component that reads the platform API never imports sample values (no mixing).
// 2. A component that imports sample values shows a DEMO badge and checks the Demo/Live mode.
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";

const SRC = join(import.meta.dirname, "..");
const SAMPLE_VALUES = /^import \{[^}]*\} from "(@\/lib\/sample-data|\.\/sample-data(\.ts)?)";?$/m;
const REAL = /\b(usePlatform|fetchPlatform)\s*[<(]/;
// Uses the sample ticker list only to resolve a search query; every view it renders is badged.
const LOOKUP_ONLY = new Set(["app/markets/markets-view.tsx"]);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [path] : [];
  });
}

const sources = files(SRC).map((f) => ({ name: relative(SRC, f), text: readFileSync(f, "utf8") }));

test("no component mixes platform data with sample values", () => {
  const mixed = sources.filter((s) => REAL.test(s.text) && SAMPLE_VALUES.test(s.text)).map((s) => s.name);
  assert.deepEqual(mixed, []);
});

test("every sample-value view is badged DEMO and gated by the data mode", () => {
  const bad = sources
    .filter((s) => s.name.endsWith(".tsx") && SAMPLE_VALUES.test(s.text) && !LOOKUP_ONLY.has(s.name))
    .filter((s) => !/DemoBadge|DemoBanner/.test(s.text) || !s.text.includes("useDataMode"))
    .map((s) => s.name);
  assert.deepEqual(bad, []);
});

test("the guard sees the files it is meant to", () => {
  assert.ok(sources.some((s) => s.name === "components/dashboard/hero-balance.tsx" && SAMPLE_VALUES.test(s.text)));
  assert.ok(sources.some((s) => s.name === "components/sec/insider-view.tsx" && REAL.test(s.text)));
});
