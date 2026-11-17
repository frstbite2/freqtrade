import type { Metadata } from "next";
import { HeroBalance } from "@/components/dashboard/hero-balance";
import { PortfolioPanel } from "@/components/dashboard/portfolio-panel";
import { RecentTrades } from "@/components/dashboard/recent-trades";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Portfolio" };

export default function PortfolioPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Paper portfolio" title="Portfolio" subtitle="Simulated balances only. No deposits, withdrawals or transfers exist, by design. A connected Phantom wallet appears on the dashboard, read-only, never here." />
      <HeroBalance />
      <PortfolioPanel />
      <RecentTrades />
    </div>
  );
}
