"use client";

import { useId, useMemo, useRef, useState } from "react";
import type { Point } from "@/lib/sample-data";
import { areaPath, project, smoothPath } from "./path";

const W = 1000;

/**
 * The hero chart: a glowing gradient line that draws itself in, a soft area fill, and a
 * crosshair that follows the pointer (or finger) with the value under it.
 */
export function AreaChart({
  data,
  from = "#a46bff",
  to = "#ff8a3d",
  height = 220,
  formatValue,
  formatTime,
  ariaLabel,
}: {
  data: Point[];
  from?: string;
  to?: string;
  height?: number;
  formatValue: (v: number) => string;
  formatTime: (t: string) => string;
  ariaLabel: string;
}) {
  const id = useId().replace(/:/g, "");
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const points = useMemo(() => project(data.map((d) => d.v), W, height), [data, height]);
  const key = `${data[0]?.t}-${data.length}`; // re-draw the line when the series changes

  const onMove = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect || data.length === 0) return;
    const f = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setHover(Math.round(f * (data.length - 1)));
  };

  const active = hover ?? null;
  const p = active !== null ? points[active] : null;

  return (
    <div
      ref={box}
      className="relative w-full touch-pan-y select-none"
      style={{ height }}
      onPointerMove={(e) => onMove(e.clientX)}
      onPointerDown={(e) => onMove(e.clientX)}
      onPointerLeave={() => setHover(null)}
      role="img"
      aria-label={ariaLabel}
    >
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
        <defs>
          <linearGradient id={`stroke-${id}`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor={from} />
            <stop offset="100%" stopColor={to} />
          </linearGradient>
          <linearGradient id={`fill-${id}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={to} stopOpacity="0.28" />
            <stop offset="55%" stopColor={from} stopOpacity="0.10" />
            <stop offset="100%" stopColor={from} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1="0" x2={W} y1={height * f} y2={height * f} stroke="rgb(255 255 255 / 0.05)" strokeDasharray="4 8" vectorEffect="non-scaling-stroke" />
        ))}
        <path key={`a-${key}`} d={areaPath(points, height)} fill={`url(#fill-${id})`} className="animate-[rise_0.9s_ease-out_both]" />
        <path
          key={`l-${key}`}
          d={smoothPath(points)}
          fill="none"
          stroke={`url(#stroke-${id})`}
          strokeWidth={2.5}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          pathLength={1}
          style={{
            strokeDasharray: 1,
            strokeDashoffset: 1,
            animation: "draw-line 1.4s cubic-bezier(0.3, 0.7, 0.2, 1) forwards",
            filter: `drop-shadow(0 0 8px ${to}88)`,
          }}
        />
      </svg>

      {p && active !== null && (
        <>
          <div className="pointer-events-none absolute inset-y-0 w-px bg-gradient-to-b from-transparent via-white/30 to-transparent" style={{ left: `${(p.x / W) * 100}%` }} />
          <div
            className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white"
            style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / height) * 100}%`, background: to, boxShadow: `0 0 0 6px ${to}33, 0 0 18px ${to}` }}
          />
          <div
            className="pointer-events-none absolute -top-2 z-10 -translate-y-full rounded-xl border border-line-strong bg-night/90 px-3 py-2 text-xs shadow-xl backdrop-blur"
            style={{ left: `clamp(0px, calc(${(p.x / W) * 100}% - 70px), calc(100% - 140px))` }}
          >
            <div className="tabular font-display text-sm font-semibold text-ink">{formatValue(data[active].v)}</div>
            <div className="text-ink-3">{formatTime(data[active].t)}</div>
          </div>
        </>
      )}
    </div>
  );
}
