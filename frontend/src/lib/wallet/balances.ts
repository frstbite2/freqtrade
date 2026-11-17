/**
 * Turning Solana JSON-RPC answers into a wallet snapshot. Pure functions: the server route does
 * the fetching, so this file can be tested on recorded or mock responses.
 *
 * RPC methods used (all read-only): getBalance, getTokenAccountsByOwner with jsonParsed encoding,
 * once for the classic token program and once for Token-2022.
 */

import { SOL_TOKEN, WRAPPED_SOL_MINT, knownToken } from "./tokens.ts";

export const TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
export const TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
const LAMPORTS_PER_SOL = 1_000_000_000;

export interface Holding {
  mint: string;
  symbol: string;
  name: string;
  color: string;
  amount: number;
  /** Exact amount as the chain reports it, for display without float rounding. */
  amountText: string;
  usdPrice: number | null;
  usdValue: number | null;
}

export interface WalletSnapshot {
  address: string;
  holdings: Holding[]; // SOL first, then recognised tokens by value
  unrecognisedTokens: number; // fungible tokens not on the supported list
  nftLike: number; // amount 1 with 0 decimals: NFTs and similar, not shown
  totalUsd: number | null; // null when no price is known
  pricesAvailable: boolean;
  slot: number | null;
  mock: boolean; // the RPC answered as the local mock (scripts/mock-solana.mjs)
  fetchedAt?: string; // set by the server route when it read the chain
}

interface RpcContext {
  context?: { slot?: number; apiVersion?: string };
}

export interface BalanceResult extends RpcContext {
  value: number; // lamports
}

export interface TokenAccountsResult extends RpcContext {
  value: {
    account: {
      data: {
        parsed?: {
          info?: {
            mint?: string;
            tokenAmount?: { amount: string; decimals: number; uiAmountString?: string };
          };
        };
      };
    };
  }[];
}

/** Prices in USD by mint; missing means unknown, never zero. */
export type Prices = Record<string, number>;

function lamportsText(lamports: number): string {
  const whole = Math.floor(lamports / LAMPORTS_PER_SOL);
  const frac = String(lamports % LAMPORTS_PER_SOL).padStart(9, "0").replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : String(whole);
}

export function buildSnapshot(
  address: string,
  balance: BalanceResult,
  tokenAccounts: TokenAccountsResult[],
  prices: Prices,
): WalletSnapshot {
  const totals = new Map<string, { raw: bigint; decimals: number }>();
  let nftLike = 0;
  for (const result of tokenAccounts) {
    for (const entry of result.value) {
      const info = entry.account.data.parsed?.info;
      const amount = info?.tokenAmount;
      if (!info?.mint || !amount || !/^\d+$/.test(amount.amount)) continue;
      const raw = BigInt(amount.amount);
      if (raw === 0n) continue;
      if (amount.decimals === 0 && raw === 1n) {
        nftLike++;
        continue;
      }
      const prev = totals.get(info.mint);
      totals.set(info.mint, { raw: (prev?.raw ?? 0n) + raw, decimals: amount.decimals });
    }
  }

  const price = (mint: string): number | null => (Number.isFinite(prices[mint]) ? prices[mint] : null);
  const sol = balance.value;
  const solPrice = price(WRAPPED_SOL_MINT);
  const holdings: Holding[] = [
    {
      ...SOL_TOKEN,
      amount: sol / LAMPORTS_PER_SOL,
      amountText: lamportsText(sol),
      usdPrice: solPrice,
      usdValue: solPrice === null ? null : (sol / LAMPORTS_PER_SOL) * solPrice,
    },
  ];
  let unrecognised = 0;
  const tokens: Holding[] = [];
  for (const [mint, { raw, decimals }] of totals) {
    const known = knownToken(mint);
    if (!known) {
      unrecognised++;
      continue;
    }
    const text = formatUnits(raw, decimals);
    const amount = Number(text);
    const p = price(mint);
    tokens.push({ ...known, amount, amountText: text, usdPrice: p, usdValue: p === null ? null : amount * p });
  }
  tokens.sort((a, b) => (b.usdValue ?? -1) - (a.usdValue ?? -1) || a.symbol.localeCompare(b.symbol));
  holdings.push(...tokens);

  const priced = holdings.filter((h) => h.usdValue !== null);
  const contexts = [balance, ...tokenAccounts];
  return {
    address,
    holdings,
    unrecognisedTokens: unrecognised,
    nftLike,
    totalUsd: priced.length ? priced.reduce((s, h) => s + (h.usdValue ?? 0), 0) : null,
    pricesAvailable: priced.length > 0,
    slot: balance.context?.slot ?? null,
    mock: contexts.some((c) => c.context?.apiVersion === "mock"),
  };
}

/** Raw integer units to a decimal string, exactly. */
export function formatUnits(raw: bigint, decimals: number): string {
  if (decimals === 0) return raw.toString();
  const text = raw.toString().padStart(decimals + 1, "0");
  const whole = text.slice(0, -decimals);
  const frac = text.slice(-decimals).replace(/0+$/, "");
  return frac ? `${whole}.${frac}` : whole;
}

/** Share of the priced value per holding, in percent. */
export function allocation(snapshot: WalletSnapshot): { symbol: string; pct: number; color: string; value: number }[] {
  if (!snapshot.totalUsd) return [];
  return snapshot.holdings
    .filter((h) => h.usdValue)
    .map((h) => ({ symbol: h.symbol, pct: ((h.usdValue ?? 0) / (snapshot.totalUsd ?? 1)) * 100, color: h.color, value: h.usdValue ?? 0 }));
}
