"use client";

import { Check, Copy, Download, ExternalLink, Loader2, LogOut, RefreshCw, Smartphone, Wallet, X } from "lucide-react";
import { type Ref, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { shortAddress } from "@/lib/wallet/address";
import { PHANTOM_DOWNLOAD, isMobileBrowser, phantomBrowseLink } from "@/lib/wallet/phantom";
import { useWallet } from "@/lib/wallet/wallet-context";
import { AllocationRing, BalancesState, HoldingsList, MockBadge, PermissionsNote, ReadOnlyBadge, SourceLine, isMock } from "./wallet-ui";
import { usd } from "@/lib/format";

const BASE =
  "inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 text-sm font-semibold transition-all disabled:cursor-wait";
const PRIMARY = `${BASE} bg-gradient-to-r from-violet to-iris text-white shadow-[0_8px_28px_-10px_#a46bff] hover:brightness-110`;
const QUIET = `${BASE} border border-line bg-white/[0.03] text-ink-2 hover:border-line-strong hover:text-ink`;

/** Top-right wallet control: detect, connect, and a read-only panel once connected. */
export function ConnectWallet() {
  const w = useWallet();
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState({ top: 72, right: 16 });
  const button = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (w.status !== "connected") setOpen(false);
  }, [w.status]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const resize = () => setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    window.addEventListener("resize", resize);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("resize", resize);
    };
  }, [open]);

  const toggle = () => {
    // The header blurs its backdrop, which traps position:fixed children, so the panel is portalled
    // to <body> and placed under the button.
    const r = button.current?.getBoundingClientRect();
    if (r) setAnchor({ top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) });
    setOpen((o) => !o);
  };

  const sol = w.balances.state === "ok" ? w.balances.snapshot.holdings[0] : null;

  let control;
  switch (w.status) {
    case "detecting":
      control = (
        <button type="button" disabled className={QUIET} aria-label="Looking for Phantom">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          <span className="hidden sm:inline">Phantom</span>
        </button>
      );
      break;
    case "not-installed":
      control = isMobileBrowser() ? (
        // Mobile browsers have no extensions: open this page in Phantom's in-app browser instead.
        <a href={phantomBrowseLink(window.location.href)} className={PRIMARY} aria-label="Open this page in the Phantom app">
          <Smartphone className="size-4" aria-hidden />
          <span className="max-[359px]:hidden sm:hidden">Phantom</span>
          <span className="hidden sm:inline">Open in Phantom</span>
        </a>
      ) : (
        <a href={PHANTOM_DOWNLOAD} target="_blank" rel="noopener noreferrer" className={QUIET} title="Phantom was not found in this browser">
          <Download className="size-4" aria-hidden />
          <span className="hidden sm:inline">Install Phantom</span>
        </a>
      );
      break;
    case "disconnected":
      control = (
        <button type="button" onClick={() => void w.connect()} className={PRIMARY} aria-label="Connect Phantom">
          <Wallet className="size-4" aria-hidden />
          <span className="max-[359px]:hidden sm:hidden">Connect</span>
          <span className="hidden sm:inline">Connect Phantom</span>
        </button>
      );
      break;
    case "connecting":
      control = (
        <button type="button" disabled className={PRIMARY} aria-live="polite">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          <span className="max-[359px]:hidden">Approve in Phantom…</span>
        </button>
      );
      break;
    case "connected":
      control = (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={`Phantom wallet ${w.address}, read-only. Open wallet details`}
          className={`${QUIET} pl-1.5 text-ink`}
        >
          <span className="relative flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet to-flare">
            <Wallet className="size-3.5 text-white" aria-hidden />
            <span className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-void bg-mint" />
          </span>
          <span className="tabular max-[359px]:hidden">{shortAddress(w.address ?? "")}</span>
          {sol && <span className="tabular hidden border-l border-line pl-2 text-ink-2 md:inline">{sol.amount.toLocaleString("en-US", { maximumFractionDigits: 3 })} SOL</span>}
          {isMock(w.mock, w.balances) && <span className="hidden size-1.5 rounded-full bg-gold md:inline-block" title="Mock wallet" />}
        </button>
      );
      break;
  }

  return (
    <div ref={button} className="relative">
      {control}
      {w.error && (
        <div role="alert" className="card absolute right-0 top-12 z-50 flex w-[min(20rem,calc(100vw-2rem))] animate-rise gap-2 p-3 text-xs text-ink-2">
          <p className="flex-1">{w.error}</p>
          <button type="button" onClick={w.clearError} aria-label="Dismiss" className="self-start text-ink-3 hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
      )}
      {open && w.address && createPortal(<WalletPanel ref={panel} anchor={anchor} onClose={() => setOpen(false)} />, document.body)}
    </div>
  );
}

function WalletPanel({ ref, anchor, onClose }: { ref: Ref<HTMLDivElement>; anchor: { top: number; right: number }; onClose: () => void }) {
  const w = useWallet();
  const [copied, setCopied] = useState(false);
  const address = w.address ?? "";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked: the full address is visible in the title for manual copying.
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm sm:hidden" aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-label="Phantom wallet, read-only"
        style={{ ["--top" as string]: `${anchor.top}px`, ["--right" as string]: `${anchor.right}px` }}
        className="card fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] animate-rise overflow-y-auto rounded-b-none p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:inset-x-auto sm:bottom-auto sm:right-[var(--right)] sm:top-[var(--top)] sm:w-[25rem] sm:rounded-b-3xl"
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15 sm:hidden" aria-hidden />
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-display text-base font-semibold">Phantom wallet</span>
              <ReadOnlyBadge />
              {isMock(w.mock, w.balances) && <MockBadge />}
            </div>
            <button type="button" onClick={copy} title={address} className="tabular mt-1 inline-flex items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
              {shortAddress(address, 6, 6)}
              {copied ? <Check className="size-3.5 text-mint" aria-label="Copied" /> : <Copy className="size-3.5" aria-label="Copy address" />}
            </button>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1 text-ink-3 hover:text-ink">
            <X className="size-5" />
          </button>
        </div>

        <div className="mt-4">
          <BalancesState>
            {(s) => (
              <div className="space-y-4">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.16em] text-ink-3">Priced value</p>
                  <p className="tabular font-display text-3xl font-semibold text-ink">{s.totalUsd === null ? "Unavailable" : usd(s.totalUsd)}</p>
                </div>
                <HoldingsList snapshot={s} />
                <AllocationRing snapshot={s} size={140} />
                <SourceLine snapshot={s} />
              </div>
            )}
          </BalancesState>
        </div>

        <div className="mt-4">
          <PermissionsNote compact />
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
          <button type="button" onClick={w.refresh} className="flex flex-col items-center gap-1 rounded-xl border border-line bg-white/[0.03] py-2.5 text-ink-2 hover:text-ink">
            <RefreshCw className="size-4" aria-hidden /> Refresh
          </button>
          <a
            href={`https://solscan.io/account/${address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-1 rounded-xl border border-line bg-white/[0.03] py-2.5 text-ink-2 hover:text-ink"
          >
            <ExternalLink className="size-4" aria-hidden /> Explorer
          </a>
          <button type="button" onClick={() => void w.disconnect()} className="flex flex-col items-center gap-1 rounded-xl border border-rose/25 bg-rose/[0.06] py-2.5 text-rose hover:bg-rose/10">
            <LogOut className="size-4" aria-hidden /> Disconnect
          </button>
        </div>
      </div>
    </>
  );
}
