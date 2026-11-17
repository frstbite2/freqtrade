/** Number and time formatting. Fixed locale and UTC, so server and browser render the same. */

const LOCALE = "en-US";

export function usd(value: number, digits = 2): string {
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** "+$1,234.50" / "-$12.00": for profit and loss. */
export function signedUsd(value: number, digits = 2): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return sign + usd(Math.abs(value), digits);
}

/** "+2.41%" / "-0.80%". */
export function signedPct(value: number, digits = 2): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function pct(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

export function compact(value: number): string {
  return new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

/** Price with sensible precision: cents above $1, more digits below. */
export function price(value: number): string {
  if (value > 0 && value < 0.01) {
    // Sub-cent tokens: keep significant digits instead of rounding to $0.0000.
    return new Intl.NumberFormat(LOCALE, { style: "currency", currency: "USD", maximumSignificantDigits: 3 }).format(value);
  }
  return usd(value, value >= 1 ? 2 : 4);
}

export function utcTime(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(iso)) + " UTC";
}

/** "Nov 12": the date alone, in UTC. */
export function utcDate(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(iso));
}

export function utcDateTime(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(iso)) + " UTC";
}

export type Trend = "up" | "down" | "flat";

export function trendOf(value: number): Trend {
  return value > 0 ? "up" : value < 0 ? "down" : "flat";
}

/** "5 min ago", "3 days ago": how fresh a real record is. Needs the current time from the caller. */
export function ago(iso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - Date.parse(iso)) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}
