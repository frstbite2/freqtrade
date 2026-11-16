# AI Trading Platform — Project Status

Last updated: 2026-11-16 · Complete and verified on real data: **1, 4**, and the SEC half of **5** (13F, 13D, 13G), plus scheduled ingestion and database migrations · Built, live verification pending: **2** · Built, unverified on real data: **3** · Not started: options flow (needs a paid provider), 6 to 10

## Status at a glance

Where the work lives: everything through 13F is on `claude/ai-trading-platform-g23fcw`. Schedules
13D/13G, scheduled ingestion and platform CI are in draft PR #2; database migrations are in draft
PR #3, stacked on #2. Neither PR is merged; both wait for the owner's review. Paper trading only:
`trading_mode: live` is a validation error.

**Complete and verified**
- Foundation: settings, logging with secret redaction, API with authentication and rate limit,
  audit log, Docker stack (M1).
- SEC insider filings, Forms 3/4/5: parsing, classification, scoring, history; checked against
  SEC's own data sets (M4).
- SEC Form 13F holdings and Schedules 13D/13G: parsing, ingestion, history, API; checked on real
  filings (M5, SEC half).
- Scheduled ingestion of all SEC sources, reviewed for continuous running (section 5f).
- Database migrations with Alembic, audited against every past schema and real databases (5g).
- CI on every pull request: platform tests (also on PostgreSQL), lint, type check, Docker image
  build with tests inside it, and upstream freqtrade's own CI.

**Built, waiting for credentials or live verification**
- Market data (M2): the Alpaca adapter has never called the real API. Needs free Alpaca paper
  keys (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) and network access to `data.alpaca.markets`.
- Technical analysis (M3): tested only on constructed price series; it runs on real prices once
  M2 is verified.
- Full Docker stack on a normal network: the image is built and tested in CI, but database, API
  and worker together have only run in the development sandbox, which cannot reach sec.gov.

**Not started**
- Options flow (M5): needs a paid data provider; the owner decides which, if any.
- Milestones 6 to 10: on hold until the owner has reviewed PRs #2 and #3.

No API keys are configured. SEC EDGAR needs only `SEC_USER_AGENT` (a name and contact email).

Passing tests do not make the platform production-ready: section 7 lists what still has to change
before it runs unattended.

Milestone 4 (insider filings) was done before Milestone 2 (market data) at the owner's request,
because SEC EDGAR needs no API key and could be verified against real data immediately.

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
| Insider / institutional filings | SEC EDGAR (`www.sec.gov`, `data.sec.gov`) | None — `SEC_USER_AGENT` with contact email is mandatory | Free. Fair-access limit 10 requests/second. **In use since M4.** |
| Equity prices + paper broker | Alpaca | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Free tier gives IEX-only real-time data; full SIP feed is paid. Paper trading is free. |
| Prices / options (alt.) | Polygon.io | `POLYGON_API_KEY` | Free tier is end-of-day and rate-limited; options and real-time are paid. |
| News, analyst actions | Finnhub | `FINNHUB_API_KEY` | Free tier is rate-limited; some endpoints are premium. |
| Fallback prices / fundamentals | Alpha Vantage, FMP | `ALPHA_VANTAGE_API_KEY`, `FMP_API_KEY` | Low free daily quotas. |
| Options chains | Tradier | `TRADIER_API_TOKEN` | Requires a brokerage or sandbox account. |
| Crypto execution (optional) | Coinbase Advanced Trade | `COINBASE_API_KEY`, `COINBASE_API_SECRET` | |
| Broker (optional) | Interactive Brokers | Local TWS/Gateway | Needs a running gateway; later milestone. |

Provider terms, quotas and prices change — re-check each one when its milestone starts.
**No API keys are configured yet.** SEC EDGAR is in use and needs none. Alpaca paper keys are
the one thing blocking verification of M2, and are needed again for M7.

## 4. Roadmap

- [x] **M1 Foundation** — structure, config, logging, database, API, tests, Docker
- [~] **M2 Market data** — built and unit-tested; **verification against live Alpaca is pending API keys**
- [~] **M3 Technical analysis** — built and tested on constructed price series; **not yet run on real market data** (waits on M2)
- [x] **M4 Insider intelligence** — EDGAR client, Forms 3/4/5 parsing, classification, scoring, history
- [~] **M5 Institutional + options** — 13F holdings and Schedules 13D/13G done and verified on real filings; options flow not started (needs a paid data provider)
- [ ] **M6 AI engine** — features, models, regime detection, opportunity score, explanations
- [ ] **M7 Risk + execution** — position sizing, hard limits, kill switch, paper broker adapters
- [ ] **M8 Backtesting** — fees, slippage, walk-forward, Monte Carlo, benchmarks
- [ ] **M9 Dashboard** — Next.js UI
- [ ] **M10 Integration** — end-to-end tests, failure drills, deployment docs

## 5. Milestone 1 — foundation (complete)

| Component | Location | Verified by |
|---|---|---|
| Settings (YAML + env overrides, strict validation) | `backend/core/config.py`, `config/*.yaml` | unit tests |
| Structured JSON logging with secret redaction | `backend/core/logging.py` | unit test; observed in container logs |
| Database engine, `audit_log` table | `backend/database/`, `backend/models/` | tests on SQLite; manual run on TimescaleDB (pg16) |
| API: `/health`, `/api/v1/status`, `/api/v1/config`, bearer auth (fails closed) | `backend/api/routes.py`, `backend/main.py` | API tests; curl against the running container |
| Rate limit per client address, applied before authentication (`api_rate_limit_per_minute`, default 120) | `backend/api/routes.py` | API test with a controlled clock |
| Startup/shutdown audit, graceful shutdown | `backend/main.py` | test; `audit_log` rows observed in Postgres |
| Docker stack (API + TimescaleDB) | `docker-compose.platform.yml`, `docker/Dockerfile.platform` | built and run; see caveat |

