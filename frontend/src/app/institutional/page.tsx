import type { Metadata } from "next";
import { Building2 } from "lucide-react";
import { CapabilityPage } from "@/components/dashboard/capability-page";

export const metadata: Metadata = { title: "Institutional Tracking" };

export default function InstitutionalPage() {
  return (
    <CapabilityPage
      eyebrow="SEC filings"
      title="Institutional tracking"
      subtitle="Quarterly 13F holdings and 13D/13G large-holder stakes. Always as of a quarter end or event date, never current holdings."
      icon={Building2}
      colors={["#38c8ff", "#6e7bff"]}
      note="The data views connect to the existing API in Stage 2."
      sources={["sec_edgar"]}
      capabilities={[
        { title: "13F holdings", detail: "Positions of tracked managers per quarter, with quarter-over-quarter changes and split handling.", ready: true },
        { title: "13D and 13G stakes", detail: "Holders above 5%, kept apart: 13D may seek influence, 13G states it is passive.", ready: true },
        { title: "Holder history", detail: "Each holder's filings over time, with share and percentage changes reported separately.", ready: true },
        { title: "Signals from ownership changes", detail: "Ranking notable accumulation and distribution is part of the AI engine (Milestone 6).", ready: false },
      ]}
    />
  );
}
