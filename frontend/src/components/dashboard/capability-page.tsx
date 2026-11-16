import { CheckCircle2, Clock3, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { SourceStatus } from "./source-status";

export interface Capability {
  title: string;
  detail: string;
  ready: boolean;
}

/** A section whose data the backend has (or will have), with what connects in which stage. */
export function CapabilityPage({
  eyebrow,
  title,
  subtitle,
  icon: Icon,
  colors,
  capabilities,
  note,
  sources,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  colors: [string, string];
  capabilities: Capability[];
  note: ReactNode;
  sources?: string[];
  children?: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle} />
      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <section className="card glow-ring relative overflow-hidden p-6" style={{ ["--g1" as string]: colors[0], ["--g2" as string]: colors[1] }}>
          <div className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full opacity-25 blur-3xl" style={{ background: colors[0] }} />
          <div className="relative flex items-center gap-3">
            <span className="flex size-12 items-center justify-center rounded-2xl text-white" style={{ background: `linear-gradient(140deg, ${colors[0]}, ${colors[1]})`, boxShadow: `0 12px 30px -12px ${colors[0]}` }}>
              <Icon className="size-6" aria-hidden />
            </span>
            <div>
              <h2 className="font-display text-lg font-semibold text-ink">What this section will show</h2>
              <p className="text-sm text-ink-3">{note}</p>
            </div>
          </div>
          <ul className="relative mt-6 grid gap-3 sm:grid-cols-2">
            {capabilities.map((c) => (
              <li key={c.title} className="rounded-2xl border border-line bg-black/20 p-4">
                <div className="flex items-center gap-2">
                  {c.ready ? <CheckCircle2 className="size-4 text-mint" aria-hidden /> : <Clock3 className="size-4 text-gold" aria-hidden />}
                  <p className="text-sm font-semibold text-ink">{c.title}</p>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-ink-3">{c.detail}</p>
                <p className={`mt-2 text-[11px] font-semibold uppercase tracking-wider ${c.ready ? "text-mint" : "text-gold"}`}>
                  {c.ready ? "In the backend today" : "Not built yet"}
                </p>
              </li>
            ))}
          </ul>
        </section>
        <div className="space-y-6">
          <SourceStatus only={sources} />
          {children}
        </div>
      </div>
    </div>
  );
}
