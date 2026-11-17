import type { Metadata } from "next";
import { InstitutionalView } from "@/components/sec/institutional-view";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Institutional Tracking" };

export default function InstitutionalPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="SEC filings · live"
        title="Institutional tracking"
        subtitle="Quarterly 13F holdings and 13D/13G large-holder stakes. Always as of a quarter end or event date, never current holdings."
      />
      <InstitutionalView />
    </div>
  );
}
