import type { Metadata } from "next";
import { RiskView } from "./risk-view";

export const metadata: Metadata = { title: "Risk Management" };

export default function RiskPage() {
  return <RiskView />;
}