Docker verification, repeated on 2026-11-14 with all code through Milestone 5: the image was built
from the committed `docker/Dockerfile.platform`, unmodified. The stack (database, API, worker)
starts on TimescaleDB and creates all 13 tables; every endpoint answers; and inside the image
(Python 3.12) the full test suite passes and the type check is clean.

How it was built here, and what that leaves unproven: the development sandbox intercepts TLS, so
`pip` inside a build cannot verify PyPI. Rather than alter the Dockerfile, the base image tag
`python:3.12-slim` was pointed at a local copy of the official image with the sandbox's
certificate added, and the build used host networking to reach the sandbox proxy. On a normal
network neither is needed: on 2026-11-15 the `docker` job of `platform-ci.yml` built the committed
Dockerfile on a GitHub runner with no workarounds and ran the tests inside the image (374 passed).
The full compose stack (database, API, worker together) has still only been started in the sandbox. Containers in the sandbox have
no route to sec.gov, so the worker's runs there ended as recorded failures, which is the designed
behaviour; scheduled ingestion against live EDGAR was verified outside the container.

Checks that now gate every change: `pytest` (412 tests pass with PostgreSQL available for the
migration tests, 399 on SQLite alone; 12 opt-in or database-specific tests skip), `ruff check` and
`ruff format`, and
`mypy --config-file backend/mypy.ini backend` (0 errors; it reported 91 when first run, all fixed).

CI: `.github/workflows/platform-ci.yml` runs those checks on every pull request that touches the
platform, plus a plain `docker build` of the committed Dockerfile and the test suite inside the
image. First run 2026-11-15 on PR #2: both jobs passed. Upstream's pre-commit hooks also run on
pull requests; they skip `backend/tests/fixtures/` (real filings must stay byte-for-byte) and leave
type-checking of `backend/` to the platform's own mypy configuration.

## 5a. Milestone 4 — insider intelligence (complete, with stated limits)

### What exists

| Component | Location |
|---|---|
| EDGAR client: declared User-Agent, 8 requests/s throttle, retry with backoff, permanent cache for filings, TTL cache for indexes, URL/path validation | `backend/services/edgar.py` |
| Parser for Forms 3, 4, 5 and amendments, with field-level validation | `backend/services/insider_intelligence/parser.py` |
| Classification and signal eligibility | `backend/services/insider_intelligence/classify.py` |
| Idempotent ingestion, per-filing atomic writes, failure reporting, re-classification on rule change, an `audit_log` entry per run | `backend/services/insider_intelligence/ingest.py` |
| Point-in-time reads, amendment and duplicate resolution, joint-filer grouping | `backend/services/insider_intelligence/history.py` |
| Insider activity score 0-100 with explanations | `backend/services/insider_intelligence/scoring.py` |
| Verification against SEC's own data sets | `backend/services/insider_intelligence/verify.py` |
| Tables `insider_issuer`, `insider_filing`, `insider_transaction` | `backend/models/insider.py` |
| `GET /api/v1/insider/{ticker}/score`, `GET /api/v1/insider/{ticker}/transactions` | `backend/api/insider.py` |

### How a transaction is categorised

Only `open_market_purchase` and `open_market_sale` can become a signal (`discretionary_buy`,
`discretionary_sell`), and only for non-derivative stock with a positive price and share count and
no data-quality issue. Everything else is stored, shown, and never counted:

| Category | Source |
|---|---|
| `planned_purchase` / `planned_sale` | Rule 10b5-1 stated in a footnote or remarks, the form's 10b5-1 checkbox, or "pursuant to trading instructions" |
| `acquisition_from_issuer` | code A: grants, awards, and shares bought from the company itself |
| `option_exercise`, `conversion` | codes M, X, O; C |
| `tax_withholding` | code F |
| `sale_to_cover_taxes` | code S whose footnote says the sale covered tax withholding |
| `sale_linked_to_exercise` | code S on a day when the shares sold do not exceed shares received by exercise in the same filing |
| `third_party_managed` | footnote says the trade was made without the insider's knowledge or direction |
| `non_open_market_purchase` / `non_open_market_sale` | footnote names an offering, private placement, tender, repurchase, ESPP or dividend reinvestment |
| `gift`, `inheritance`, `disposition_to_issuer`, `other` | codes G; W; D; J, K, L, I, U, E, H, Z |
| `derivative_purchase` / `derivative_sale` | code P/S on options, warrants and similar |
| `holding` | Form 3 holdings and holding lines on Forms 4/5 |

Rules that came from reading real filings, each covered by a test on the filing in question:

- Apple reports plan sales in a footnote while the form's 10b5-1 checkbox is unchecked, so the
  checkbox alone is not trusted.
- Nike attaches policy boilerplate ("...except pursuant to approved 10b5-1 trading plans") to
  genuine open-market purchases, so merely mentioning 10b5-1 does not make a trade a plan trade.
- When the checkbox is ticked but footnotes single out only some rows, the remaining rows keep
  their category and get the issue `plan_scope_ambiguous`, which excludes them from signals.
- Intel's CEO acquired 1,043,406 shares from Intel at a price under his offer letter (code A):
  paid for, but not an open-market purchase.
- A company's index also lists filings it made as a holder of another company (Intel on Mobileye);
  these are skipped.
- A fund and its chairman who file jointly, in varying order, count as one insider.

### Verification performed (2026-11-13)

