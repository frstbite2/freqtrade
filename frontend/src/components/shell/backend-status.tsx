"use client";

import { usePlatform } from "@/lib/platform";

/** Real check, every 30 s: is the FastAPI backend reachable from the frontend server? */
export function BackendStatus() {
  const health = usePlatform<{ status: string; database: string }>("health", 30_000);
  const view =
    health.state === "loading"
      ? { label: "Checking", dot: "bg-ink-3", text: "text-ink-3", title: "Checking the platform API" }
      : health.state === "ok" && health.data.status === "ok"
        ? { label: "API online", dot: "bg-mint", text: "text-mint", title: "Platform API and database reachable" }
        : health.state === "ok" || health.state === "unavailable"
          ? { label: "API degraded", dot: "bg-gold", text: "text-gold", title: "The platform API answered, but reports a problem" }
          : { label: "API offline", dot: "bg-rose", text: "text-rose", title: "The platform API is not reachable from this server" };
  return (
    <span title={view.title} className={`hidden items-center gap-2 rounded-xl border border-line bg-white/[0.03] px-3 py-1.5 text-xs font-medium sm:inline-flex ${view.text}`}>
      <span className={`size-1.5 rounded-full ${view.dot} shadow-[0_0_8px_currentColor]`} />
      {view.label}
    </span>
  );
}
