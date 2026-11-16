"use client";

import { Check, X } from "lucide-react";
import { SectionHeader } from "@/components/ui/section";
import { useWallet } from "@/lib/wallet/wallet-context";
import { ReadOnlyBadge } from "./wallet-ui";

const GRANTS = [
  "Your wallet's public address, which Phantom shares when you approve the connection.",
  "Public balances for that address (SOL and supported tokens), read by this app's server from the Solana network.",
];
const NEVER = [
  "Signing messages or transactions, or sending anything.",
  "Token approvals, delegations or spending limits.",
  "Your recovery phrase or private keys. Phantom never gives these to any site; anyone asking for them is a scam.",
  "Deposits into this app. The bots trade paper money only and never use this wallet.",
];

/** The wallet connection's permissions, spelled out. Mirrors frontend/README.md. */
export function WalletPermissions() {
  const w = useWallet();
  return (
    <section className="card p-5 sm:p-6 xl:col-span-2">
      <SectionHeader
        title="Phantom wallet permissions"
        subtitle={w.status === "connected" ? "Connected now. Disconnect from the wallet button at the top right." : "Not connected"}
        right={<ReadOnlyBadge />}
      />
      <div className="grid gap-4 text-sm md:grid-cols-2">
        <div className="rounded-2xl border border-mint/20 bg-mint/[0.05] p-4">
          <p className="font-semibold text-ink">This app can see</p>
          <ul className="mt-2 space-y-2 text-ink-2">
            {GRANTS.map((g) => (
              <li key={g} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-mint" aria-hidden />{g}</li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-rose/20 bg-rose/[0.05] p-4">
          <p className="font-semibold text-ink">This app never asks for</p>
          <ul className="mt-2 space-y-2 text-ink-2">
            {NEVER.map((g) => (
              <li key={g} className="flex gap-2"><X className="mt-0.5 size-4 shrink-0 text-rose" aria-hidden />{g}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-4 text-xs leading-relaxed text-ink-3">
        A connected site could in principle ask Phantom for a signature later; Phantom would show every such request for
        your approval. This app contains no code that makes one, and a test fails if one is ever added. To revoke the
        connection entirely, use Disconnect here and remove this site from the connected apps in Phantom's settings.
      </p>
    </section>
  );
}
