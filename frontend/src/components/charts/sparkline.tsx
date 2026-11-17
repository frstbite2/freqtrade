import { useId } from "react";
import { areaPath, project, smoothPath } from "./path";

/** A compact trend line with a soft glow, coloured by direction unless a colour is given. */
export function Sparkline({
  values,
  color,
  width = 120,
  height = 40,
  className = "",
}: {
  values: number[];
  color?: string;
  width?: number;
  height?: number;
  className?: string;
}) {
  const id = useId().replace(/:/g, "");
  const up = values[values.length - 1] >= values[0];
  const stroke = color ?? (up ? "#36e3a1" : "#ff5c7a");
  const points = project(values, width, height, 0.12);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={className} width={width} height={height} aria-hidden>
      <defs>
        <linearGradient id={`sp-${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath(points, height)} fill={`url(#sp-${id})`} />
      <path d={smoothPath(points)} fill="none" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" style={{ filter: `drop-shadow(0 0 4px ${stroke}99)` }} />
    </svg>
  );
}
