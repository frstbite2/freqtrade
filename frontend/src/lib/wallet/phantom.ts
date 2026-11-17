/**
 * The only code that talks to Phantom. It uses Phantom's documented injected provider
 * (window.phantom.solana) for exactly three things: connect, disconnect, and the events that say
 * the account changed. It never asks Phantom to sign anything: no messages, no transactions, no
 * approvals. test: src/lib/wallet/read-only.test.ts fails if a signing method is ever referenced.
 *
 * What connecting grants: this site learns the wallet's public address, and may later *ask* for
 * signatures, each of which Phantom would show to the user for approval. This app never asks.
 */

export interface PublicKeyLike {
  toString(): string;
}

/** The subset of Phantom's provider this app uses. Signing methods are deliberately absent. */
export interface PhantomProvider {
  isPhantom?: boolean;
  isMock?: boolean;
  publicKey: PublicKeyLike | null;
  isConnected?: boolean;
  connect(options?: { onlyIfTrusted?: boolean }): Promise<{ publicKey: PublicKeyLike }>;
  disconnect(): Promise<void>;
  on(event: "connect" | "disconnect" | "accountChanged", handler: (arg?: PublicKeyLike | null) => void): void;
  removeListener?(event: string, handler: (arg?: PublicKeyLike | null) => void): void;
  off?(event: string, handler: (arg?: PublicKeyLike | null) => void): void;
}

declare global {
  interface Window {
    phantom?: { solana?: PhantomProvider };
    solana?: PhantomProvider;
  }
}

/** Phantom's provider, only if it really says it is Phantom. */
export function detectPhantom(): PhantomProvider | null {
  if (typeof window === "undefined") return null;
  const provider = window.phantom?.solana ?? window.solana;
  return provider?.isPhantom ? provider : null;
}

export function isMobileBrowser(): boolean {
  return typeof navigator !== "undefined" && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

/** Opens this page inside Phantom's in-app browser (its documented universal link). */
export function phantomBrowseLink(url: string): string {
  return `https://phantom.app/ul/browse/${encodeURIComponent(url)}?ref=${encodeURIComponent(new URL(url).origin)}`;
}

export const PHANTOM_DOWNLOAD = "https://phantom.com/download";

/** Phantom's code when the user closes or declines the connection prompt. */
export const USER_REJECTED = 4001;
