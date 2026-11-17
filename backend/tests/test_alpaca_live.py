"""Live checks against Alpaca. PENDING: these have never been run, because no API keys were
available when the adapter was written. They are the verification step for Milestone 2.

    ALPACA_LIVE_TESTS=1 ALPACA_API_KEY=... ALPACA_SECRET_KEY=... pytest -m live -k alpaca

Free (paper) keys are enough; the default feed is "iex". The assertions are facts that do not
depend on any particular price: the trading calendar, internal consistency, and that paging
returns the same data as a single request.
"""

import os
from datetime import UTC, datetime

import pytest

from backend.services.market_data import alpaca as alpaca_module
from backend.services.market_data.alpaca import AlpacaMarketData
from backend.services.market_data.base import MarketDataError
from backend.services.market_data.integrity import check_bars


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (
            os.environ.get("ALPACA_LIVE_TESTS")
            and os.environ.get("ALPACA_API_KEY")
            and os.environ.get("ALPACA_SECRET_KEY")
        ),
        reason="set ALPACA_LIVE_TESTS=1, ALPACA_API_KEY and ALPACA_SECRET_KEY to run these",
    ),
]

JAN, FEB = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def client():
    client = AlpacaMarketData(
        os.environ["ALPACA_API_KEY"],
        os.environ["ALPACA_SECRET_KEY"],
        feed=os.environ.get("ALPACA_FEED", "iex"),
    )
    yield client
    client.close()


def test_daily_bars_for_a_closed_month(client):
    bars = client.get_bars("AAPL", "1d", JAN, FEB, "raw")
    report = check_bars(bars, "AAPL", "1d", JAN, FEB)
    assert report.rejected == []
    # US markets were open 21 days in January 2024 (closed 1 January and 15 January).
    days = [b.ts.date().isoformat() for b in report.accepted]
    assert (days[0], days[-1]) == ("2024-01-02", "2024-01-31")
    assert len(report.accepted) == 21
    assert all(b.ts.weekday() < 5 for b in bars)
    # 23 weekdays minus 21 trading days: exactly the two holidays should be flagged as missing.
    assert any(w.startswith("2 weekday(s)") for w in report.warnings), report.warnings


def test_paging_returns_the_same_bars_as_one_request(client, monkeypatch):
    whole = client.get_bars("AAPL", "1d", JAN, FEB, "raw")
    monkeypatch.setattr(alpaca_module, "PAGE_LIMIT", 5)
    before = client.requests_made
    assert client.get_bars("AAPL", "1d", JAN, FEB, "raw") == whole
    assert client.requests_made - before >= 5


def test_intraday_bars_are_consistent_and_on_the_grid(client):
    start, end = datetime(2024, 1, 3, 14, 30, tzinfo=UTC), datetime(2024, 1, 3, 21, 0, tzinfo=UTC)
    report = check_bars(client.get_bars("AAPL", "5m", start, end, "raw"), "AAPL", "5m", start, end)
    assert report.accepted and report.rejected == []
    assert not any("boundary" in w for w in report.warnings), report.warnings


def test_split_adjustment_changes_history_before_a_split(client):
    """Apple split 4-for-1 on 2020-08-31: adjusted closes before it are a quarter of raw."""
    start, end = datetime(2020, 8, 3, tzinfo=UTC), datetime(2020, 8, 8, tzinfo=UTC)
    raw = client.get_bars("AAPL", "1d", start, end, "raw")
    split = client.get_bars("AAPL", "1d", start, end, "split")
    if not raw:
        pytest.skip("this feed has no history for August 2020")
    assert len(raw) == len(split)
    for r, s in zip(raw, split, strict=True):
        assert abs(r.close / s.close - 4) < 0.01


def test_latest_quote_parses(client):
    quote = client.get_latest_quote("AAPL")
    assert quote.symbol == "AAPL" and quote.ts.tzinfo is not None


def test_unknown_symbol_and_bad_keys_are_not_silent(client):
    # Either an empty list or an explicit error is acceptable; record which one Alpaca gives.
    try:
        assert client.get_bars("ZZZZZZZZ", "1d", JAN, FEB, "raw") == []
    except MarketDataError as exc:
        assert "ZZZZZZZZ" in str(exc) or "4" in str(exc)
    bad = AlpacaMarketData("invalid-key", "invalid-secret", max_attempts=1)
    with pytest.raises(MarketDataError, match=r"40[13]"):
        bad.get_bars("AAPL", "1d", JAN, FEB, "raw")
    bad.close()
