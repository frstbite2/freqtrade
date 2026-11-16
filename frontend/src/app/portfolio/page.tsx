import type { Metadata } from "next";
import { HeroBalance } from "@/components/dashboard/hero-balance";
import { PortfolioPanel } from "@/components/dashboard/portfolio-panel";
import { RecentTrades } from "@/components/dashboard/recent-trades";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Portfolio" };

export default function PortfolioPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Paper portfolio" title="Portfolio" subtitle="Simulated balances only. No deposits, withdrawals, transfers or wallet connections exist, by design." />
      <HeroBalance />
      <PortfolioPanel />
      <RecentTrades />
    </div>
  );
}
