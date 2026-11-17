"use client";

import { FreshBadge } from "@/components/ui/badges";
import { ago } from "@/lib/format";
import type { Remote } from "@/lib/platform";
import { type Freshness, type JobName, type Jobs, freshness } from "@/lib/sec";

/** The scheduler interval for a job, when the backend reports one. */
export function everyMinutes(jobs: Remote<Jobs>, job: JobName): number | undefined {
  return jobs.state === "ok" ? jobs.data.jobs[job]?.every_minutes : undefined;
}

export function FreshFor({ f }: { f: Freshness }) {
  return <FreshBadge state={f.state} age={f.state === "unavailable" ? undefined : ago(f.ingestedAt, Date.now())} />;
}

/** Badge for one real record set: current, stale (job overdue) or unavailable (not ingested). */
export function Fresh({ ingestedAt, job, jobs }: { ingestedAt: string | null | undefined; job: JobName; jobs: Remote<Jobs> }) {
  return <FreshFor f={freshness(ingestedAt, everyMinutes(jobs, job), Date.now())} />;
}
