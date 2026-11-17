import { Lock, type LucideIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";

/** A section that waits on a milestone: what it will hold, and what it depends on. */
export function MilestonePage({
  eyebrow,
  title,
  subtitle,
  icon: Icon,
  milestone,
  colors,
  features,
  dependsOn,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  milestone: string;
  colors: [string, string];
  features: { title: string; detail: string }[];
  dependsOn: string[];
}) {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle} />
      <section className="card glow-ring relative overflow-hidden p-6 sm:p-8" style={{ ["--g1" as string]: colors[0], ["--g2" as string]: colors[1] }}>
        <div className="pointer-events-none absolute -left-20 -top-24 size-80 animate-float rounded-full opacity-20 blur-3xl" style={{ background: colors[0] }} />
        <div className="pointer-events-none absolute -bottom-24 right-0 size-72 rounded-full opacity-15 blur-3xl" style={{ background: colors[1] }} />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center">
          <div className="relative mx-auto flex size-32 shrink-0 items-center justify-center lg:mx-0">
            <span className="absolute inset-0 animate-spin-slow rounded-full border border-dashed" style={{ borderColor: `${colors[0]}66` }} />
            <span className="absolute inset-5 rounded-full border-2 border-transparent animate-[spin_5s_linear_infinite]" style={{ borderTopColor: colors[1] }} />
            <span className="flex size-14 items-center justify-center rounded-2xl text-white" style={{ background: `linear-gradient(140deg, ${colors[0]}, ${colors[1]})`, boxShadow: `0 0 40px -6px ${colors[0]}` }}>
              <Icon className="size-7" aria-hidden />
            </span>
          </div>
          <div className="text-center lg:text-left">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-white/5 px-3 py-1 text-xs font-semibold text-ink-2">
              <Lock className="size-3.5" aria-hidden /> Unlocks with {milestone}
            </span>
            <h2 className="mt-3 font-display text-2xl font-bold text-ink">Nothing to show yet, on purpose</h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-3">
              This section only shows results that were actually computed. Until {milestone} is built and
              tested, it stays empty rather than displaying invented numbers.
            </p>
            <p className="mt-3 text-xs text-ink-3">Depends on: {dependsOn.join(" · ")}</p>
          </div>
        </div>
        <ul className="relative mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {features.map((f) => (
            <li key={f.title} className="rounded-2xl border border-line bg-black/20 p-4">
              <p className="text-sm font-semibold text-ink">{f.title}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-3">{f.detail}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
