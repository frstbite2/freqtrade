import { CircleSlash, PlugZap, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

/** A value that does not exist yet. Says why, instead of showing a made-up number. */
export function Unavailable({ reason, compact = false }: { reason: string; compact?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-ink-3 ${compact ? "text-xs" : "text-sm"}`}
      title={reason}
    >
      <CircleSlash className="size-3.5 shrink-0" aria-hidden />
      {reason}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl border border-line-strong bg-white/5 text-ink-2">
        {icon ?? <CircleSlash className="size-5" aria-hidden />}
      </div>
      <p className="font-display text-base font-semibold text-ink">{title}</p>
      {children && <div className="max-w-md text-sm leading-relaxed text-ink-3">{children}</div>}
      {action}
    </div>
  );
}

export function OfflineState({ what }: { what: string }) {
  return (
    <EmptyState icon={<PlugZap className="size-5" aria-hidden />} title="Backend not connected">
      {what} comes from the platform API, which is not reachable from this server. Start the
      backend and set <code className="text-ink-2">PLATFORM_API_URL</code> and{" "}
      <code className="text-ink-2">PLATFORM_API_TOKEN</code> for the frontend server.
    </EmptyState>
  );
}

export function ErrorState({ title, detail }: { title: string; detail: string }) {
  return (
    <EmptyState icon={<TriangleAlert className="size-5 text-rose" aria-hidden />} title={title}>
      {detail}
    </EmptyState>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton h-12" />
      ))}
    </div>
  );
}
