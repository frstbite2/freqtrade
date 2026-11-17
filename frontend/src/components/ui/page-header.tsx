import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, eyebrow, right }: { title: string; subtitle?: ReactNode; eyebrow?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-violet">{eyebrow}</div>}
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-ink-3 sm:text-base">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
