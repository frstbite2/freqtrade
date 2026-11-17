"use client";

import { useMemo, useRef, useState } from "react";
import { smoothPath } from "./path";

export interface Series {
  id: string;
  label: string;
  color: string;
  values: number[];
}

const W = 1000;

/** Several return curves on one scale; legend chips toggle lines, the crosshair reads them all. */
export function CompareChart({
  series,
  height = 240,
  format,
}: {
  series: Series[];
  height?: number;
  format: (v: number) => string;
}) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const shown = series.filter((s) => !hidden.has(s.id));
  const n = Math.max(...series.map((s) => s.values.length));

  const { lo, hi } = useMemo(() => {
    const all = (shown.length ? shown : series).flatMap((s) => s.values);
    const min = Math.min(0, ...all);
    const max = Math.max(0, ...all);
    const pad = (max - min) * 0.1 || 1;
    return { lo: min - pad, hi: max + pad };
  }, [shown, series]);

  const y = (v: number) => height - ((v - lo) / (hi - lo)) * height;
  const x = (i: number) => (i / (n - 1)) * W;

  const toggle = (id: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {series.map((s) => {
          const off = hidden.has(s.id);
          return (
            <button
              key={s.id}
              type="button"
              aria-pressed={!off}
              onClick={() => toggle(s.id)}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium transition-all ${off ? "border-line text-ink-3" : "border-line-strong bg-white/5 text-ink"}`}
            >
              <span className="size-2 rounded-full" style={{ background: off ? "transparent" : s.color, boxShadow: off ? `inset 0 0 0 1px ${s.color}` : `0 0 8px ${s.color}` }} />
              {s.label}
            </button>
          );
        })}
      </div>
      <div
        ref={box}
        className="relative w-full touch-pan-y select-none"
        style={{ height }}
        onPointerMove={(e) => {
          const r = box.current?.getBoundingClientRect();
          if (r) setHover(Math.round(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * (n - 1)));
        }}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label="Strategy return comparison"
      >
        <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
          <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="rgb(255 255 255 / 0.18)" strokeDasharray="5 6" vectorEffect="non-scaling-stroke" />
          {shown.map((s) => (
            <path
              key={s.id}
              d={smoothPath(s.values.map((v, i) => ({ x: x(i), y: y(v) })))}
              fill="none"
              stroke={s.color}
              strokeWidth={2.2}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              style={{ filter: `drop-shadow(0 0 6px ${s.color}88)`, transition: "d 0.5s ease" }}
            />
          ))}
        </svg>
        <span className="absolute left-0 text-[10px] text-ink-3" style={{ top: `calc(${(y(0) / height) * 100}% - 14px)` }}>0%</span>
        {hover !== null && shown.length > 0 && (
          <>
            <div className="pointer-events-none absolute inset-y-0 w-px bg-white/25" style={{ left: `${(x(hover) / W) * 100}%` }} />
            <div
              className="pointer-events-none absolute top-0 z-10 min-w-40 rounded-xl border border-line-strong bg-night/90 p-2.5 text-xs shadow-xl backdrop-blur"
              style={{ left: `clamp(0px, calc(${(x(hover) / W) * 100}% + 12px), calc(100% - 170px))` }}
            >
              {shown.map((s) => (
                <div key={s.id} className="flex items-center justify-between gap-4 py-0.5">
                  <span className="flex items-center gap-1.5 text-ink-2">
                    <span className="size-1.5 rounded-full" style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span className="tabular font-semibold text-ink">{format(s.values[Math.min(hover, s.values.length - 1)])}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
