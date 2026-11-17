import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { signedPct, signedUsd, trendOf } from "@/lib/format";

/** A change, coloured by direction, with an arrow so colour is never the only cue. */
export function Delta({
  value,
  kind = "pct",
  className = "",
  size = "sm",
}: {
  value: number;
  kind?: "pct" | "usd";
  className?: string;
  size?: "sm" | "md";
}) {
  const trend = trendOf(value);
  const color = trend === "up" ? "text-mint" : trend === "down" ? "text-rose" : "text-ink-3";
  const Icon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;
  return (
    <span
      className={`tabular inline-flex items-center gap-0.5 font-semibold ${color} ${size === "md" ? "text-sm" : "text-xs"} ${className}`}
    >
      <Icon className={size === "md" ? "size-4" : "size-3.5"} aria-hidden />
      {kind === "pct" ? signedPct(value) : signedUsd(value)}
    </span>
  );
}