| Check | Result |
|---|---|
| Parser vs SEC's "Insider Transactions Data Sets", random sample of 1,200 filings from 2009 Q3, 2016 Q1, 2024 Q3 and 2026 Q1 | 0 value mismatches, 0 parse failures. 1,134 identical row for row. In 66, every value is identical but SEC's data set carries one field (usually nature of ownership) in a different row |
| Those 66 filings re-read from the raw documents with a separate text-matching extractor | The raw document agrees with our parser row for row in 66 of 66 |
| Real ingestion: Intel, Apple, Nike, Occidental, Texas Pacific Land, GameStop, Carvana, JPMorgan, filings since 2023-01-01 | 3,080 filings and 14,742 rows stored, 0 failures, 38 other-issuer filings skipped. 986 rows are signals; none of them has a plan flag, an issue, a non-P/S code or a non-positive price |
| Same pipeline on PostgreSQL 16 / TimescaleDB | Exact decimals, UTC timestamps, identical scores |
| Acceptance timestamps | SEC index time confirmed as true UTC against filing headers in both standard and daylight time |
| Hand-computed checks | Nike April 2026 cluster: 4 insiders, $2,734,230.20; Intel August 2024: holdings increase 2.0% over 631,307 shares reported |
| Index paging for a heavy filer, live | JPMorgan's index spans 73 pages; reading back to 2023 took 29 requests and returned 488 ownership filings with no duplicates |
| Automated tests | 112 offline tests; parsing, classification, ingestion and scoring run on 26 real filings stored unmodified, and the verification tool on SEC's real data-set rows for three of them. 4 opt-in live tests, including a byte-for-byte comparison of a fixture with what EDGAR serves |

Reproduce: `python -m backend.services.insider_intelligence.verify <quarter>_form345.zip`
(needs `SEC_USER_AGENT`), and `EDGAR_LIVE_TESTS=1 pytest -m live`.

SEC's data set itself differs from the filings in three documented ways (two-decimal rounding,
optional fields shifted between rows, joint filers' roles merged); `verify.py` explains how each
is handled. The original filing is treated as the source of truth.

If an ingestion run cannot store a filing, the count is kept on the issuer, returned as
`missing_filings` by both endpoints, and the score's explanation says the history is incomplete.

### Partially complete

- **Score components.** Five of seven are computed. `announcement_timing` needs an earnings/news
  calendar and `value_vs_market_cap` needs market data; both are reported as unavailable and left
  out of the normalisation, never counted as zero.
- **Score weights and thresholds** are unvalidated priors. They need walk-forward testing (M8).
- **Categorisation accuracy** was checked by reading filings and footnotes from eight issuers and
  by invariants over 14,742 rows. It has not been measured against an independently labelled set,
  because none exists; wording not seen in those issuers can be missed.

### Limits that the filings themselves impose

- SEC code P/S means "open market or private". A private deal is recognised only when a footnote
  says so.
- A plan trade that the filer discloses nowhere (no checkbox, footnote or remark) cannot be told
  apart from a discretionary trade.
- An amendment that only adds a lot on the same day with the same code also hides the original
  lot. This undercounts; it never double counts.
- Two different insiders who make an identical trade and end with identical holdings are read as
  one trade reported twice. This undercounts.
- Prices are not yet checked against market prices (needs M2), so a typo in a filed price passes.

### Not done in this milestone

- Alerts on new insider activity. (Forms 13D/13G/13F and scheduled ingestion are done: see 5d to 5f.)
- Filings before mid-2003 have no structured document; they are counted in the ingest report
  (`without XML`) and not parsed.

### Blocked

Nothing in Milestone 4 is blocked. Running it needs `SEC_USER_AGENT` (a name and contact email,
required by SEC) and network access to `www.sec.gov` and `data.sec.gov`.

## 5b. Milestone 2 — market data (built; LIVE VERIFICATION PENDING)

**Status in one line:** the code is complete and its logic is tested, but it has never talked
to Alpaca, because no API keys were available. Treat every statement below about Alpaca's
behaviour as unconfirmed until the live tests have been run.

### What exists

| Component | Location |
|---|---|
| Provider-neutral types (`Bar`, `Quote`), provider interface, request validation | `backend/services/market_data/base.py` |
| Alpaca adapter: historical bars with paging, latest quote, exact decimal parsing, error mapping | `backend/services/market_data/alpaca.py` |
| Integrity checks: rejected bars with reasons, warnings | `backend/services/market_data/integrity.py` |
| Caching service: fetch once, check, store, serve from storage | `backend/services/market_data/service.py` |
| Tables `price_bar`, `price_coverage` | `backend/models/market.py` |
| `GET /api/v1/market/{symbol}/bars`, `GET /api/v1/market/{symbol}/quote` | `backend/api/market.py` |
| Shared retry and request-spacing helper (also used by the EDGAR client) | `backend/core/http.py` |

Timeframes: 1m, 5m, 15m, 1h, 4h, 1d, 1w. Adjustments: raw, split, dividend, all.

### Behaviour

- **Normalisation.** Every bar is UTC, keyed by the start of its period, with prices kept as exact
  decimals (parsed straight from the response text, never through binary floats).
- **Integrity.** A bar is rejected, reported with reasons and never stored if it is impossible:
  high below low, open or close outside the high-low range, non-positive price, negative volume,
  non-finite number, wrong symbol or timeframe, timestamp without timezone or outside the
  requested range, or two different bars for the same moment. Warnings (not rejections): a close
  moving more than 50% between bars, VWAP outside the range, bars off the timeframe grid,
  out-of-order or repeated bars, and weekdays without a daily bar.
