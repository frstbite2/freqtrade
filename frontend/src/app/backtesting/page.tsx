import type { Metadata } from "next";
import { FlaskConical } from "lucide-react";
import { MilestonePage } from "@/components/dashboard/milestone-page";

export const metadata: Metadata = { title: "Backtesting" };

export default function BacktestingPage() {
  return (
    <MilestonePage
      eyebrow="Research"
      title="Backtesting"
      subtitle="Testing strategies on history without peeking: every input limited to what was public at the simulated moment."
      icon={FlaskConical}
      milestone="Milestone 8 (backtesting)"
      colors={["#36e3a1", "#38c8ff"]}
      dependsOn={["Strategies (M6)", "Risk engine and paper broker (M7)", "Point-in-time data (in place)"]}
      features={[
        { title: "Fees and slippage", detail: "Realistic costs on every simulated fill." },
        { title: "Walk-forward tests", detail: "Fit on one period, judge on the next, repeatedly." },
        { title: "Monte Carlo", detail: "How results vary when trade order and luck change." },
        { title: "Benchmarks", detail: "Every strategy compared with simply holding the market." },
      ]}
    />
  );
}
