import type { Metadata } from "next";
import { InsiderView } from "@/components/sec/insider-view";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Insider Intelligence" };

export default function InsiderPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="SEC filings · live"
        title="Insider Intelligence"
        subtitle="Officer, director and 10% owner trades from SEC Forms 3, 4 and 5: delayed public disclosures, never evidence of wrongdoing. Only open-market purchases and sales count as signals."
      />
      <InsiderView />
    </div>
  );
}
