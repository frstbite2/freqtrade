"use client";

import { useState, type ReactNode } from "react";

export interface Slice {
  label: string;
  value: number;
  color: string;
}

/** Allocation ring. Hovering (or tapping) a slice or its legend row brings it forward. */
export function Donut({
  slices,
  size = 200,
  thickness = 22,
  center,
  formatValue,
}: {
  slices: Slice[];
  size?: number;
  thickness?: number;
  center: (active: Slice | null) => ReactNode;
  formatValue: (s: Slice, total: number) => string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = (size - thickness) / 2 - 6;
  const c = 2 * Math.PI * r;
  const gap = 0.012 * c;
  let offset = 0;

  return (
    <div className="@container w-full">
    <div className="flex flex-col items-center gap-5 @md:flex-row @md:items-center">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / 0.05)" strokeWidth={thickness} />
          {slices.map((s, i) => {
            const len = (s.value / total) * c;
            const dash = `${Math.max(0, len - gap)} ${c}`;
            const el = (
              <circle
                key={s.label}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={active === i ? thickness + 8 : thickness}
                strokeDasharray={dash}
                strokeDashoffset={-offset}
                strokeLinecap="round"
                className="cursor-pointer transition-all duration-300"
                style={{
                  opacity: active === null || active === i ? 1 : 0.35,
                  filter: active === i ? `drop-shadow(0 0 10px ${s.color})` : `drop-shadow(0 0 4px ${s.color}55)`,
                }}
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
              />
            );
            offset += len;
            return el;
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          {center(active === null ? null : slices[active])}
        </div>
      </div>
      <ul className="grid w-full grid-cols-2 gap-x-4 gap-y-1.5 text-sm @md:grid-cols-1">
        {slices.map((s, i) => (
          <li key={s.label}>
            <button
              type="button"
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              onClick={() => setActive(active === i ? null : i)}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left transition-colors ${active === i ? "bg-white/8" : "hover:bg-white/5"}`}
            >
              <span className="size-2.5 shrink-0 rounded-full" style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }} />
              <span className="flex-1 truncate text-ink-2">{s.label}</span>
              <span className="tabular font-medium text-ink">{formatValue(s, total)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
    </div>
  );
}
