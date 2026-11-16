#!/usr/bin/env node
/**
 * DEVELOPMENT ONLY: a local stand-in for a Solana JSON-RPC endpoint and a price API, so the
 * read-only wallet view can be built and tested without the real network or a real wallet.
 * Every RPC answer carries context.apiVersion "mock", which the interface shows as MOCK.
 *
 *   npm run mock:solana            # listens on 127.0.0.1:8899
 *   SOLANA_RPC_URL=http://127.0.0.1:8899 WALLET_PRICE_URL=http://127.0.0.1:8899/price
 */
import { createServer } from "node:http";

const PORT = Number(process.env.PORT || 8899);
const context = { slot: 312_345_678, apiVersion: "mock" };
const CLASSIC = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

const account = (mint, amount, decimals) => ({
  pubkey: "MockAccount" + mint.slice(0, 8),
  account: { data: { parsed: { info: { mint, tokenAmount: { amount, decimals } }, type: "account" }, program: "spl-token" } },
});

const CLASSIC_ACCOUNTS = [
  account("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "1250500000", 6), // 1,250.5 USDC
  account("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "820000000", 6), // 820 JUP
  account("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "1500000000000", 5), // 15,000,000 BONK
  account("mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", "3200000000", 9), // 3.2 mSOL
  account("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "1000000000", 6), // not on the supported list
  account("4Nd1mBQtrMJVYVfKf2PJy9NZUZdTAsp7D4xWLs4gDB4T", "1", 0), // NFT-like
  account("HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", "0", 6), // empty account
];
const TOKEN_2022_ACCOUNTS = [account("2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo", "42000000", 6)]; // unrecognised

const PRICES = {
  So11111111111111111111111111111111111111112: 186.4,
  EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v: 1.0,
  JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN: 0.92,
  DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263: 0.0000241,
  mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So: 228.5,
};

function answer(method, params) {
  if (method === "getBalance") return { context, value: 12_480_000_000 }; // 12.48 SOL
  if (method === "getTokenAccountsByOwner")
    return { context, value: params?.[1]?.programId === CLASSIC ? CLASSIC_ACCOUNTS : TOKEN_2022_ACCOUNTS };
  return null;
}

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  res.setHeader("Content-Type", "application/json");
  if (req.method === "GET" && url.pathname === "/price") {
    const ids = (url.searchParams.get("ids") || "").split(",");
    const body = Object.fromEntries(ids.filter((id) => id in PRICES).map((id) => [id, { usdPrice: PRICES[id], priceChange24h: 0 }]));
    return res.end(JSON.stringify(body));
  }
  if (req.method !== "POST") return res.writeHead(405).end(JSON.stringify({ error: "POST JSON-RPC only" }));
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", () => {
    let call;
    try {
      call = JSON.parse(raw);
    } catch {
      return res.writeHead(400).end(JSON.stringify({ jsonrpc: "2.0", error: { code: -32700, message: "parse error" }, id: null }));
    }
    const result = answer(call.method, call.params);
    res.end(JSON.stringify(result === null
      ? { jsonrpc: "2.0", error: { code: -32601, message: "method not found" }, id: call.id }
      : { jsonrpc: "2.0", result, id: call.id }));
  });
}).listen(PORT, "127.0.0.1", () => console.log(`mock Solana RPC and prices on http://127.0.0.1:${PORT} (MOCK DATA)`));
