// Pure rule checks; no network.
import assert from "node:assert/strict";
import { test } from "node:test";
import { isAllowedPath } from "./proxy-rules.ts";

test("allows the read-only platform endpoints", () => {
  assert.ok(isAllowedPath(["health"]));
  assert.ok(isAllowedPath(["api", "v1", "status"]));
  assert.ok(isAllowedPath(["api", "v1", "insider", "NKE", "score"]));
  assert.ok(isAllowedPath(["api", "v1", "ownership", "GME", "holders"]));
});

test("refuses everything else, including traversal and odd characters", () => {
  for (const bad of [
    [],
    ["api"],
    ["api", "v1"],
    ["admin"],
    ["api", "v2", "status"],
    ["api", "v1", "insider", ".."],
    ["api", "v1", "insider", "%2e%2e"],
    ["api", "v1", "insider", "a/b"],
    ["api", "v1", "insider", "NK E"],
    ["api", "v1", "insider", "x".repeat(65)],
    ["health", "a", "b", "c", "d", "e", "f", "g", "h"],
  ]) {
    assert.equal(isAllowedPath(bad), false, JSON.stringify(bad));
  }
});
