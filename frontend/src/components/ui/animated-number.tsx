"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Counts up to `value` when it first appears, and glides to new values after that.
 * The server renders the final value, so there is no layout jump and no hydration mismatch.
 */
export function AnimatedNumber({
  value,
  format,
  duration = 1400,
  from = 0.9,
  className = "",
}: {
  value: number;
  format: (n: number) => string;
  duration?: number;
  from?: number;
  className?: string;
}) {
  const [shown, setShown] = useState(value);
  const previous = useRef<number | null>(null);

  useEffect(() => {
    const start = previous.current ?? value * from;
    previous.current = value;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    let frame = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 4);
      setShown(start + (value - start) * eased);
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, from]);

  return <span className={`tabular ${className}`}>{format(shown)}</span>;
}
