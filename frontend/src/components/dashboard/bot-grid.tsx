import { BOTS } from "@/lib/bots";
import { BotCard } from "./bot-card";

export function BotGrid() {
  return (
    <div className="grid items-start gap-4 sm:grid-cols-2 sm:[&>*:last-child]:col-span-2 xl:grid-cols-6 xl:[&>*]:col-span-2 xl:[&>*:nth-last-child(-n+2)]:col-span-3">
      {BOTS.map((b, i) => (
        <BotCard key={b.id} bot={b} index={i} />
      ))}
    </div>
  );
}
