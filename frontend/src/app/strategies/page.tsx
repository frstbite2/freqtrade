import type { Metadata } from "next";
import { Workflow } from "lucide-react";
import { MilestonePage } from "@/components/dashboard/milestone-page";

export const metadata: Metadata = { title: "Strategies" };

export default function StrategiesPage() {
  return (
    <MilestonePage
      eyebrow="AI engine"
      title="Strategies"
      subtitle="How each bot decides: its rules, the signals it weighs and the reasoning behind every decision."
      icon={Workflow}
      milestone="Milestone 6 (AI engine)"
      colors={["#a46bff", "#ff5fa2"]}
      dependsOn={["Market data verified (M2)", "Technical analysis on real prices (M3)", "SEC intelligence (M4, M5)"]}
      features={[
        { title: "Strategy rules", detail: "Each bot's entry and exit logic, written so a person can follow it." },
        { title: "Explainable signals", detail: "Every decision lists its evidence and the weight each input carried." },
        { title: "Regime awareness", detail: "Strategies adapt to trending, ranging and volatile markets." },
        { title: "Transparent scoring", detail: "Opportunity scores are research rankings, never probabilities." },
      ]}
    />
  );
}
