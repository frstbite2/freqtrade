/**
 * DEVELOPMENT ONLY: a stand-in for Phantom so the wallet experience can be built and tried without
 * a real wallet. Installed only when NEXT_PUBLIC_MOCK_PHANTOM=1; the interface then shows a MOCK
 * badge. Its address was generated at random for this purpose and belongs to no one. Balances for
 * it come from scripts/mock-solana.mjs, never from the real network.
 */

import type { PhantomProvider, PublicKeyLike } from "./phantom.ts";

export const MOCK_ADDRESS = "BECsvF75hVLrB5ioGAzrsofJNHpQ8vkJP2RZ2Sc7cjmX";
const TRUSTED = "orbit.mockWallet.trusted";

export function installMockPhantom(): void {
  if (typeof window === "undefined" || window.phantom?.solana) return;
  const handlers = new Map<string, Set<(arg?: PublicKeyLike | null) => void>>();
  const emit = (event: string, arg?: PublicKeyLike | null) => handlers.get(event)?.forEach((h) => h(arg));
  const key: PublicKeyLike = { toString: () => MOCK_ADDRESS };
  const trusted = () => {
    try {
      return window.localStorage.getItem(TRUSTED) === "1";
    } catch {
      return false;
    }
  };

  const provider: PhantomProvider = {
    isPhantom: true,
    isMock: true,
    publicKey: null,
    isConnected: false,
    async connect(options) {
      if (options?.onlyIfTrusted && !trusted()) throw Object.assign(new Error("User rejected the request."), { code: 4001 });
      if (!options?.onlyIfTrusted) await new Promise((r) => setTimeout(r, 700)); // the approval prompt
      provider.publicKey = key;
      provider.isConnected = true;
      try {
        window.localStorage.setItem(TRUSTED, "1");
      } catch {}
      emit("connect", key);
      return { publicKey: key };
    },
    async disconnect() {
      provider.publicKey = null;
      provider.isConnected = false;
      try {
        window.localStorage.removeItem(TRUSTED);
      } catch {}
      emit("disconnect");
    },
    on(event, handler) {
      if (!handlers.has(event)) handlers.set(event, new Set());
      handlers.get(event)?.add(handler);
    },
    removeListener(event, handler) {
      handlers.get(event)?.delete(handler);
    },
  };
  window.phantom = { solana: provider };
}
