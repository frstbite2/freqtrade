import type { Metadata } from "next";
import { BotGrid } from "@/components/dashboard/bot-grid";
import { StrategyComparison } from "@/components/dashboard/strategy-comparison";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "AI Bots" };

export default function BotsPage() {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Command centre" title="AI bots" subtitle="Each bot is a specialist. Expand a card for what it looks for, or open its full profile." />
      <BotGrid />
      <StrategyComparison />
    </div>
  );
}
