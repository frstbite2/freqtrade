"use client";

import { useEffect, useState } from "react";

/** The result of a call to the backend through the server-side proxy. */
export type Remote<T> =
  | { state: "loading" }
  | { state: "ok"; data: T }
  /** The backend answered with an error. `body` is kept: some errors (a 503 health report) carry data. */
  | { state: "unavailable"; status: number; message: string; body: unknown }
  | { state: "offline" };

/** GET /api/platform/<path>. Never talks to the backend directly, so no secret is needed here. */
export async function fetchPlatform<T>(path: string): Promise<Remote<T>> {
  try {
    const response = await fetch(`/api/platform/${path}`, { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (response.status === 502) return { state: "offline" };
    if (!response.ok) {
      const message = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
      return { state: "unavailable", status: response.status, message, body };
    }
    return { state: "ok", data: body as T };
  } catch {
    return { state: "offline" };
  }
}

export function usePlatform<T>(path: string | null, refreshMs?: number): Remote<T> {
  const [result, setResult] = useState<Remote<T>>({ state: "loading" });

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setResult({ state: "loading" });
    const load = async () => {
      const next = await fetchPlatform<T>(path);
      if (!cancelled) setResult(next);
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
