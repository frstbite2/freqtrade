"use client";

import { KeyRound, Lock, MonitorSmartphone } from "lucide-react";
import { SourceStatus } from "@/components/dashboard/source-status";
import { DataModeToggle } from "@/components/shell/data-mode-toggle";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section";
import { useDataMode } from "@/lib/data-mode";

export function SettingsView() {
  const { mode } = useDataMode();
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Preferences" title="Settings" subtitle="What the interface shows, and how it reaches the platform." />
      <div className="grid gap-6 xl:grid-cols-2">
        <section className="card p-5 sm:p-6">
          <SectionHeader title="Data shown" subtitle="Remembered in this browser only" right={<DataModeToggle />} />
          <div className="space-y-3 text-sm">
            <Option active={mode === "demo"} title="Demo" text="The design prototype's sample values, every one marked DEMO. For trying out the interface." />
            <Option active={mode === "live"} title="Live" text="Only what the platform API returns. Anything not built yet says so instead of showing a number." />
          </div>
        </section>
        <SourceStatus />
        <section className="card p-5 sm:p-6 xl:col-span-2">
          <SectionHeader title="Security" />
          <ul className="grid gap-3 sm:grid-cols-3">
            <Note icon={<KeyRound className="size-4 text-gold" aria-hidden />} title="Credentials stay on the server">
              The API token lives only in the frontend server's environment. The browser talks to this app, never to the backend directly.
            </Note>
            <Note icon={<Lock className="size-4 text-mint" aria-hidden />} title="Paper trading only">
              No deposits, withdrawals, transfers or wallet connections exist. Live trading is a validation error in the backend.
            </Note>
            <Note icon={<MonitorSmartphone className="size-4 text-sky" aria-hidden />} title="Private by default">
              Meant for localhost or a trusted network. Search engines are told not to index it.
            </Note>
          </ul>
        </section>
      </div>
    </div>
  );
}

function Option({ active, title, text }: { active: boolean; title: string; text: string }) {
  return (
    <div className={`rounded-2xl border p-4 transition-colors ${active ? "border-violet/40 bg-violet/10" : "border-line bg-black/15"}`}>
      <p className="font-semibold text-ink">{title}{active && <span className="ml-2 text-xs font-medium text-violet">selected</span>}</p>
      <p className="mt-1 text-ink-3">{text}</p>
    </div>
  );
}

function Note({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <li className="rounded-2xl border border-line bg-black/15 p-4 text-sm">
      <p className="flex items-center gap-2 font-semibold text-ink">{icon}{title}</p>
      <p className="mt-1.5 text-ink-3">{children}</p>
    </li>
  );
}
