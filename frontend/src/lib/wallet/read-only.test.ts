// Static guard, no wallet needed: the frontend must never ask a wallet to sign, send or approve.
// It scans every source file for wallet methods that could move funds or prove ownership.
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";

const SRC = join(import.meta.dirname, "..", "..");
const SELF = relative(SRC, import.meta.filename);
const FORBIDDEN = /\b(signMessage|signTransaction|signAllTransactions|signAndSendTransaction|signAndSendAllTransactions|signIn|sendTransaction|requestAirdrop)\b|\.request\s*\(/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(ts|tsx|js|mjs)$/.test(name) ? [path] : [];
  });
}

test("no source file references a wallet signing, sending or request method", () => {
  const offenders = files(SRC)
    .filter((f) => relative(SRC, f) !== SELF)
    .flatMap((f) =>
      readFileSync(f, "utf8")
        .split("\n")
        .map((line, i) => [line, i] as const)
        .filter(([line]) => FORBIDDEN.test(line))
        .map(([line, i]) => `${relative(SRC, f)}:${i + 1}: ${line.trim()}`),
    );
  assert.deepEqual(offenders, []);
});

test("the guard itself catches a signing call", () => {
  assert.ok(FORBIDDEN.test("await provider.signTransaction(tx)"));
  assert.ok(FORBIDDEN.test("provider.request({ method: 'signMessage' })"));
  assert.ok(!FORBIDDEN.test("const signal = AbortSignal.timeout(1)"));
});
