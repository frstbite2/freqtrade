"use client";

import { BOTS } from "@/lib/bots";
import { type PlatformStatus, usePlatform } from "@/lib/platform";
import type { Facts } from "@/lib/readiness";
import type { IngestionHealth } from "@/lib/sec";
import { BotCard } from "./bot-card";

export function BotGrid() {
  // Read once for all cards: which providers are configured, and how fresh the SEC data is.
  const status = usePlatform<PlatformStatus>("api/v1/status");
  const health = usePlatform<IngestionHealth>("api/v1/health/ingestion");
  const facts: Facts = {
    providers: status.state === "ok" ? status.data.providers_configured : null,
    ingestion:
      health.state === "ok"
        ? health.data
        : health.state === "unavailable" && health.status === 503 && health.body && typeof health.body === "object" && "jobs" in health.body
          ? (health.body as IngestionHealth)
          : null,
  };
  return (
    <div className="grid items-start gap-4 sm:grid-cols-2 sm:[&>*:last-child]:col-span-2 xl:grid-cols-6 xl:[&>*]:col-span-2 xl:[&>*:nth-last-child(-n+2)]:col-span-3">
      {BOTS.map((b, i) => (
        <BotCard key={b.id} bot={b} index={i} facts={status.state === "loading" ? null : facts} />
      ))}
    </div>
  );
}
