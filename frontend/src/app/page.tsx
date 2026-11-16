import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { AiInsights } from "@/components/dashboard/ai-insights";
import { BotGrid } from "@/components/dashboard/bot-grid";
import { HeroBalance } from "@/components/dashboard/hero-balance";
import { MarketOverview, Watchlist } from "@/components/dashboard/markets";
import { PortfolioPanel } from "@/components/dashboard/portfolio-panel";
import { RecentTrades } from "@/components/dashboard/recent-trades";
import { StatGrid } from "@/components/dashboard/stat-grid";
import { StrategyComparison } from "@/components/dashboard/strategy-comparison";
import { SectionHeader } from "@/components/ui/section";
import { WalletCard } from "@/components/wallet/wallet-card";

export default function DashboardPage() {
  return (
    <div className="space-y-6 sm:space-y-8">
      <HeroBalance />
      <StatGrid />
      <WalletCard />

      <section aria-labelledby="bots-heading">
        <SectionHeader title="AI bots" subtitle="Five specialists, each with its own strategy and watchlist" />
        <h2 id="bots-heading" className="sr-only">AI bots</h2>
        <BotGrid />
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.7fr_1fr]">
        <PortfolioPanel />
        <ActivityFeed limit={5} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <MarketOverview />
        <Watchlist limit={6} />
        <AiInsights />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <StrategyComparison />
        <RecentTrades />
      </div>
    </div>
  );
}
