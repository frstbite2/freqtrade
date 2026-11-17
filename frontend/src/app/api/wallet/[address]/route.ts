/**
 * Read-only balances for a Solana address, read by this server so the browser never needs an RPC
 * key. The browser sends only a public address; nothing here can sign or move funds.
 *
 * Settings (server-side only, see .env.example):
 *   SOLANA_RPC_URL    JSON-RPC endpoint. Required: there is deliberately no default, so real
 *                     balances appear only after someone sets it on purpose, once live access is
 *                     verified. A provider URL with a key stays on this server.
 *   WALLET_PRICE_URL  price endpoint answering ?ids=<mint,...> in Jupiter Price API v3 form;
 *                     prices are optional: without them balances still show, without USD values.
 *
 * LIVE VERIFICATION PENDING: written to the documented RPC and price formats and tested on mock
 * responses only; the development sandbox cannot reach the Solana network.
 */

import { isSolanaAddress } from "@/lib/wallet/address";
import {
  type BalanceResult,
  type Prices,
  TOKEN_2022_PROGRAM,
  TOKEN_PROGRAM,
  type TokenAccountsResult,
  buildSnapshot,
} from "@/lib/wallet/balances";
import { KNOWN_TOKENS, WRAPPED_SOL_MINT } from "@/lib/wallet/tokens";

export const dynamic = "force-dynamic";

const TIMEOUT_MS = 10_000;
const DEFAULT_PRICES = "https://lite-api.jup.ag/price/v3";

class RpcError extends Error {}

async function rpc<T>(url: string, method: string, params: unknown[]): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw new RpcError(`the Solana RPC answered HTTP ${response.status}`);
  const body = (await response.json()) as { result?: T; error?: { message?: string } };
  if (body.error || body.result === undefined) throw new RpcError("the Solana RPC returned an error");
  return body.result;
}

async function prices(mints: string[]): Promise<Prices> {
  const base = process.env.WALLET_PRICE_URL || DEFAULT_PRICES;
  try {
    const response = await fetch(`${base}?ids=${mints.join(",")}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) return {};
    const body = (await response.json()) as Record<string, { usdPrice?: unknown } | null>;
    const out: Prices = {};
    for (const mint of mints) {
      const p = body?.[mint]?.usdPrice;
      if (typeof p === "number" && Number.isFinite(p) && p >= 0) out[mint] = p;
    }
    return out;
  } catch {
    return {}; // unknown prices are shown as unavailable, never as zero
  }
}

export async function GET(_request: Request, { params }: { params: Promise<{ address: string }> }) {
  const { address } = await params;
  if (!isSolanaAddress(address)) {
    return Response.json({ error: "not a Solana address" }, { status: 400 });
  }
  const url = process.env.SOLANA_RPC_URL;
  if (!url) {
    return Response.json({ error: "Balances unavailable: no Solana RPC is configured on this server (SOLANA_RPC_URL)." }, { status: 503 });
  }
  try {
    const accounts = (program: string) =>
      rpc<TokenAccountsResult>(url, "getTokenAccountsByOwner", [address, { programId: program }, { encoding: "jsonParsed", commitment: "confirmed" }]);
    const [balance, classic, token2022, priceTable] = await Promise.all([
      rpc<BalanceResult>(url, "getBalance", [address, { commitment: "confirmed" }]),
      accounts(TOKEN_PROGRAM),
      accounts(TOKEN_2022_PROGRAM),
      prices([WRAPPED_SOL_MINT, ...KNOWN_TOKENS.map((t) => t.mint)]),
    ]);
    const snapshot = { ...buildSnapshot(address, balance, [classic, token2022], priceTable), fetchedAt: new Date().toISOString() };
    return Response.json(snapshot, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    // Never echo the RPC URL: it can contain a provider key.
    const message = error instanceof RpcError ? error.message : "the Solana RPC is not reachable";
    return Response.json({ error: `Balances unavailable: ${message}.` }, { status: 502 });
  }
}
