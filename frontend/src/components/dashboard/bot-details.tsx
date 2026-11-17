"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { AreaChart } from "@/components/charts/area-chart";
import { BotIcon } from "@/components/ui/bot-icon";
import { Chip, DemoBadge, StatusDot } from "@/components/ui/badges";
import { EmptyState } from "@/components/ui/states";
import { type BotIdentity, buildLabel } from "@/lib/bots";
import { useDataMode } from "@/lib/data-mode";
import { signedPct, utcDateTime, utcTime } from "@/lib/format";
import { ACTIVITY, BOT_DEMO } from "@/lib/sample-data";

/** Full profile of a bot: a side panel on desktop, a bottom sheet on phones. */
export function BotDetails({ bot, open, onClose }: { bot: BotIdentity; open: boolean; onClose: () => void }) {
  const { mode } = useDataMode();
  const demo = mode === "demo";
  const stats = BOT_DEMO[bot.id];
  const signals = ACTIVITY.filter((a) => a.bot === bot.id);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label={`${bot.name} details`}>
      <div className="absolute inset-0 animate-[rise_0.25s_ease-out_both] bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        className="absolute inset-x-0 bottom-0 max-h-[88dvh] animate-[rise_0.35s_cubic-bezier(0.2,0.7,0.2,1)_both] overflow-y-auto rounded-t-3xl border border-line-strong bg-night p-5 sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[460px] sm:rounded-none sm:rounded-l-3xl sm:p-7"
        style={{ boxShadow: `0 0 80px -20px rgb(${bot.glow} / 0.5)` }}
      >
        <div className="pointer-events-none absolute -top-20 right-0 size-72 rounded-full opacity-25 blur-3xl" style={{ background: bot.g1 }} />
        <div className="relative flex items-start gap-4">
          <BotIcon bot={bot} size={56} />
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-xl font-bold text-ink">{bot.name}</h2>
            <p className="text-sm text-ink-3">{bot.tagline}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusDot status={demo ? stats.status : "offline"} />
              <Chip>{bot.strategy}</Chip>
              {demo && <DemoBadge />}
            </div>
          </div>
          <button type="button" onClick={onClose} className="rounded-xl p-2 text-ink-3 hover:bg-white/5 hover:text-ink" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>

        <section className="relative mt-6 rounded-2xl border border-line bg-white/[0.03] p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-3">Real implementation status</p>
          <p className="mt-1 text-sm text-ink">{buildLabel(bot.build)}</p>
          {bot.build.kind === "data_ready" && <p className="mt-1 text-xs text-ink-3">{bot.build.data}</p>}
        </section>

        <section className="relative mt-5">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-display text-sm font-semibold text-ink">Simulated performance</h3>
            {demo && <span className={`tabular text-sm font-semibold ${stats.pnlPct >= 0 ? "text-mint" : "text-rose"}`}>{signedPct(stats.pnlPct, 1)}</span>}
          </div>
          {demo ? (
            <AreaChart data={stats.spark} from={bot.g2} to={bot.g1} height={150} formatValue={(v) => signedPct(v, 1)} formatTime={utcDateTime} ariaLabel={`${bot.name} sample return`} />
          ) : (
            <EmptyState title="No verified trades">Performance appears once the strategy is built and has completed paper trades.</EmptyState>
          )}
        </section>

        <section className="relative mt-5 grid gap-4 sm:grid-cols-2">
          <Block title="Looks for" items={bot.focus} color={bot.g1} />
          <Block title="Signals it will use" items={bot.signals} color={bot.g2} />
        </section>
        <section className="relative mt-4">
          <Block title="Data sources" items={bot.dataSources} color="#38c8ff" />
        </section>

        <section className="relative mt-5">
          <h3 className="mb-2 font-display text-sm font-semibold text-ink">Recent signals</h3>
          {demo && signals.length > 0 ? (
            <ul className="space-y-2">
              {signals.map((s) => (
                <li key={s.id} className="rounded-xl border border-line bg-white/[0.03] p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">{s.asset}: {s.title}</span>
                    <span className="tabular text-xs text-ink-3">{utcTime(s.time)}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink-3">{s.explanation}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">{demo ? "No sample signals for this bot." : "None: the bot does not run yet."}</p>
          )}
        </section>
      </div>
    </div>,
    document.body,
  );
}

function Block({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white/[0.02] p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">{title}</p>
      <ul className="space-y-1.5 text-sm text-ink-2">
        {items.map((i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-2 size-1.5 shrink-0 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}
