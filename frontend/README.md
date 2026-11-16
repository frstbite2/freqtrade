# Frontend (Stage 1 prototype)

The web interface for the AI trading platform. Paper trading only: no real orders, deposits,
withdrawals, transfers or wallet connections exist anywhere in it.

```bash
cd frontend
npm install
cp .env.example .env.local     # PLATFORM_API_URL and PLATFORM_API_TOKEN (server-side only)
npm run dev                    # http://localhost:3000
npm run build && npm start     # production build
npm run typecheck && npm test
```

The FastAPI backend (`backend/`) runs separately; see the repository README.

## How it fits together

- Next.js (App Router), React, TypeScript, Tailwind CSS. Charts are hand-built SVG
  (`src/components/charts/`); icons come from `lucide-react`. No other runtime dependencies.
- The browser never talks to the backend. It calls `/api/platform/<path>`, a server route that
  checks the path against an allowlist (`src/lib/proxy-rules.ts`), adds the bearer token from the
  server's environment and forwards a GET. The token is never sent to the browser.
- **Demo / Live switch** (top bar). Demo shows the prototype's sample values
  (`src/lib/sample-data.ts`), each one badged DEMO under a page-wide notice. Live shows only what
  the backend returns; anything not built yet says so instead of showing a number.
- Real data in Stage 1: backend health, configured data providers, trading mode and the risk
  limits. Everything else is sample data until Stage 2 connects it.

## Layout

```
src/app/             pages (dashboard, bots, markets, portfolio, insider, institutional,
                     strategies, backtesting, risk, settings) and the API proxy route
src/components/
  shell/             sidebar, mobile tab bar and menu, top bar, notifications, demo banner
  dashboard/         hero balance, stat tiles, bot cards and details, portfolio, activity
                     feed, markets, trades, strategy comparison, insights, section pages
  charts/            area chart, sparkline, donut, comparison chart
  ui/                badges, deltas, token icons, animated numbers, empty and error states
src/lib/             brand, formatting, bot identities, sample data, data mode, API hook
```

## Rules for this code

- Never show an invented profit, win rate, signal or price as real. Sample values stay in
  `sample-data.ts` and are always shown with a DEMO badge; live mode never uses them.
- Win rates appear only after 30 completed trades (`MIN_TRADES_FOR_WIN_RATE`).
- Secrets stay server-side: never add `NEXT_PUBLIC_` variables for credentials.
- New backend paths for the browser are added to `ALLOWED_PREFIXES`, GET only.
