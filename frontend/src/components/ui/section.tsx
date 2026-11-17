import type { ReactNode } from "react";

export function SectionHeader({
  title,
  subtitle,
  right,
  eyebrow,
}: {
  title: string;
  subtitle?: ReactNode;
  right?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5">{eyebrow}</div>}
        <h2 className="font-display text-lg font-semibold tracking-tight text-ink sm:text-xl">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}
