# CLAUDE.md

Two codebases live here:

- `freqtrade/`, `tests/`, `docs/`, `docker-compose.yml`, `requirements*.txt` — upstream freqtrade
  (crypto bot). Leave it untouched unless explicitly asked.
- `backend/`, `config/`, `docker-compose.platform.yml`, `docker/Dockerfile.platform`,
  `requirements-platform.txt` — the AI trading platform. It does not import freqtrade.

Read `PROJECT_STATUS.md` first: audit, architecture, roadmap, required APIs, known shortcuts.
Update it whenever a milestone item is completed or deferred.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-platform.txt
cd backend && ../.venv/bin/pytest          # platform tests (own pytest.ini)
.venv/bin/ruff check backend && .venv/bin/ruff format backend
API_AUTH_TOKEN=dev .venv/bin/uvicorn --factory backend.main:create_app --reload
docker compose -f docker-compose.platform.yml up -d --build   # needs .env (see .env.example)

# Insider filings (needs SEC_USER_AGENT="Name email@example.com" and access to sec.gov)
.venv/bin/python -m backend.services.insider_intelligence.ingest NKE AAPL --since 2023-01-01
.venv/bin/python -m backend.services.insider_intelligence.verify 2024q3_form345.zip --sample 300
cd backend && EDGAR_LIVE_TESTS=1 ../.venv/bin/pytest -m live -k edgar

# Market data: live verification is PENDING until Alpaca keys exist
cd backend && ALPACA_LIVE_TESTS=1 ALPACA_API_KEY=... ALPACA_SECRET_KEY=... ../.venv/bin/pytest -m live -k alpaca
```

## Rules

- One milestone at a time; tests pass before moving on. Never claim something works untested.
- Paper trading only. `trading_mode: live` must stay a validation error until the user
  explicitly authorizes the Milestone 7 live gate.
- The risk engine is independent; the decision engine can never override hard limits.
- Secrets come from environment variables only. Never in YAML, code, logs, or API responses.
  New secrets are registered in `SECRET_ENV_VARS` (`backend/core/config.py`) so they are redacted,
  and added to `.env.example` with an empty placeholder.
- Never fabricate market data, filings, or results. If a provider is not configured, report
  "unavailable" — distinct from zero activity. No silent simulated-data fallbacks.
- Store the public-availability timestamp with every external record; backtests may only use data
  available at the simulated time.
- Scores are research rankings, not probabilities. Disclosed insider/13F data is delayed public
  disclosure — never describe it as illegal activity or as current holdings.
- Create `backend/services/<engine>/` only when implementing that engine; no placeholder modules.
- Test parsing and classification on real filings. To add one, save the document byte-for-byte in
  `backend/tests/fixtures/edgar/` with its index metadata in `manifest.json`; never edit a fixture.
- Any change to `classify.py` rules must bump `CLASSIFIER_VERSION`, so stored rows are re-classified.
- Tests without real data must say so at the top of the file. The Alpaca adapter stays marked
  "live verification pending" in code and in PROJECT_STATUS.md until `test_alpaca_live.py` has passed.
- Reuse `backend/core/http.py` (retry, request spacing) for any new provider.
- Technical analysis is unverified on real data until M2 is verified; keep that stated in
  `engine.py`, the API disclaimer and PROJECT_STATUS.md. Detectors must stay causal: the
  truncation test in `test_technical_analysis.py` must keep passing.
- Insider signals are only clean open-market P/S trades. Never count grants, exercises, tax
  withholding, gifts or plan trades; when a filing is ambiguous, exclude it and record the issue.
