import Link from "next/link";
import { EmptyState } from "@/components/ui/states";

export default function NotFound() {
  return (
    <div className="card mx-auto mt-10 max-w-lg">
      <EmptyState
        title="This page drifted out of orbit"
        action={
          <Link href="/" className="rounded-xl bg-gradient-to-r from-violet to-ember px-4 py-2 text-sm font-semibold text-white">
            Back to the dashboard
          </Link>
        }
      >
        The address does not match any part of the platform.
      </EmptyState>
    </div>
  );
}
