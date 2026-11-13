# AI Trading Platform — Project Status

Last updated: 2026-11-13 · Milestones complete: **1, 4** · In progress: **2**

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
needed to verify M2 against live data and for M7.

## 4. Roadmap

- [x] **M1 Foundation** — structure, config, logging, database, API, tests, Docker
- [ ] **M2 Market data** — provider adapter interface, Alpaca adapter, normalization, cache, integrity checks
- [ ] **M3 Technical analysis** — indicators, candlestick/chart patterns, market structure
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
| Startup/shutdown audit, graceful shutdown | `backend/main.py` | test; `audit_log` rows observed in Postgres |
| Docker stack (API + TimescaleDB) | `docker-compose.platform.yml`, `docker/Dockerfile.platform` | built and run; see caveat |

Caveat on the Docker verification: the development sandbox intercepts TLS, so the image was
built from a temporary copy of the Dockerfile with two extra lines trusting the sandbox CA.
The committed Dockerfile has not itself been built on a normal network, and has not been rebuilt
since Milestone 4 added code.

## 5a. Milestone 4 — insider intelligence (complete, with stated limits)

### What exists

| Component | Location |
|---|---|
| EDGAR client: declared User-Agent, 8 requests/s throttle, retry with backoff, permanent cache for filings, TTL cache for indexes, URL/path validation | `backend/services/edgar.py` |
| Parser for Forms 3, 4, 5 and amendments, with field-level validation | `backend/services/insider_intelligence/parser.py` |
| Classification and signal eligibility | `backend/services/insider_intelligence/classify.py` |
| Idempotent ingestion, per-filing atomic writes, failure reporting, re-classification on rule change | `backend/services/insider_intelligence/ingest.py` |
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
| Automated tests | 118 offline tests on 26 real filings stored unmodified; 4 opt-in live tests, including a byte-for-byte comparison of a fixture with what EDGAR serves |

Reproduce: `python -m backend.services.insider_intelligence.verify <quarter>_form345.zip`
(needs `SEC_USER_AGENT`), and `EDGAR_LIVE_TESTS=1 pytest -m live`.

SEC's data set itself differs from the filings in three documented ways (two-decimal rounding,
optional fields shifted between rows, joint filers' roles merged); `verify.py` explains how each
is handled. The original filing is treated as the source of truth.

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

## 6. Known shortcuts and deferred items

- Schema is created with `create_all`, which cannot alter existing tables. A development database
  created before a model change must be deleted and re-ingested (filings are cached). Adopt
  Alembic before the first deployment that must keep its data.
- SQLite stores decimals as floating point (about 15 significant digits); PostgreSQL is exact.
- Redis is not in the stack yet; it is added with the cache in M2.
- No rate limiting on the API yet (single-user, bound to localhost); add before any non-local exposure.
- Uvicorn's own access log lines are plain text, not JSON (they contain no secrets).
- Single shared bearer token rather than user accounts; revisit with the dashboard (M9).
- No database backup job yet; add with deployment docs (M10).
