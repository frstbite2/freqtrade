import type { Metadata } from "next";
import { Landmark } from "lucide-react";
import { CapabilityPage } from "@/components/dashboard/capability-page";

export const metadata: Metadata = { title: "Insider Intelligence" };

export default function InsiderPage() {
  return (
    <CapabilityPage
      eyebrow="SEC filings"
      title="Insider Intelligence"
      subtitle="Officer, director and 10% owner trades from SEC Forms 3, 4 and 5: delayed public disclosures, never evidence of wrongdoing."
      icon={Landmark}
      colors={["#ffc65c", "#ff8a3d"]}
      note="The data views connect to the existing API in Stage 2."
      sources={["sec_edgar"]}
      capabilities={[
        { title: "Forms 3, 4 and 5", detail: "Ingested from SEC EDGAR on a schedule, with the time each filing became public.", ready: true },
        { title: "Clean buy and sell signals", detail: "Only open-market purchases and sales count; grants, exercises, tax withholding, gifts and plan trades never do.", ready: true },
        { title: "Insider score per company", detail: "A research ranking of recent insider buying and selling, with its components shown.", ready: true },
        { title: "Trading strategy", detail: "Turning insider activity into simulated trades is part of the AI engine (Milestone 6).", ready: false },
      ]}
    />
  );
}