- **Caching.** Bars whose period ended at least 20 minutes ago are stored. Newer bars can still
  change and are fetched fresh each time. Raw history never expires; adjusted history expires
  after 24 hours because every later split or dividend rewrites it. `price_coverage` records
  which ranges were fetched, so "nothing traded" is never confused with "never asked". Redis
  is not used: the database is the cache, and nothing here needs a second store.
- **Errors.** Rate-limit and server errors are retried with backoff; authentication and request
  errors are reported once with Alpaca's message; a failed fetch stores nothing. API keys are
  sent only as headers and never appear in URLs, logs or error messages.
- **No keys.** The API answers 503 "prices are unavailable". Ranges already stored are still
  served. Nothing is simulated.
- **Quotes** carry their age and a `usable` flag (false when stale, crossed, or one-sided).
- **Feed.** `alpaca_feed` in `config/settings.yaml`, default `iex`. IEX is a single exchange, so
  its volumes are a small share of total market volume; bars are stored per feed and never mixed.

### Verification performed

| Check | Result |
|---|---|
| Unit tests of the adapter, integrity checks, cache and API | 103 tests pass. **All prices in them are made up and all Alpaca responses are synthetic**, shaped after the field names in Alpaca's official SDK |
| Cache on PostgreSQL 16 / TimescaleDB with a fake provider | Exact 8-decimal round trip, gap-only fetching, adjusted-history refresh |
| App without keys | 503 "unavailable" for bars and quote; status shows `alpaca: false` |
| Against live Alpaca | **NOT DONE** |

Source for the Alpaca interface: the official `alpaca-py` SDK 0.45.0, read from PyPI (Alpaca's
documentation site was not reachable from the development environment). Taken from it: base URL,
`/v2/stocks/bars` and `/v2/stocks/quotes/latest`, the `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY`
headers, parameter names, the 10,000-per-page limit, `next_page_token` paging, field names
(`t o h l c v n vw`; `bp bs ap as`), timeframe spellings and feed names.

### Unverified until the live tests run

1. That real responses have the shape the SDK implies, including what is sent when there is no
   data (handled: null, absent, or an empty map).
2. Whether Alpaca's `end` bound is inclusive. The adapter enforces `start <= ts < end` itself.
3. The timestamp of daily bars (assumed: midnight US Eastern, expressed in UTC). This affects the
   weekday-gap warning and when a daily bar counts as final.
4. Status codes and messages for bad keys, unknown symbols and plan restrictions.
5. Rate limits. The adapter spaces requests to about 170 per minute on the assumption of a
   200-per-minute free-plan limit; that figure is from memory, not from a source read here.
6. How far back the free IEX feed goes, and how 4-hour and weekly bars are aligned.

### To verify (needs free Alpaca paper keys)

```bash
cd backend && ALPACA_LIVE_TESTS=1 ALPACA_API_KEY=... ALPACA_SECRET_KEY=... ../.venv/bin/pytest -m live -k alpaca
```

Six tests in `backend/tests/test_alpaca_live.py` check the January 2024 trading calendar (21
sessions), internal consistency, paging against a single request, intraday alignment, the 2020
Apple split under split adjustment, quote parsing, and error behaviour. The environment also
needs network access to `data.alpaca.markets`.

### Not done in this milestone

- A second (fallback) provider. The interface allows one; no other provider's keys exist either.
- Streaming prices (websocket). Only request/response is built.
- An exchange calendar, so holidays show up in the weekday-gap warning.
- Checking insider-filing prices against market prices (waits for verified price data).

### Blocked

