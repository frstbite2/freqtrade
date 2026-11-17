// Unit test on constructed inputs (no real wallet data needed for address handling).
import assert from "node:assert/strict";
import { test } from "node:test";
import { isSolanaAddress, shortAddress } from "./address.ts";

test("accepts real-format addresses: 32 bytes in base58", () => {
  assert.ok(isSolanaAddress("So11111111111111111111111111111111111111112"));
  assert.ok(isSolanaAddress("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"));
  assert.ok(isSolanaAddress("11111111111111111111111111111111")); // the system program, 32 zero bytes
});

test("rejects anything else", () => {
  for (const bad of ["", "abc", "0OIl" + "1".repeat(40), "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v/../x", "1".repeat(45), "z".repeat(44)]) {
    assert.equal(isSolanaAddress(bad), false, bad);
  }
});

test("shortens for display", () => {
  assert.equal(shortAddress("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"), "EPjF…Dt1v");
  assert.equal(shortAddress("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6, 6), "EPjFWd…yTDt1v");
  assert.equal(shortAddress("short"), "short");
});
