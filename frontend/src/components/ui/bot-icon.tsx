import { Anchor, Crosshair, Landmark, Rocket, Waves } from "lucide-react";
import type { BotIdentity } from "@/lib/bots";

const ICONS = { crosshair: Crosshair, rocket: Rocket, anchor: Anchor, waves: Waves, landmark: Landmark };

/** The bot's emblem: its icon on a glowing gradient tile in the bot's own colours. */
export function BotIcon({ bot, size = 44 }: { bot: BotIdentity; size?: number }) {
  const Icon = ICONS[bot.icon];
  return (
    <span
      aria-hidden
      className="relative inline-flex shrink-0 items-center justify-center rounded-2xl text-white"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(140deg, ${bot.g1}, ${bot.g2})`,
        boxShadow: `0 10px 30px -10px rgb(${bot.glow} / 0.8), 0 0 0 1px rgb(255 255 255 / 0.18) inset`,
      }}
    >
      <Icon style={{ width: size * 0.48, height: size * 0.48 }} strokeWidth={2.2} />
    </span>
  );
}
