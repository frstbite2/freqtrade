/**
 * Which backend paths the browser may reach through /api/platform/... (GET only).
 * Anything else is refused before a request leaves the Next.js server.
 */

export const ALLOWED_PREFIXES: readonly string[][] = [
  ["health"],
  ["api", "v1", "status"],
  ["api", "v1", "config"],
  ["api", "v1", "jobs"],
  ["api", "v1", "health", "ingestion"],
  ["api", "v1", "insider"],
  ["api", "v1", "institutional"],
  ["api", "v1", "ownership"],
  ["api", "v1", "market"],
  ["api", "v1", "technical"],
];

const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export function isAllowedPath(segments: string[]): boolean {
  if (segments.length === 0 || segments.length > 8) return false;
  if (!segments.every((s) => SEGMENT.test(s) && s !== "." && s !== "..")) return false;
  return ALLOWED_PREFIXES.some(
    (prefix) => prefix.length <= segments.length && prefix.every((p, i) => segments[i] === p),
  );
}
