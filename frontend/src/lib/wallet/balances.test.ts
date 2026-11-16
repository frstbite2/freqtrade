// MOCK DATA: these RPC answers are hand-built in the documented jsonParsed shape. Live verification
// against the real Solana network is pending (the development sandbox cannot reach it).
import assert from "node:assert/strict";
import { test } from "node:test";
import { allocation, buildSnapshot, formatUnits, TOKEN_PROGRAM, type TokenAccountsResult } from "./balances.ts";

const USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
const BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263";
const SOL = "So11111111111111111111111111111111111111112";
const ADDRESS = "BECsvF75hVLrB5ioGAzrsofJNHpQ8vkJP2RZ2Sc7cjmX";
void TOKEN_PROGRAM;

const acct = (mint: string, amount: string, decimals: number) => ({
  account: { data: { parsed: { info: { mint, tokenAmount: { amount, decimals } } } } },
});
const accounts = (...value: ReturnType<typeof acct>[]): TokenAccountsResult => ({ context: { slot: 7 }, value });

test("aggregates accounts per mint exactly and orders SOL first, then by value", () => {
  const s = buildSnapshot(
    ADDRESS,
    { context: { slot: 7 }, value: 2_500_000_000 },
    [accounts(acct(USDC, "1000000", 6), acct(USDC, "2500001", 6), acct(BONK, "100000000000", 5))],
    { [SOL]: 100, [USDC]: 1, [BONK]: 0.00002 },
  );
  assert.deepEqual(s.holdings.map((h) => h.symbol), ["SOL", "BONK", "USDC"]); // BONK $20 outranks USDC $3.50
  assert.equal(s.holdings[0].amountText, "2.5");
  assert.equal(s.holdings[2].amountText, "3.500001");
  assert.equal(s.holdings[1].amount, 1_000_000);
  assert.equal(s.totalUsd, 250 + 3.500001 + 20);
  assert.equal(s.slot, 7);
  assert.equal(s.mock, false);
  const shares = allocation(s);
  assert.ok(Math.abs(shares.reduce((t, a) => t + a.pct, 0) - 100) < 1e-9);
});

test("skips empty accounts, counts NFT-like and unrecognised tokens without naming them", () => {
  const s = buildSnapshot(
    ADDRESS,
    { value: 0 },
    [accounts(acct(USDC, "0", 6), acct("4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "1", 0)), accounts(acct("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "5", 2))],
    {},
  );
  assert.deepEqual(s.holdings.map((h) => h.symbol), ["SOL"]);
  assert.equal(s.nftLike, 1);
  assert.equal(s.unrecognisedTokens, 1);
});

test("missing prices are unknown, never zero", () => {
  const s = buildSnapshot(ADDRESS, { value: 1_000_000_000 }, [accounts(acct(USDC, "5000000", 6))], { [USDC]: 1 });
  assert.equal(s.holdings[0].usdValue, null);
  assert.equal(s.holdings[0].usdPrice, null);
  assert.equal(s.totalUsd, 5);
  const none = buildSnapshot(ADDRESS, { value: 1 }, [], {});
  assert.equal(none.totalUsd, null);
  assert.equal(none.pricesAvailable, false);
  assert.deepEqual(allocation(none), []);
});

test("an answer from the local mock RPC is flagged as mock", () => {
  const s = buildSnapshot(ADDRESS, { context: { apiVersion: "mock" }, value: 1 }, [], {});
  assert.equal(s.mock, true);
});

test("formatUnits is exact", () => {
  assert.equal(formatUnits(0n, 6), "0");
  assert.equal(formatUnits(1n, 6), "0.000001");
  assert.equal(formatUnits(123456789012345678901234567890n, 9), "123456789012345678901.23456789");
  assert.equal(formatUnits(42n, 0), "42");
});
