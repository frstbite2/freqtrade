# AI Trading Platform — Project Status

Last updated: 2026-11-12 · Current milestone: **1 complete, 2 next**

## 1. Repository audit

This repository is an unmodified fork of [freqtrade](https://github.com/freqtrade/freqtrade)
(crypto trading bot, GPLv3). Findings that shaped the architecture:

| Freqtrade has | Fit for this project |
|---|---|
| Exchange layer built on `ccxt` (crypto only) | No equities, no Alpaca/IBKR, no options, no SEC data. Not reusable for the core use case. |
| Backtesting + hyperopt | Tied to the crypto strategy interface. Metrics code (`freqtrade/data/metrics.py`: Sharpe, Sortino, drawdown) depends only on numpy/pandas/scipy and is a candidate for reuse in Milestone 8. |
| FreqAI (LightGBM, XGBoost, PyTorch) | Coupled to freqtrade's data kitchen. We will use the same libraries directly instead. |
| FastAPI server, SQLAlchemy persistence | Same libraries chosen here, but freqtrade's instances are wired to its own bot. |

**Decision:** build the platform as a standalone package in `backend/` that does **not import
freqtrade**. Freqtrade stays untouched and working (its own `docker-compose.yml`, tests and
`requirements.txt` are unchanged). Reasons: the two have different asset classes and data
models, and freqtrade's dependency set (TA-Lib C library, ccxt) is heavy and unrelated.
Deviations from the layout in the brief, and why:

- `backend/tests/` instead of top-level `tests/` — the top-level directory is freqtrade's suite
  with its own heavy `conftest.py`.
- `docker-compose.platform.yml`, `docker/Dockerfile.platform`, `requirements-platform.txt` —
  the unsuffixed names belong to freqtrade.
- `backend/services/<engine>/` directories are created when each engine is implemented, not as
  empty placeholders.

## 2. Architecture

```
            ┌────────────── Dashboard (Next.js, M9) ──────────────┐
            │                  REST / WebSocket                    │
            ▼                                                      │
      FastAPI (backend/api)  ── auth, validation, audit ───────────┘
            │
   ┌────────┴────────────────────────────────────────────────┐
   │ AI Decision Engine (M6): weighted evidence → score,       │
   │ explanation, decision (may be NO TRADE)                   │
   └───▲──────▲──────▲──────▲──────▲──────▲───────────────────┘
       │      │      │      │      │      │   evidence (typed, timestamped, sourced)
  Technical Pattern Insider Instit. Options News      ← independent engines (M3–M5)
       ▲      ▲      ▲      ▲      ▲      ▲
       └──────┴──── Market Data Engine (M2) + SEC EDGAR client (M4)
                    provider adapters with fallbacks + cache

  Decision ──► Risk Engine (M7, independent, hard limits, can veto) ──► Execution adapters
                                                                        (paper first)
  Backtesting (M8) replays the same engines over point-in-time data.
  Storage: PostgreSQL + TimescaleDB (SQLite for local dev/tests).
```

Principles enforced in code, not just documented:

- **Risk limits are config-validated and independent** of the decision engine (`config/risk.yaml`,
  `RiskConfig`). Out-of-range or inconsistent limits stop startup.
- **Paper only.** `trading_mode` accepts only `paper`; `live` is a validation error until the
  gated live configuration of Milestone 7 exists.
- **Secrets only from environment variables.** YAML rejects unknown keys; logs redact secret
  values; the API reports only whether a provider is configured.
- **Unavailable ≠ zero.** `/api/v1/status` reports which providers are configured so engines can
  report "no data source" distinctly from "no activity".
- **Point-in-time data.** Every stored record will carry the time it became publicly available
  (e.g. SEC acceptance timestamp), which is what backtests key on.

## 3. Required APIs

| Purpose | Provider | Key needed | Notes |
|---|---|---|---|
| Insider / institutional filings | SEC EDGAR (`data.sec.gov`) | None — `SEC_USER_AGENT` with contact email is mandatory | Free. Fair-access limit 10 requests/second. |
| Equity prices + paper broker | Alpaca | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Free tier gives IEX-only real-time data; full SIP feed is paid. Paper trading is free. |
| Prices / options (alt.) | Polygon.io | `POLYGON_API_KEY` | Free tier is end-of-day and rate-limited; options and real-time are paid. |
| News, analyst actions | Finnhub | `FINNHUB_API_KEY` | Free tier is rate-limited; some endpoints are premium. |
| Fallback prices / fundamentals | Alpha Vantage, FMP | `ALPHA_VANTAGE_API_KEY`, `FMP_API_KEY` | Low free daily quotas. |
| Options chains | Tradier | `TRADIER_API_TOKEN` | Requires a brokerage or sandbox account. |
| Crypto execution (optional) | Coinbase Advanced Trade | `COINBASE_API_KEY`, `COINBASE_API_SECRET` | |
| Broker (optional) | Interactive Brokers | Local TWS/Gateway | Needs a running gateway; later milestone. |

Provider terms, quotas and prices change — re-check each one when its milestone starts.
**None of these keys are configured yet.** Minimum to proceed: `SEC_USER_AGENT` (M4) and Alpaca
paper keys (M2, M7).

## 4. Roadmap

- [x] **M1 Foundation** — structure, config, logging, database, API, tests, Docker
- [ ] **M2 Market data** — provider adapter interface, Alpaca adapter, normalization, cache, integrity checks
- [ ] **M3 Technical analysis** — indicators, candlestick/chart patterns, market structure
- [ ] **M4 Insider intelligence** — EDGAR client, Forms 3/4/5 parsing, transaction codes, scoring
- [ ] **M5 Institutional + options** — 13F diffs, unusual options activity, scoring
- [ ] **M6 AI engine** — features, models, regime detection, opportunity score, explanations
- [ ] **M7 Risk + execution** — position sizing, hard limits, kill switch, paper broker adapters
- [ ] **M8 Backtesting** — fees, slippage, walk-forward, Monte Carlo, benchmarks
- [ ] **M9 Dashboard** — Next.js UI
- [ ] **M10 Integration** — end-to-end tests, failure drills, deployment docs

## 5. Milestone 1 — what exists and how it was verified

| Component | Location | Verified by |
|---|---|---|
| Settings (YAML + env overrides, strict validation) | `backend/core/config.py`, `config/*.yaml` | unit tests |
| Structured JSON logging with secret redaction | `backend/core/logging.py` | unit test; observed in container logs |
| Database engine, `audit_log` table | `backend/database/`, `backend/models/` | tests on SQLite; manual run on TimescaleDB (pg16) |
| API: `/health`, `/api/v1/status`, `/api/v1/config`, bearer auth (fails closed) | `backend/api/routes.py`, `backend/main.py` | API tests; curl against the running container |
| Startup/shutdown audit, graceful shutdown | `backend/main.py` | test; `audit_log` rows observed in Postgres after `docker compose stop` |
| Docker stack (API + TimescaleDB) | `docker-compose.platform.yml`, `docker/Dockerfile.platform` | built and run; see caveat |

Test suite: 17 tests, all passing (`cd backend && pytest`). Lint: `ruff check backend` clean.

Caveat on the Docker verification: the development sandbox intercepts TLS, so the image was
built from a temporary copy of the Dockerfile with two extra lines trusting the sandbox CA.
The committed Dockerfile is otherwise identical but has not itself been built on a normal network.

## 6. Known shortcuts and deferred items

- Schema is created with `create_all`; adopt Alembic migrations when the first table changes (M2).
- Redis is not in the stack yet; it is added with the cache in M2.
- No rate limiting on the API yet (single-user, bound to localhost); add before any non-local exposure.
- Uvicorn's own access log lines are plain text, not JSON (they contain no secrets).
- Single shared bearer token rather than user accounts; revisit with the dashboard (M9).
- No database backup job yet; add with deployment docs (M10).
