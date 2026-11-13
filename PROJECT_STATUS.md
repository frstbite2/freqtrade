# AI Trading Platform — Project Status

Last updated: 2026-11-13 · Complete and verified: **1, 4** · Built, live verification pending: **2** · Built, unverified on real data: **3**

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
- [ ] **M5 Institutional + options** — 13F diffs, 13D/13G, unusual options activity, scoring
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

Docker verification, repeated on 2026-11-13 with all code through Milestone 3: the stack starts
on TimescaleDB, creates all six tables, answers on every endpoint, and the full test suite passes
inside the image (Python 3.12, TA-Lib from its binary wheel). Caveat: the development sandbox intercepts TLS, so the image was
built from a temporary copy of the Dockerfile with two extra lines trusting the sandbox CA. The
committed Dockerfile is otherwise identical but has not itself been built on a normal network.

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

- Forms 13D, 13G and 13F: Milestone 5.
- Scheduled or continuous ingestion and alerts: ingestion is a manual command today.
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
  30 bars, mostly fair value gaps and volume imbalances (confidence 0.3 to 0.4). The dashboard
  and decision engine will need to filter or rank them.
- **Patterns from swings.** Chart patterns are found from three-bar swing points, so a pattern
  whose turns are shallower or faster than that is missed, and the swing size is the same on
  every timeframe.
- **No machine learning yet.** Random forests, gradient boosting, regime clustering and anomaly
  detection are Milestone 6 work, which needs real data to train on.
- The higher-timeframe check uses only the next timeframe up, and only when it was requested.

### Blocked

- Validation on real markets: needs Milestone 2 verified (Alpaca keys).
- Historical performance of comparable setups: needs Milestone 8.

## 6. Known shortcuts and deferred items

- Schema is created with `create_all`, which cannot alter existing tables. A development database
  created before a model change must be deleted and re-ingested (filings are cached). Adopt
  Alembic before the first deployment that must keep its data.
- SQLite stores decimals as floating point (about 15 significant digits); PostgreSQL is exact.
- Redis is not in the stack. The price cache is the database; add Redis only when something
  needs shared short-lived state (for example streaming quotes or job coordination).
- The API rate limit counts requests inside one process. Before running several workers or
  exposing the API beyond localhost, move it to a shared store or a reverse proxy.
- Uvicorn's own access log lines are plain text, not JSON (they contain no secrets).
- Single shared bearer token rather than user accounts; revisit with the dashboard (M9).
- No database backup job yet; add with deployment docs (M10).
