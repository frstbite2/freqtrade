/**
 * Solana tokens the wallet view recognises, by mint address. Anything else in a wallet is counted
 * but not named or priced, because a token's own metadata can claim any name.
 */

export const WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112";

export interface KnownToken {
  mint: string;
  symbol: string;
  name: string;
  color: string;
}

export const KNOWN_TOKENS: KnownToken[] = [
  { mint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", symbol: "USDC", name: "USD Coin", color: "#38c8ff" },
  { mint: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", symbol: "USDT", name: "Tether USD", color: "#36e3a1" },
  { mint: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", symbol: "JUP", name: "Jupiter", color: "#b6f36a" },
  { mint: "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", symbol: "JTO", name: "Jito", color: "#6e7bff" },
  { mint: "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", symbol: "JitoSOL", name: "Jito Staked SOL", color: "#a46bff" },
  { mint: "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", symbol: "mSOL", name: "Marinade Staked SOL", color: "#ff5fa2" },
  { mint: "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", symbol: "PYTH", name: "Pyth Network", color: "#c58cff" },
  { mint: "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", symbol: "RAY", name: "Raydium", color: "#38c8ff" },
  { mint: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", symbol: "BONK", name: "Bonk", color: "#ffc65c" },
  { mint: "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", symbol: "WIF", name: "dogwifhat", color: "#ff8a3d" },
];

export const SOL_TOKEN: KnownToken = { mint: WRAPPED_SOL_MINT, symbol: "SOL", name: "Solana", color: "#a46bff" };

const BY_MINT = new Map(KNOWN_TOKENS.map((t) => [t.mint, t]));

export function knownToken(mint: string): KnownToken | undefined {
  return BY_MINT.get(mint);
}