- Live verification: needs `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.

## 5c. Milestone 3 — technical analysis (built; UNVERIFIED ON REAL DATA)

**Status in one line:** every indicator and detector is implemented and tested, but only on price
series constructed for the tests. It was started before Milestone 2 was verified, at the owner's
request. Nothing about how well these rules work on real markets is known yet.

### What exists

| Component | Location |
|---|---|
| Indicators: RSI, MACD, EMA 9/21/50/100/200, SMA 20/50/100/200, session VWAP (intraday), Bollinger Bands, ATR, ADX/DI, OBV, MFI, relative volume, average volume, historical volatility; Fibonacci retracements; volume profile with point of control and value area | `backend/services/technical_analysis/indicators.py` |
| Candlesticks: engulfing, morning/evening star, hammer, shooting star, doji, three white soldiers, three black crows (TA-Lib recognisers); inside bar, pin bar | `backend/services/technical_analysis/candles.py` |
| Chart patterns: double/triple tops and bottoms, head and shoulders (and inverse), bull/bear flags, ascending/descending/symmetrical triangles, rising/falling wedges, rounded bottom, cup and handle, breakouts and breakdowns | `backend/services/technical_analysis/patterns.py` |
| Market structure: swing highs/lows labelled HH/HL/LH/LL, trend, break of structure, change of character, liquidity sweeps, order blocks, fair value gaps (and which are still open), volume imbalances, supply/demand zones, support/resistance, consolidation and expansion, trend exhaustion (RSI divergence) | `backend/services/technical_analysis/structure.py` |
| Multi-timeframe engine: each detection is checked against the next higher timeframe's bias | `backend/services/technical_analysis/engine.py` |
| `GET /api/v1/technical/{symbol}?timeframes=1d,1w` | `backend/api/technical.py` |

Every detection carries: name, kind, direction, symbol, timeframe, detection time, confidence,
explanation, and where it applies an entry zone, stop-loss and targets (the pattern's measured
move, or 1x and 2x the risk), plus the higher-timeframe check. `historical_performance` always
says "unavailable": comparable-setup statistics come from backtesting (Milestone 8) and are not
invented here.

### Design rules

- **No look-ahead.** A swing is only known three bars after its extreme; a pattern is dated at the
  bar whose close completes it; the higher-timeframe check uses only bars that had closed. Tested
  by running the engine on truncated histories and requiring identical earlier detections.
- **Confidence is a rule-match score, not a probability.** Candlesticks start at 0.4 and gain for a
  preceding move to reverse and for unusual volume; chart patterns start at 0.5 to 0.7 by how
  cleanly they match. A higher timeframe that agrees adds 0.1; one that disagrees takes 0.15.
- **Unavailable is not zero.** Indicators without enough history are null. Fewer than 60 bars on a
  timeframe returns `insufficient_data`.
- **Split-adjusted prices** feed the analysis, so a stock split does not look like a crash.
- Distances are measured in ATR, so the same rules apply to a $5 and a $500 stock.

### Verification performed

| Check | Result |
|---|---|
| Indicators against independent formulas (SMA, EMA, Bollinger, Wilder RSI and ATR, OBV) | Equal to floating-point precision |
| Each candlestick and chart pattern on a constructed example | Recognised once, at the expected bar, with the stop on the losing side |
| Look-alikes (steady trend, flat line, V-shaped recovery, deep pullback, unbroken double top, mismatched highs, ordinary candles, breakout on ordinary volume) | Not reported |
| No look-ahead, 12 truncation points on seeded random walks | Earlier detections identical |
| Whole test suite inside the Docker image | Passes |
| On real market data | **NOT DONE** — needs verified price data (Milestone 2) |

67 tests, all on constructed data, as the top of `backend/tests/test_technical_analysis.py` says.

### Known weaknesses

- **Thresholds are untuned.** Every rule's numbers (how equal two highs must be, how deep a pattern
  must be, what counts as a squeeze) are reasonable defaults chosen without real data.
- **Volume of output.** On random walks the engine reports about 30 to 45 events per timeframe in
  30 bars, mostly fair value gaps and volume imbalances (confidence 0.3 to 0.4). The endpoint
  therefore returns only confidence 0.5 and above unless `min_confidence` says otherwise; the
  threshold itself is as untuned as the rest.
- **Patterns from swings.** Chart patterns are found from three-bar swing points, so a pattern
  whose turns are shallower or faster than that is missed, and the swing size is the same on
  every timeframe.
- **No machine learning yet.** Random forests, gradient boosting, regime clustering and anomaly
  detection are Milestone 6 work, which needs real data to train on.
- The higher-timeframe check uses only the next timeframe up, and only when it was requested.

### Blocked

- Validation on real markets: needs Milestone 2 verified (Alpaca keys).
- Historical performance of comparable setups: needs Milestone 8.

## 5d. Milestone 5, part 1 — institutional holdings from Form 13F (complete, with stated limits)

Options flow (the other half of Milestone 5) is not started: it needs a paid data provider.

### What exists

| Component | Location |
|---|---|
| Parser for 13F-HR, 13F-HR/A and 13F-NT submissions, with cover-page reconciliation | `backend/services/institutional_analysis/parser.py` |
| Ingestion of tracked managers, idempotent and audited | `backend/services/institutional_analysis/ingest.py` |
| Point-in-time reports, amendments, quarter-over-quarter changes, split handling | `backend/services/institutional_analysis/holdings.py` |
| Institutional activity score 0-100 per security | `backend/services/institutional_analysis/scoring.py` |
| Verification against SEC's Form 13F data sets | `backend/services/institutional_analysis/verify.py` |
| Tables `institutional_manager`, `institutional_filing`, `institutional_holding` | `backend/models/institutional.py` |
| `GET /api/v1/institutional/securities/{cusip}`, `/search?name=`, `/managers`, `/managers/{cik}/changes` | `backend/api/institutional.py` |
| 14 tracked managers (names confirmed on EDGAR), editable | `config/settings.yaml` → `tracked_managers` |

### Rules that came from the real filings

- **A filing is a delayed snapshot.** Every result names its quarter end and the moment it became
  public, and nothing is used before that moment. Results never claim a manager holds something now.
- **Confidential positions arrive late.** Pershing Square's Hertz stake was omitted from its
  December 2024 report (filed 14 February 2025) and disclosed by a "new holdings" amendment on
  16 April 2025. It is added only from that moment, and is then an increase the next quarter,
  not a new position.
- **A restatement replaces** the report it amends; adding both would double every share.
- **A 13F-NT is not an exit.** It says another manager reports the holdings. That quarter is
  "reported elsewhere" and the manager is left out of comparisons, never shown as selling.
- **One security, many rows.** Managers split a position across rows; shares are summed per CUSIP.
- **Options are not ownership.** Put and call rows are counted separately and excluded from shares.
- **Value units cannot be trusted from the date.** Values were thousands of dollars before 3 January
  2023 and dollars after, but Baupost, Duquesne and others still file thousands. A filing whose
  median value per share is under $1 is read as thousands, and the filing is flagged.
- **Stock splits are not buying.** 13F says nothing about splits. Nvidia's 10-for-1 split in June
  2024 turns Appaloosa's 84% sale into an apparent 56% purchase. A split is recognised when some
  tracked holder's share count is multiplied by exactly a split ratio and the implied price moved
  the other way; previous shares are then adjusted for everyone. When the implied price moved by
  more than about half or double and no holder shows an exact ratio, the security is marked
  "unclear" for that quarter and not interpreted.
- The cover page states the table's row count and total value; every filing is checked against it.

### Verification performed (2026-11-13)

| Check | Result |
|---|---|
| Parser vs SEC's Form 13F data set for filings of June to August 2025, random sample of 120 holdings reports | 120 of 120 identical: cover fields and all 31,381 holdings rows |
| Real ingestion of the 14 tracked managers, filings since 2024-01-01 | 165 filings, 20,129 rows, 0 failures; every table reconciles with its cover page |
| Value unit | Confirmed on Berkshire: about $0.14 "per share" for Apple in the November 2022 filing (thousands) and $129.93 in February 2023 (dollars). 24 of the 165 filings were read as thousands by the per-share rule |
| Splits found across nine quarters of real data | Nvidia 10-for-1 and Palo Alto 2-for-1 recognised; Broadcom, Netflix, Chipotle, Interactive Brokers and Deckers (real splits no tracked holder carried exactly) marked unclear |
| Automated tests | 33 tests on 14 real submissions stored unmodified |

Reproduce: `python -m backend.services.institutional_analysis.verify <data set>.zip`.

### Partially complete

- **Score.** Four components (breadth, new positions, net buying, consistency over two quarters),
  normalised over those available. Weights are unvalidated priors. It ranks accumulation only;
  net selling scores 0 and is reported in the counts.
- **Split handling** is inferred from the holders. A split nobody carried exactly, or simply a
  very large real price move, makes a security "unclear" for that quarter. Verified market data
  (Milestone 2) would replace the inference with actual split dates.
- **The thousands rule** misreads a filing only if most of a manager's holdings trade under $1.

### Limits

- **Coverage is the tracked list.** "3 of 13 managers added" describes those managers, not the
  market. Adding managers is a settings change; the largest quantitative firms file tens of
  thousands of rows a quarter.
- **13F has no tickers.** Securities are identified by CUSIP; `/search` finds a CUSIP by the issuer
  name managers report. Mapping tickers to CUSIPs needs a licensed source and is not done.
- 13F covers long positions in listed US securities only: no shorts, no cash, no foreign listings.
- Filings before 2013 are text-only and are not parsed.

### Not done

- Options flow: needs a paid provider (Polygon or Tradier). This is the only part of Milestone 5 left.

## 5e. Milestone 5, part 2 — Schedules 13D and 13G (complete, with stated limits)

### 13D and 13G are different statements

| | Schedule 13D | Schedule 13G |
|---|---|---|
| Who files | A holder above 5% who has, or may have, the purpose of influencing or controlling the company | A passive holder above 5%: institutions and passive investors |
| What it says | The stake and the purpose of the transaction (Item 4) | The stake and the rule relied on; nothing about intent |
| How fresh | Amended promptly on material changes | Mostly updated quarterly or yearly |

Every record carries its schedule and a plain-language meaning, and the API can filter on it.
A holder who moves from 13G to 13D is flagged, since that is a statement of changed intent.

### What exists

| Component | Location |
|---|---|
| Parser for structured SCHEDULE 13D, 13D/A, 13G, 13G/A (both schema layouts) and for EDGAR's filing header | `backend/services/beneficial_ownership/parser.py` |
| Ingestion per issuer, idempotent and audited | `backend/services/beneficial_ownership/ingest.py` |
| History, each holder's latest position, and changes between a holder's filings | `backend/services/beneficial_ownership/history.py` |
| Tables `beneficial_issuer`, `beneficial_filing`, `beneficial_owner` | `backend/models/beneficial.py` |
| `GET /api/v1/ownership/{ticker}/holders`, `GET /api/v1/ownership/{ticker}/filings` (both take `as_of` and `schedule`) | `backend/api/ownership.py` |

Stored per filing: schedule, form, amendment number, event date, filing date, public-availability
time, security and CUSIP, who filed it, the rule (13G) or purpose text (13D), every reporting
person with shares, percentage of the class and voting/dispositive powers, and a link to the filing.

### Rules that came from the real filings

- **Structured data starts in December 2024.** Earlier filings ("SC 13D", "SC 13G") are free-form
  documents. They are kept as dated history entries with the filer's name, taken from EDGAR's own
  header, and with shares and percentage marked unknown. Their numbers are not guessed.
- **A company's index mixes two things**: stakes others hold in it, and stakes it holds in others.
  One of Intel's entries is Intel reporting its MariaDB stake. Structured filings are matched on
  the issuer in the document, free-form ones on the subject company in EDGAR's header.
- **Persons on one filing are not added up.** A fund, its adviser and its owner each report the
  same shares. The largest reporting person stands for the filing.
- **Share changes and percentage changes are separate facts.** Between two of Ryan Cohen's
  GameStop amendments the share count stayed at 42,082,626 while the stake fell from 9.3% to 8.3%,
  because the share class grew. Each change reports both, with a note when only one moved, and
  a note when shares jump but the percentage does not (a split or share-class change).
- **Holders are followed by name.** The account a filing is submitted under varies (the person, a
  fund vehicle, a law firm), so a holder's history is linked by the reporting person's name.
- A filing reporting less than 5% is kept and marked as an exit below the threshold.

### Verification performed (2026-11-14)

| Check | Result |
|---|---|
| Real ingestion of 16 issuers since November 2023 | 320 filings stored (197 structured, 123 free-form), 0 failures, 15 filings about other companies skipped |
| Parser vs an independent text extraction of the same documents (SEC publishes no bulk 13D/13G data set to compare against) | 208 of 208 structured filings and all 407 reporting persons agree on names, shares, percentages, issuer, CUSIP, form and amendment number |
| Automated tests | 28 tests on 16 real documents stored unmodified |

### Limits

- **Delayed and as of an event date.** Never the holder's position today. A 13G in particular can
  be a year old.
- **Percentages are the filer's own.** They are not recomputed, and different filers may use
  different share counts for the same class.
- **Name linking** treats "The Vanguard Group" and "VANGUARD GROUP INC" as different holders, and
  would merge two different holders with identical names.
- **No history of figures before December 2024**, only the fact and date of each filing.
- Only the first CUSIP is stored when a filing lists several.

## 5f. Scheduled ingestion (complete)

`python -m backend.services.scheduler` runs as a loop (the `worker` service in the compose file),
or once with `--once` for cron. Three jobs, each with its own interval in `config/settings.yaml`
under `ingestion`: `insider` (Forms 3/4/5 for the `watchlist`, hourly), `beneficial` (13D/13G for
the `watchlist`, every six hours), `institutional` (13F for `tracked_managers`, daily).

| Requirement | How it is met |
|---|---|
| Safe to run repeatedly | Ingestion skips filings already stored; a second pass stores nothing and makes no requests for them |
| Duplicate protection | A unique constraint lets the database hold only one running row per job, so two workers cannot run the same job. A run left "running" past `stale_after_minutes` is closed as abandoned and taken over |
| Retries | Each request retries with backoff; a failed job is tried again after `retry_after_minutes`; filings that failed are retried on the next run |
| Failure reporting | Every run is stored in `job_run` with per-target results and an error summary, written to the audit log, logged, and served by `GET /api/v1/jobs` with what is due next |
| One bad target | Does not stop the others, whatever the error (an unexpected one is logged with its traceback); the run is recorded as `partial` |
| Another process storing the same filings | A manual ingest or second worker storing a filing first is counted as already stored, not as an error (any other constraint failure is still raised) |
| Graceful stop | On SIGTERM the worker finishes the current target, records the run as `interrupted` with the targets it did not reach, and exits; an interrupted run is retried after `retry_after_minutes`. The compose file gives the worker 2 minutes to stop |
| Database or other failure in a pass | Logged; the worker tries again at the next poll instead of exiting |

Verified: 15 tests, 17 cases (clock-controlled, on the real SEC fixtures) and a live run against EDGAR for
5 watchlist tickers and 14 managers (all three jobs succeeded; an immediate second pass ran
nothing).

Review of 2026-11-16 (continuous running). Each defect below was first reproduced by a test that
failed on the unfixed code:

- A filing stored by another process between listing and storing (a manual ingest during a
  worker run) raised a uniqueness error that failed the whole 13D/13G or 13F job. Insider
  ingestion avoided the error only by deleting and re-inserting the other process's row, counted
  as a re-classification. All three now count it as already stored.
- An unexpected error on one target (anything but an SEC or data error) failed the whole job and
  skipped every later target, on every run.
- Stopping the worker left its run marked "running", so the job did not run again until the
  stale limit (3 hours by default). Docker's default 10-second stop also killed it mid-target.
- Any exception in a scheduler pass (for example the database restarting) ended the worker.
- In the 13D/13G API, `schedule=13G` was applied before working out each holder's latest filing,
  so a holder that had moved from 13G to 13D was still listed as a passive 13G holder.

Not done, and limits:
- No alerts when a run fails (it is recorded and visible, but nobody is notified).
- A run is considered abandoned only by age: a genuine run longer than `stale_after_minutes`
  (3 hours) would be taken over by another worker. Real runs took seconds with a warm cache;
  first runs on a cold cache are longer but were not timed. A heartbeat column would remove the
  limit; it is a schema change, left for after migrations land.
- SEC request spacing (8 per second) is per process. A manual ingest during a worker run can
  together exceed SEC's guideline of 10 per second and get the address blocked for a while.
- `job_run` and `audit_log` grow without limit (about 30 runs and 200 audit rows a day with the
  default watchlist); there is no retention policy yet.

## 5g. Database migrations (complete)

The schema is now managed by Alembic (`backend/migrations/`); `create_all` is gone. Every start of
the API, the worker and the ingestion commands upgrades the database to the newest revision.

| Behaviour | How |
|---|---|
| Fresh database | Revision `0001` creates all 13 tables. |
| Database created before migrations | `0001` creates only the tables that are missing and records the revision. Existing tables and rows are not touched. |
| Reversible | Every revision has a downgrade. Reversing `0001` drops the tables, so it refuses to run while any of them holds a row. |
| API and worker starting together | On PostgreSQL the migration takes a transaction-level advisory lock, so the second process waits. |
| Model changed without a migration | A test compares the migrated schema with the models and fails. |
| Schema differs from the models at start-up | Logged as an error with the differences (never altered silently). |

Changing the schema: edit the model, then
`alembic -c backend/alembic.ini revision --autogenerate -m "what changed"`, review the generated
file, and add a test if it moves data.

Safety audit (2026-11-15) and what it changed:

- **Older databases.** The database was rebuilt as each of the seven past commits that changed
  the models created it, on SQLite and on PostgreSQL, then adopted. Three early versions lacked
  two columns (`insider_filing.classifier_version`, `insider_issuer.failed_filings`); adoption
  left those databases unusable. The baseline now adds them. Existing rows get 0: for
  `classifier_version` that is below every real version, so ingestion re-classifies those filings;
  for `failed_filings` it stands only until the next ingestion run. All seven now adopt with no
  difference from the models and no rows lost. The seven schemas are kept as test fixtures.
- **Failed migration.** On SQLite a migration that failed half way kept its table changes (Python's
  default SQLite mode commits them immediately). Migrations now run on SQLite with transactional
  DDL, so a failure rolls back everything on both databases. Only migrations use that mode (see
  the reassessment below).
- **Lock.** Besides four processes starting at once, a process is shown to wait while another
  holds the lock, to leave the schema untouched meanwhile, and to finish once it is released.
  PostgreSQL releases the lock itself if the holder dies. There is no time limit on the wait.
- **Downgrade.** On PostgreSQL the baseline downgrade now locks the tables before checking that
  they are empty, so nothing can be written between the check and the drop. The migration tests
  refuse to run against a database that holds rows.

Verified (2026-11-15): 13 migration tests. On SQLite 17 pass (10 tests plus the seven historical
schemas) and the two lock tests are skipped; on PostgreSQL 16 (TimescaleDB image) all 12 that take
a database pass. Both lock tests fail when the lock is disabled. Seven real
databases left from earlier ingestion runs, all created before migrations (81,173 rows; four of
them missing the columns above), were adopted as copies: a hash of every existing row was
identical before and after, and none differed from the models afterwards. In the sandbox
Docker stack: a database created by the previous image was adopted (revision recorded, row counts
only grew, `downgrade base` refused), and three cold starts of API and worker together on an empty
database each ran the baseline exactly once with no errors. CI runs the migration tests against a
PostgreSQL service.

Reassessment against the updated PR #2 (2026-11-16). PR #2's fixes merged into the migrations
branch without conflict and changed no table. One regression was found in the migrations work
itself: transactional DDL had been switched on for every SQLite connection, and in that mode a
session that has only read keeps a lock that blocks other processes' writes until it ends. PR #2's
new test of a manual ingest running beside the worker failed with "database is locked". Only
migrations now use that mode, through their own connection, both at start-up and from the
`alembic` command. The failed-migration test runs through both paths; with the start-up path's
setting removed it fails. PostgreSQL was never affected.

Verified after the reassessment: full suite 412 passed with PostgreSQL, 399 on SQLite (12 skipped);
migration tests 18 passed on SQLite (2 lock tests skipped) and 13 on PostgreSQL; PR #2's scheduler
tests, including the race between a manual ingest and the worker, pass on SQLite and on
PostgreSQL; the seven real databases (81,173 rows) again kept every row unchanged. In the sandbox
Docker stack, a cold start ran the baseline once with no errors, and stopping the worker mid-run
recorded the run as interrupted, naming the target it had not reached, within 4 seconds.

Not done: offline SQL script generation (`alembic --sql`); TimescaleDB hypertables (no table uses
them yet).

## 6. Known shortcuts and deferred items

- Migrations (section 5g): the baseline repairs the two column gaps that past versions of the
  platform really had. Any other difference in a pre-migration database (for example a missing
  index) is reported at start-up, not repaired.
- Migration downgrades are tested on empty tables only (the baseline refuses to drop data); each
  future migration that changes data needs its own test with rows in place.
- SQLite stores decimals as floating point (about 15 significant digits); PostgreSQL is exact.
- Redis is not in the stack. The price cache is the database; add Redis only when something
  needs shared short-lived state (for example streaming quotes or job coordination).
- The API rate limit counts requests inside one process. Before running several workers or
  exposing the API beyond localhost, move it to a shared store or a reverse proxy.
- Uvicorn's own access log lines are plain text, not JSON (they contain no secrets).
- Single shared bearer token rather than user accounts; revisit with the dashboard (M9).
- No database backup job yet; add with deployment docs (M10).
- Schedules 13D/13G: a holder's history is linked by the reporting person's name, so differently
  spelled names count as different holders (section 5e).
- Scheduler limits (section 5f): no alerts on failed runs; a run is judged abandoned by age only;
  SEC request spacing is per process; `job_run` and `audit_log` have no retention policy.

## 7. Before production

Everything here is known and documented, and none of it is hidden by the tests passing. Items
marked *(decision)* change the architecture or add a service, so they wait for the owner.

Reliability of the worker
- **Job lock judged by age.** A worker killed without warning (out of memory, host restart,
  `kill -9`) leaves its run marked running, and that job does not run again until
  `stale_after_minutes` (3 hours) has passed; the other jobs are not affected. Conversely, a
  genuine run longer than 3 hours could be taken over by a second worker. Ingestion is
  idempotent, so an overlap would not corrupt data, but it doubles the load on SEC. Fix: a lock
  that the database releases when the connection dies (a PostgreSQL advisory lock) or a heartbeat
  column. *(decision)*
- **No alerting.** Failed, partial and interrupted runs are stored, logged and shown by
  `GET /api/v1/jobs`, but nobody is notified. *(decision: which channel)*
- **SEC request rate is limited per process** (8 per second). Two processes ingesting at once can
  exceed SEC's 10 per second guideline and have the address blocked for a while. Fix: a shared
  limiter, or a rule that manual ingestion is not run while the worker runs.
- **First runs on an empty cache were never timed.** Warm-cache runs take seconds; the stale limit
  must stay above the longest real run.
- **No retention** for `job_run` and `audit_log` (about 30 and 200 rows a day by default).

Verification still missing
- Full Docker stack (database, API, worker) on a normal network with access to sec.gov: only run
  in the development sandbox. The image itself is built and tested in CI.
- PostgreSQL adoption of a real, populated pre-migration database: none existed; checked on
  rebuilt schemas and a small database.
- Alpaca market data (M2) against the real API, and technical analysis (M3) on real prices: need
  Alpaca paper keys.
- The 13D/13G parser was checked against a second extraction of the same filings, not against an
  SEC data set (SEC publishes none).

Data limits that stay true in production
- 13D/13G holders are linked across filings by name; spelling variants split a holder in two.
- 13D/13G filings before December 2024 have no figures; 13F and 13D/13G are delayed disclosures,
  never current holdings.

Operations and security
- No database backups (planned with M10).
- One shared API bearer token and an in-process rate limit: do not expose the API beyond a trusted
  network until accounts and a shared limiter exist (M9).
- The runtime image also contains the test and type-check tools (`pytest`, `mypy`); a separate
  production image without them would be smaller.
- SQLite is for development: its writes are serialised and wait at most 5 seconds for a lock.
  Deployment uses PostgreSQL.
