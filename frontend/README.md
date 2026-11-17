# Frontend (Stage 1 prototype)

The web interface for the AI trading platform. Paper trading only: no real orders, deposits,
withdrawals or transfers exist anywhere in it. A Phantom wallet can be connected **read-only** to
view its balances (see below); it is never used for trading.

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
- **Real data, shown in both modes and marked LIVE:** backend health, configured providers,
  trading mode, risk limits; SEC insider filings and scores (Insider Intelligence), 13F manager
  changes and holders by security, 13D/13G large holders (Institutional), the newest SEC
  disclosures and the ingestion pipeline's health (dashboard, Settings), and each bot's readiness.
  Every SEC record shows when it became public and when it was ingested; stale data stays visible
  with its age. Scores are research rankings, not probabilities.
- **Freshness of real data:** each SEC card shows LIVE (ingested on schedule), STALE (the job is
  overdue: interval plus 30 minutes, the backend's own rule; data shown with its age) or
  UNAVAILABLE (nothing ingested). A stale or unusable quote is never shown as a live price.
- **Market data:** with Alpaca keys on the backend, Live mode charts daily bars and the latest
  quote for the watchlist (`/api/v1/market`). Live verification pending: tested on mock responses
  only. A provider failure (backend 502 with a reason) is reported as such, not as "offline".
- **Guards:** `src/lib/demo-guard.test.ts` fails if a component that reads the API imports sample
  values, or if a sample-value view lacks a DEMO badge or the Demo/Live check.
- **Needs the Milestone 5 backend (PR #2/#3):** `/api/v1/ownership`, `/api/v1/jobs` and
  `/api/v1/health/ingestion`. Against an older backend those cards say the scheduler is missing.
- **Not real yet, shown only as DEMO or "unavailable":** prices and charts (Alpaca keys needed),
  AI signals and bot performance (Milestones 6 and 7), the paper portfolio.

## Phantom wallet (read-only)

The top-right **Connect Phantom** button and the dashboard's "Your Phantom wallet" card show a
real Solana wallet's balances, kept apart from the simulated portfolio.

**What connecting grants.** Phantom's documented injected provider (`window.phantom.solana`) is
used for `connect()`, `disconnect()` and the `connect` / `disconnect` / `accountChanged` events,
nothing else (`src/lib/wallet/phantom.ts`). Approving the connection shares the wallet's **public
address** with this site. That is all this app uses it for: the frontend server then reads public
balances for that address from a Solana RPC (`getBalance`, `getTokenAccountsByOwner`, both
read-only) and USD prices from Jupiter's price API.

In Phantom's model a connected site *could* later ask for a signature, and Phantom would show
each request for approval. This app never does: there is no code that calls `signMessage`,
`signTransaction`, `signAllTransactions`, `signAndSendTransaction`, `signIn` or `request`, and
`src/lib/wallet/read-only.test.ts` fails if any appears. It never asks for a recovery phrase,
private key, deposit, token approval or spending limit, and the bots never see the wallet. A
returning visitor is reconnected only with `connect({ onlyIfTrusted: true })`, which never opens a
prompt. Revoke access with Disconnect, and remove the site from Phantom's connected apps.

**Shown:** SOL plus the supported tokens in `src/lib/wallet/tokens.ts`, identified by mint
address (a token's own metadata can claim any name). Other tokens and NFTs are counted, not
named. A missing price shows "price unavailable", never $0.

**Mobile:** phone browsers have no extensions, so without Phantom the button becomes "Open in
Phantom", Phantom's universal link that opens this page in its in-app browser, where the same
connect flow works.

**Settings** (server-side, `.env.local`): `SOLANA_RPC_URL` has no default on purpose. Until it is
set, the wallet shows "balances unavailable", so real balances appear only after live access has
been verified and the setting made deliberately. A provider URL with a key stays on the server.
`WALLET_PRICE_URL` defaults to Jupiter's price API.

**Developing without a wallet or the network:**

```bash
npm run mock:solana                      # fake RPC + prices on 127.0.0.1:8899, answers marked "mock"
SOLANA_RPC_URL=http://127.0.0.1:8899 WALLET_PRICE_URL=http://127.0.0.1:8899/price \
NEXT_PUBLIC_MOCK_PHANTOM=1 npm run dev   # a fake Phantom; the UI shows a MOCK badge
```

**Live verification pending:** the balance route was written to the documented RPC and price
formats and tested only against the mock server and a fake provider; the development sandbox
cannot reach the Solana network, and no real wallet has been connected.

## Layout

```
src/app/             pages (dashboard, bots, markets, portfolio, insider, institutional,
                     strategies, backtesting, risk, settings) and the API proxy route
src/components/
  sec/               SEC filing views: insider, institutional, disclosures feed, pipeline health
  shell/             sidebar, mobile tab bar and menu, top bar, notifications, demo banner
  dashboard/         hero balance, stat tiles, bot cards and details, portfolio, activity
                     feed, markets, trades, strategy comparison, insights, section pages
  charts/            area chart, sparkline, donut, comparison chart
  ui/                badges, deltas, token icons, animated numbers, empty and error states
  wallet/            connect button and panel, dashboard wallet card, permissions section
src/lib/             brand, formatting, bot identities, sample data, data mode, API hook
src/lib/wallet/      Phantom provider, wallet state, balance parsing, token list, dev mocks
scripts/             mock-solana.mjs (development only)
```

## Rules for this code

- Never show an invented profit, win rate, signal or price as real. Sample values stay in
  `sample-data.ts` and are always shown with a DEMO badge; live mode never uses them.
- Win rates appear only after 30 completed trades (`MIN_TRADES_FOR_WIN_RATE`).
- Secrets stay server-side: never add `NEXT_PUBLIC_` variables for credentials.
- New backend paths for the browser are added to `ALLOWED_PREFIXES`, GET only.
- The wallet stays read-only: never call a wallet signing or `request` method, and never connect
  the wallet to bots, orders or the paper portfolio.
