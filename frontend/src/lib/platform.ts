"use client";

import { useEffect, useState } from "react";

/** The result of a call to the backend through the server-side proxy. */
export type Remote<T> =
  | { state: "loading" }
  | { state: "ok"; data: T }
  | { state: "unavailable"; status: number; message: string }
  | { state: "offline" };

/** GET /api/platform/<path>. Never talks to the backend directly, so no secret is needed here. */
export function usePlatform<T>(path: string | null, refreshMs?: number): Remote<T> {
  const [result, setResult] = useState<Remote<T>>({ state: "loading" });

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(`/api/platform/${path}`, { cache: "no-store" });
        const body = await response.json().catch(() => ({}));
        if (cancelled) return;
        if (response.status === 502) setResult({ state: "offline" });
        else if (!response.ok)
          setResult({
            state: "unavailable",
            status: response.status,
            message: typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`,
          });
        else setResult({ state: "ok", data: body as T });
      } catch {
        if (!cancelled) setResult({ state: "offline" });
      }
    };
    void load();
    const timer = refreshMs ? setInterval(load, refreshMs) : undefined;
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [path, refreshMs]);

  return path === null ? { state: "loading" } : result;
}

export interface PlatformStatus {
  version: string;
  environment: string;
  trading_mode: string;
  providers_configured: Record<string, boolean>;
}
