import { LogoMark } from "@/components/shell/logo";

/** Shown while a page loads: the mark inside counter-rotating scanner rings. */
export default function Loading() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6" role="status" aria-label="Loading">
      <div className="relative flex size-40 items-center justify-center">
        <span className="absolute inset-0 animate-spin-slow rounded-full border border-dashed border-violet/40" />
        <span className="absolute inset-4 animate-[spin_6s_linear_infinite_reverse] rounded-full border-2 border-transparent border-t-ember border-r-ember/40 shadow-[0_0_30px_-6px_#ff8a3d]" />
        <span className="absolute inset-9 animate-[spin_2.4s_linear_infinite] rounded-full border-2 border-transparent border-b-sky border-l-sky/40" />
        <span className="animate-float">
          <LogoMark size={46} />
        </span>
      </div>
      <p className="text-gradient-live font-display text-sm font-semibold uppercase tracking-[0.3em]">Syncing intelligence</p>
    </div>
  );
}
