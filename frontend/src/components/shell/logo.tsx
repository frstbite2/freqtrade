"use client";

import { useId } from "react";
import { BRAND } from "@/lib/brand";

/** The mark: a glowing core inside a tilted orbit. */
export function LogoMark({ size = 34 }: { size?: number }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
      <defs>
        <radialGradient id={`core-${id}`} cx="35%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#ffd2a8" />
          <stop offset="45%" stopColor="#ff8a3d" />
          <stop offset="100%" stopColor="#a46bff" />
        </radialGradient>
        <linearGradient id={`ring-${id}`} x1="0" x2="1">
          <stop offset="0%" stopColor="#38c8ff" />
          <stop offset="100%" stopColor="#a46bff" />
        </linearGradient>
      </defs>
      <circle cx="20" cy="20" r="8.5" fill={`url(#core-${id})`} style={{ filter: "drop-shadow(0 0 6px #ff8a3d)" }} />
      <ellipse cx="20" cy="20" rx="17" ry="7.5" fill="none" stroke={`url(#ring-${id})`} strokeWidth="2" transform="rotate(-28 20 20)" />
      <circle cx="34.2" cy="12.6" r="2.2" fill="#38c8ff" style={{ filter: "drop-shadow(0 0 4px #38c8ff)" }} />
    </svg>
  );
}

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark />
      <div className="leading-tight">
        <div className="font-display text-lg font-bold tracking-tight text-ink">{BRAND.name}</div>
        <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-ink-3">{BRAND.tagline}</div>
      </div>
    </div>
  );
}
