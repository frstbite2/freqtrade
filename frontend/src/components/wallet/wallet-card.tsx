"use client";

import { Download, Loader2, ShieldOff, Smartphone, Wallet } from "lucide-react";
import { usd } from "@/lib/format";
import { shortAddress } from "@/lib/wallet/address";
import { PHANTOM_DOWNLOAD, isMobileBrowser, phantomBrowseLink } from "@/lib/wallet/phantom";
import { useWallet } from "@/lib/wallet/wallet-context";
import { AllocationRing, BalancesState, HoldingsList, MockBadge, PermissionsNote, ReadOnlyBadge, SourceLine, isMock } from "./wallet-ui";

/**
 * The user's real Phantom wallet on the dashboard, kept visibly apart from the paper portfolio:
 * different heading, a READ-ONLY badge, and no link to bots or orders.
 */
export function WalletCard() {
  const w = useWallet();

  return (
    <section
      aria-labelledby="wallet-heading"
      className="card glow-ring overflow-hidden p-5 sm:p-6"
      style={{ ["--g1" as string]: "#a46bff", ["--g2" as string]: "#38c8ff" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="wallet-heading" className="font-display text-lg font-semibold">Your Phantom wallet</h2>
            <ReadOnlyBadge />
            {isMock(w.mock, w.balances) && <MockBadge />}
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-3">
            <ShieldOff className="size-3.5 shrink-0" aria-hidden />
            Real on-chain balances. Separate from the paper portfolio; the bots cannot trade it.
          </p>
        </div>
        {w.status === "connected" && w.address && (
          <span className="tabular rounded-xl border border-line bg-white/[0.03] px-3 py-1.5 text-xs text-ink-2" title={w.address}>
            {shortAddress(w.address, 6, 6)}
          </span>
        )}
      </div>

      {w.status === "connected" ? (
        <div className="mt-5">
          <BalancesState>
            {(s) => (
              <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
                <div className="min-w-0">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-ink-3">Priced value</p>
                  <p className="tabular font-display text-3xl font-semibold text-ink">{s.totalUsd === null ? "Unavailable" : usd(s.totalUsd)}</p>
                  <div className="mt-3">
                    <HoldingsList snapshot={s} />
                  </div>
                </div>
                <div className="flex min-w-0 flex-col gap-4">
                  <AllocationRing snapshot={s} />
                  <div className="mt-auto">
                    <SourceLine snapshot={s} />
                  </div>
                </div>
              </div>
            )}
          </BalancesState>
        </div>
      ) : (
        <div className="mt-5 grid items-center gap-5 md:grid-cols-[1fr_1.2fr]">
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm text-ink-2">
              {w.status === "not-installed"
                ? "Phantom was not found in this browser."
                : "Connect to see your SOL and supported token balances here. Nothing is shared until you approve in Phantom."}
            </p>
            <CardAction />
          </div>
          <PermissionsNote />
        </div>
      )}
    </section>
  );
}

function CardAction() {
  const w = useWallet();
  const cls =
    "inline-flex h-10 items-center gap-2 rounded-xl bg-gradient-to-r from-violet to-iris px-4 text-sm font-semibold text-white shadow-[0_8px_28px_-10px_#a46bff] hover:brightness-110 disabled:cursor-wait";
  if (w.status === "not-installed") {
    return isMobileBrowser() ? (
      <a href={phantomBrowseLink(window.location.href)} className={cls}>
        <Smartphone className="size-4" aria-hidden /> Open in Phantom
      </a>
    ) : (
      <a href={PHANTOM_DOWNLOAD} target="_blank" rel="noopener noreferrer" className={cls}>
        <Download className="size-4" aria-hidden /> Install Phantom
      </a>
    );
  }
  const busy = w.status === "connecting" || w.status === "detecting";
  return (
    <button type="button" disabled={busy} onClick={() => void w.connect()} className={cls}>
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Wallet className="size-4" aria-hidden />}
      {w.status === "connecting" ? "Approve in Phantom…" : w.status === "detecting" ? "Looking for Phantom…" : "Connect Phantom"}
    </button>
  );
}
