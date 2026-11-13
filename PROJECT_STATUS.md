# AI Trading Platform — Project Status

Last updated: 2026-11-12 · Current milestone: **1 complete, 2 in progress**

## Milestone 2 — Market data (in progress)

Implemented on branch `chatgpt/m2-alpaca-market-data`:

- Provider-neutral immutable OHLCV `Bar` model; UTC timestamp normalization and OHLC integrity validation.
- Read-only Alpaca stock-bars adapter using the market-data API (IEX feed by default); no order-placement functionality.
- Credential fail-closed behavior, bounded pagination, request validation, and provider errors that do not echo response bodies or credentials.
- Thread-safe bounded in-process TTL/LRU cache.
- Mock-transport tests for normalization, feed selection, pagination/cache, invalid OHLC, missing credentials, HTTP failures, input validation, and cache eviction.

**Verification status:** tests are authored but have not yet been executed in this environment. No Alpaca credentials are configured, so live-provider verification remains pending. The current cache is process-local; shared Redis caching and persistence are deferred until the platform stack is extended.

## 1. Repository audit

This repository is an unmodified fork of [freqtrade](https://github.com/freqtrade/freqtrade)
(crypto trading bot, GPLv3). The standalone platform lives in `backend/` and does not import or modify upstream Freqtrade code.

## 2. Architecture and safety rules

- Standalone package under `backend/`; original Freqtrade code and its requirements remain untouched.
- Paper-only trading configuration is enforced by Pydantic; live trading is rejected.
- Market-data adapter is read-only and has no broker order endpoints.
- Secrets are environment-only; never commit keys or paste them into source files.
- Missing provider data is unavailable, not zero activity.
- Historical records must retain source and point-in-time availability metadata as later engines are added.

## 3. Required APIs

| Purpose | Provider | Key needed | Notes |
|---|---|---|---|
| Equity prices + paper broker | Alpaca | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | IEX feed by default; feed access depends on subscription. |
| Insider / institutional filings | SEC EDGAR | None; descriptive `SEC_USER_AGENT` with contact email | Free; observe fair-access policy. |
| Alternative prices / options | Polygon.io | `POLYGON_API_KEY` | Re-check current tiers and limits when implemented. |
| News / analyst actions | Finnhub | `FINNHUB_API_KEY` | Re-check current tiers and limits when implemented. |

No provider credentials are stored in the repository. Use a local ignored `.env` file or deployment secrets.

## 4. Roadmap

- [x] **M1 Foundation** — structure, config, logging, database, API, tests, Docker
- [ ] **M2 Market data** — provider adapter, Alpaca integration, normalization, cache, integrity checks (implementation in review; tests not yet run)
- [ ] **M3 Technical analysis** — indicators, candlestick/chart patterns, market structure
- [ ] **M4 Insider intelligence** — EDGAR client, Forms 3/4/5 parsing, transaction codes, scoring
- [ ] **M5 Institutional + options** — 13F diffs, unusual options activity, scoring
- [ ] **M6 AI engine** — features, models, regime detection, opportunity score, explanations
- [ ] **M7 Risk + execution** — position sizing, hard limits, kill switch, paper broker adapters
- [ ] **M8 Backtesting** — fees, slippage, walk-forward, Monte Carlo, benchmarks
- [ ] **M9 Dashboard** — Next.js UI
- [ ] **M10 Integration** — end-to-end tests, failure drills, deployment docs

## 5. Verification gates

Before marking M2 complete:

1. Run `cd backend && pytest` and fix all failures.
2. Run the project's lint checks.
3. Add a live Alpaca read-only smoke test once paper-account market-data credentials are configured; never use live order endpoints.
4. Confirm cache behavior and provider failure handling under repeated requests.
