"use client";

import type { ReactNode } from "react";
import { Eye, FlaskConical, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { Donut } from "@/components/charts/donut";
import { TokenIcon } from "@/components/ui/token-icon";
import { SkeletonRows } from "@/components/ui/states";
import { pct, price, usd, utcDateTime } from "@/lib/format";
import { allocation, type Holding, type WalletSnapshot } from "@/lib/wallet/balances";
import { useWallet, type Balances } from "@/lib/wallet/wallet-context";

export function ReadOnlyBadge() {
  return (
    <span
      title="This app can only see the wallet's public address and balances. It cannot sign, send or approve anything."
      className="inline-flex items-center gap-1 rounded-full border border-sky/30 bg-sky/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-sky"
    >
      <Eye className="size-3" aria-hidden />
      Read-only
    </span>
  );
}

/** Shown whenever the wallet or its balances come from the development mocks. */
export function MockBadge() {
  return (
    <span
      title="Development mock: a pretend wallet and pretend balances. No real wallet or funds are involved."
      className="inline-flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gold"
    >
      <FlaskConical className="size-3" aria-hidden />
      Mock
    </span>
  );
}

export function isMock(mockProvider: boolean, balances: Balances): boolean {
  return mockProvider || (balances.state === "ok" && balances.snapshot.mock);
}

/** Exactly what the connection allows, in plain words. Kept in step with frontend/README.md. */
export function PermissionsNote({ compact = false }: { compact?: boolean }) {
  return (
    <div className="rounded-2xl border border-sky/20 bg-sky/[0.06] p-3.5 text-xs leading-relaxed text-ink-2">
      <p className="flex items-center gap-1.5 font-semibold text-ink">
        <ShieldCheck className="size-3.5 text-sky" aria-hidden />
        What connecting shares
      </p>
      <p className="mt-1">
        Only your wallet&apos;s <strong className="text-ink">public address</strong>. Balances are then read from the public
        Solana network. This app never asks Phantom to sign a message or transaction, never requests approvals or spending
        limits, and never asks for your recovery phrase. The bots cannot trade this wallet.
      </p>
      {!compact && (
        <p className="mt-1.5 text-ink-3">
          Disconnect here, or remove this site from the connected apps in Phantom's settings, at any time.
        </p>
      )}
    </div>
  );
}

function amount(h: Holding): string {
  return h.amount.toLocaleString("en-US", { maximumFractionDigits: h.amount >= 1 ? 4 : 6 });
}

export function HoldingsList({ snapshot }: { snapshot: WalletSnapshot }) {
  const shares = new Map(allocation(snapshot).map((a) => [a.symbol, a.pct]));
  return (
    <div>
      <ul className="divide-y divide-line">
        {snapshot.holdings.map((h) => (
          <li key={h.mint} className="flex items-center gap-3 py-2.5">
            <TokenIcon symbol={h.symbol} color={h.color} size={34} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-ink">{h.symbol}</p>
              <p className="truncate text-xs text-ink-3">
                {h.name}
                {h.usdPrice !== null && <span className="tabular"> · {price(h.usdPrice)}</span>}
              </p>
            </div>
            <div className="text-right">
              <p className="tabular text-sm font-medium text-ink" title={`${h.amountText} ${h.symbol}`}>
                {amount(h)}
              </p>
              <p className="tabular text-xs text-ink-3">
                {h.usdValue === null ? "price unavailable" : `${usd(h.usdValue)}${shares.has(h.symbol) ? ` · ${pct(shares.get(h.symbol) ?? 0)}` : ""}`}
              </p>
            </div>
          </li>
        ))}
      </ul>
      {(snapshot.unrecognisedTokens > 0 || snapshot.nftLike > 0) && (
        <p className="mt-2 text-xs text-ink-3">
          Not shown:{" "}
          {[
            snapshot.unrecognisedTokens > 0 && `${snapshot.unrecognisedTokens} token${snapshot.unrecognisedTokens > 1 ? "s" : ""} outside the supported list`,
            snapshot.nftLike > 0 && `${snapshot.nftLike} NFT${snapshot.nftLike > 1 ? "s" : ""} or collectible${snapshot.nftLike > 1 ? "s" : ""}`,
          ]
            .filter(Boolean)
            .join(", ")}
          .
        </p>
      )}
    </div>
  );
}

export function AllocationRing({ snapshot, size = 168 }: { snapshot: WalletSnapshot; size?: number }) {
  const slices = allocation(snapshot).map((a) => ({ label: a.symbol, value: a.value, color: a.color }));
  if (!slices.length) {
    return <p className="text-sm text-ink-3">Allocation needs prices, and none are available right now.</p>;
  }
  return (
    <Donut
      slices={slices}
      size={size}
      thickness={18}
      formatValue={(s, total) => pct((s.value / total) * 100)}
      center={(active) => (
        <>
          <span className="text-[10px] uppercase tracking-[0.16em] text-ink-3">{active ? active.label : "Total"}</span>
          <span className="tabular font-display text-lg font-semibold text-ink">{usd(active ? active.value : (snapshot.totalUsd ?? 0), 0)}</span>
        </>
      )}
    />
  );
}

export function SourceLine({ snapshot }: { snapshot: WalletSnapshot }) {
  return (
    <p className="text-[11px] text-ink-3">
      {snapshot.mock ? "Mock Solana RPC" : "Solana mainnet RPC"}
      {snapshot.slot !== null && <span className="tabular"> · slot {snapshot.slot.toLocaleString("en-US")}</span>}
      {snapshot.fetchedAt && <span> · read {utcDateTime(snapshot.fetchedAt)}</span>}
      {" · "}
      {snapshot.pricesAvailable ? "USD prices: Jupiter price API" : "USD prices unavailable"}
    </p>
  );
}

/** Loading, error and empty handling around a snapshot, shared by the panel and the dashboard card. */
export function BalancesState({ children }: { children: (snapshot: WalletSnapshot) => ReactNode }) {
  const { balances, refresh } = useWallet();
  if (balances.state === "ok") return <>{children(balances.snapshot)}</>;
  if (balances.state === "error") {
    return (
      <div role="alert" className="flex flex-col items-start gap-2 rounded-2xl border border-rose/25 bg-rose/[0.06] p-3.5 text-sm">
        <p className="flex items-center gap-1.5 font-medium text-rose">
          <TriangleAlert className="size-4" aria-hidden /> Balances unavailable
        </p>
        <p className="text-xs text-ink-2">{balances.message} Your wallet is still connected; nothing is shown rather than a guess.</p>
        <button type="button" onClick={refresh} className="inline-flex items-center gap-1.5 text-xs font-medium text-ink hover:text-violet">
          <RefreshCw className="size-3.5" aria-hidden /> Try again
        </button>
      </div>
    );
  }
  return <SkeletonRows rows={3} />;
}
