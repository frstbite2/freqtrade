"use client";

import { AlertTriangle, CheckCircle2, Clock3, PauseCircle, XCircle } from "lucide-react";
import { LiveBadge } from "@/components/ui/badges";
import { SectionHeader } from "@/components/ui/section";
import { OfflineState, SkeletonRows } from "@/components/ui/states";
import { ago, utcDateTime } from "@/lib/format";
import { usePlatform } from "@/lib/platform";
import { type IngestionHealth, readableProblem } from "@/lib/sec";

const JOB_LABEL: Record<string, string> = {
  insider: "Insider filings (Forms 3, 4, 5)",
  beneficial: "Large holders (13D, 13G)",
  institutional: "Institutional holdings (13F)",
};

const STATUS = {
  healthy: { label: "Healthy", icon: CheckCircle2, cls: "text-mint border-mint/30 bg-mint/10" },
  degraded: { label: "Degraded", icon: AlertTriangle, cls: "text-gold border-gold/30 bg-gold/10" },
  unhealthy: { label: "Needs attention", icon: XCircle, cls: "text-rose border-rose/30 bg-rose/10" },
  disabled: { label: "Disabled", icon: PauseCircle, cls: "text-ink-3 border-line-strong bg-white/5" },
} as const;

/** Real: the SEC ingestion scheduler's health, from GET /api/v1/health/ingestion (503 still carries the report). */
export function PipelineHealth() {
  const result = usePlatform<IngestionHealth>("api/v1/health/ingestion", 60_000);
  const report =
    result.state === "ok"
      ? result.data
      : result.state === "unavailable" && result.status === 503 && typeof result.body === "object" && result.body && "status" in result.body
        ? (result.body as IngestionHealth)
        : null;
  const now = Date.now();

  return (
    <section className="card flex flex-col p-5 sm:p-6">
      <SectionHeader title="Data pipeline" subtitle="SEC filing ingestion, checked every minute" right={<LiveBadge />} />
      {result.state === "loading" ? (
        <SkeletonRows rows={3} />
      ) : result.state === "offline" ? (
        <OfflineState what="Ingestion health" />
      ) : !report ? (
        <p className="text-sm text-ink-3">
          {result.state === "unavailable" && result.status === 404
            ? "This backend has no ingestion scheduler yet (it arrives with the Milestone 5 branch, PR #2)."
            : `The platform API answered: ${result.state === "unavailable" ? result.message : "unexpected response"}.`}
        </p>
      ) : (
        <Report report={report} now={now} />
      )}
    </section>
  );
}

function Report({ report, now }: { report: IngestionHealth; now: number }) {
  const s = STATUS[report.status] ?? STATUS.degraded;
  const Icon = s.icon;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${s.cls}`}>
          <Icon className="size-3.5" aria-hidden /> {s.label}
        </span>
        {report.scheduler && <span className="text-xs text-ink-3">Scheduler: {report.scheduler}</span>}
        {report.ingesting_now && <span className="text-xs text-sky">Ingesting now</span>}
      </div>
      <ul className="space-y-2">
        {Object.entries(report.jobs ?? {}).map(([name, j]) => (
          <li key={name} className="rounded-xl border border-line bg-black/15 px-3 py-2.5 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate text-ink-2">{JOB_LABEL[name] ?? name}</span>
              {j.overdue ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-rose"><Clock3 className="size-3.5" aria-hidden /> Overdue</span>
              ) : j.last_failure && j.last_run?.status !== "succeeded" ? (
                <span className="shrink-0 text-xs font-medium text-rose">Last run failed</span>
              ) : (
                <span className="shrink-0 text-xs font-medium text-mint">On schedule</span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-ink-3">
              {j.last_success ? (
                <span title={utcDateTime(j.last_success.started_at)}>Last success {ago(j.last_success.started_at, now)}</span>
              ) : (
                "Never succeeded: no data yet"
              )}
              {" · "}
              {j.targets} {j.targets === 1 ? "target" : "targets"} · every {j.every_minutes >= 60 ? `${j.every_minutes / 60} h` : `${j.every_minutes} min`}
            </p>
          </li>
        ))}
      </ul>
      {report.problems.length > 0 && (
        <ul className="space-y-1 text-xs text-rose/90">
          {report.problems.map((p) => (
            <li key={p} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />{readableProblem(p)}</li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-ink-3">Checked {utcDateTime(report.checked_at)}. Stale data stays visible, labelled with when it was ingested.</p>
    </div>
  );
}
