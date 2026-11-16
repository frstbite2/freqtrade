"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { WalletSnapshot } from "./balances";
import { type PhantomProvider, USER_REJECTED, detectPhantom } from "./phantom";

/**
 * Read-only wallet state. Connecting tells this app the wallet's public address; balances are then
 * read from the Solana network by the frontend server. Nothing here can move funds or sign.
 * The wallet is separate from the simulated portfolio and is never used by the bots.
 */

export type WalletStatus = "detecting" | "not-installed" | "disconnected" | "connecting" | "connected";

export type Balances =
  | { state: "idle" | "loading" }
  | { state: "ok"; snapshot: WalletSnapshot }
  | { state: "error"; message: string };

interface WalletState {
  status: WalletStatus;
  address: string | null;
  mock: boolean;
  error: string | null;
  balances: Balances;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  refresh: () => void;
  clearError: () => void;
}

const WalletContext = createContext<WalletState | null>(null);
const REMEMBER = "orbit.wallet.connectedBefore";

function remember(on: boolean) {
  try {
    if (on) window.localStorage.setItem(REMEMBER, "1");
    else window.localStorage.removeItem(REMEMBER);
  } catch {
    // Storage blocked: the user simply clicks Connect again next time.
  }
}

function rememberedBefore(): boolean {
  try {
    return window.localStorage.getItem(REMEMBER) === "1";
  } catch {
    return false;
  }
}

function explain(error: unknown): string {
  const code = (error as { code?: number })?.code;
  if (code === USER_REJECTED) return "The connection was declined in Phantom. Nothing was shared.";
  if (code === -32002) return "Phantom is already showing a connection request. Check the Phantom window.";
  return "Phantom could not connect. Unlock Phantom and try again.";
}

export function WalletProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WalletStatus>("detecting");
  const [address, setAddress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [balances, setBalances] = useState<Balances>({ state: "idle" });
  const [nonce, setNonce] = useState(0);
  const provider = useRef<PhantomProvider | null>(null);

  // Find Phantom. Extensions inject their provider shortly after the page loads, so look again.
  useEffect(() => {
    let cancelled = false;
    let detach = () => {};
    const attach = (p: PhantomProvider) => {
      provider.current = p;
      const onConnect = (key?: { toString(): string } | null) => {
        if (key) {
          setAddress(key.toString());
          setStatus("connected");
        }
      };
      const onDisconnect = () => {
        setAddress(null);
        setStatus("disconnected");
        setBalances({ state: "idle" });
      };
      // Switching accounts in Phantom: follow the new one, or treat "no account" as disconnected.
      const onAccountChanged = (key?: { toString(): string } | null) => (key ? onConnect(key) : onDisconnect());
      p.on("connect", onConnect);
      p.on("disconnect", onDisconnect);
      p.on("accountChanged", onAccountChanged);
      detach = () => {
        const off = p.removeListener?.bind(p) ?? p.off?.bind(p);
        off?.("connect", onConnect);
        off?.("disconnect", onDisconnect);
        off?.("accountChanged", onAccountChanged);
      };
      setStatus(p.publicKey ? "connected" : "disconnected");
      if (p.publicKey) setAddress(p.publicKey.toString());
      // Reconnect silently only if this browser connected before and Phantom already trusts the
      // site: onlyIfTrusted never opens a prompt.
      else if (rememberedBefore()) p.connect({ onlyIfTrusted: true }).catch(() => remember(false));
    };

    const find = async () => {
      if (process.env.NEXT_PUBLIC_MOCK_PHANTOM === "1") {
        const { installMockPhantom } = await import("./mock-provider");
        installMockPhantom();
      }
      for (let i = 0; i < 6 && !cancelled; i++) {
        const p = detectPhantom();
        if (p) return attach(p);
        await new Promise((r) => setTimeout(r, 250));
      }
      if (!cancelled) setStatus("not-installed");
    };
    void find();
    return () => {
      cancelled = true;
      detach();
    };
  }, []);

  // Balances for the connected address, read by the frontend server from the Solana network.
  useEffect(() => {
    if (status !== "connected" || !address) return;
    let cancelled = false;
    setBalances((b) => (b.state === "ok" ? b : { state: "loading" }));
    fetch(`/api/wallet/${address}`, { cache: "no-store" })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (cancelled) return;
        if (r.ok) setBalances({ state: "ok", snapshot: body as WalletSnapshot });
        else setBalances({ state: "error", message: typeof body.error === "string" ? body.error : `HTTP ${r.status}` });
      })
      .catch(() => !cancelled && setBalances({ state: "error", message: "The balance service is not reachable." }));
    return () => {
      cancelled = true;
    };
  }, [status, address, nonce]);

  const connect = useCallback(async () => {
    const p = provider.current;
    if (!p) return;
    setError(null);
    setStatus("connecting");
    try {
      const { publicKey } = await p.connect();
      setAddress(publicKey.toString());
      setStatus("connected");
      remember(true);
    } catch (e) {
      setStatus("disconnected");
      setError(explain(e));
    }
  }, []);

  const disconnect = useCallback(async () => {
    remember(false);
    try {
      await provider.current?.disconnect();
    } finally {
      setAddress(null);
      setStatus("disconnected");
      setBalances({ state: "idle" });
    }
  }, []);

  return (
    <WalletContext.Provider
      value={{
        status,
        address,
        mock: Boolean(provider.current?.isMock),
        error,
        balances,
        connect,
        disconnect,
        refresh: () => setNonce((n) => n + 1),
        clearError: () => setError(null),
      }}
    >
      {children}
    </WalletContext.Provider>
  );
}

export function useWallet(): WalletState {
  const value = useContext(WalletContext);
  if (!value) throw new Error("useWallet must be used inside WalletProvider");
  return value;
}
