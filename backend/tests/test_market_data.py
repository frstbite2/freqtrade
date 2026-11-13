"""Market data: Alpaca adapter, integrity checks, caching service and API.

NO REAL MARKET DATA IS USED HERE. No Alpaca keys were available, so every price in this file is
made up for the test, and the Alpaca payloads follow the field names in Alpaca's official SDK
(alpaca-py 0.45.0). These tests prove the code's logic; they do not prove it matches the live
service. That check is `test_alpaca_live.py`, which is pending API keys.
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.core.config import load_settings
from backend.main import create_app
from backend.models.market import PriceBar, PriceCoverage
from backend.services.market_data.alpaca import AlpacaMarketData
from backend.services.market_data.base import Bar, MarketDataError, ProviderNotConfigured, Quote
from backend.services.market_data.integrity import check_bars
from backend.services.market_data.service import MarketDataService, uncovered


D = Decimal
KEY, SECRET = "test-key-id", "test-secret-value"


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


JAN2, JAN9 = at("2024-01-02"), at("2024-01-09")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    return slept


# --- Alpaca adapter (synthetic payloads shaped like the SDK's field mapping) ---


def raw_bar(t="2024-01-02T05:00:00Z", **changes):
    return {
        "t": t,
        "o": 10.5,
        "h": 11.25,
        "l": 10.125,
        "c": 11.0,
        "v": 1200,
        "n": 34,
        "vw": 10.8,
    } | changes


def alpaca(handler, **kwargs) -> AlpacaMarketData:
    kwargs.setdefault("min_interval", 0)
    return AlpacaMarketData(KEY, SECRET, transport=httpx.MockTransport(handler), **kwargs)


def serving(body, status=200):
    return lambda request: httpx.Response(status, json=body)


@pytest.mark.parametrize(("key", "secret"), [(None, None), ("k", None), (None, "s"), ("", "")])
def test_missing_keys_mean_unavailable(key, secret):
    with pytest.raises(ProviderNotConfigured):
        AlpacaMarketData(key, secret)


def test_unknown_feed_is_refused():
    with pytest.raises(ValueError, match="feed"):
        AlpacaMarketData(KEY, SECRET, feed="everything")


def test_bars_request_and_exact_parsing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            content=b'{"bars": {"AAPL": [{"t": "2024-01-02T05:00:00Z", "o": 187.15, "h": 188.44,'
            b' "l": 183.885, "c": 185.64, "v": 82488674, "n": 1008871, "vw": 185.937347}]},'
            b' "next_page_token": null}',
        )

    (bar,) = alpaca(handler, feed="sip").get_bars("aapl", "1d", JAN2, JAN9, "split")
    (request,) = seen
    assert request.url.path == "/v2/stocks/bars" and request.url.host == "data.alpaca.markets"
    assert dict(request.url.params) == {
        "symbols": "AAPL",
        "timeframe": "1Day",
        "start": "2024-01-02T00:00:00Z",
        "end": "2024-01-09T00:00:00Z",
        "limit": "10000",
        "adjustment": "split",
        "feed": "sip",
        "sort": "asc",
    }
    assert request.headers["APCA-API-KEY-ID"] == KEY
    assert request.headers["APCA-API-SECRET-KEY"] == SECRET
    assert KEY not in str(request.url) and SECRET not in str(request.url)
    assert bar == Bar(
        symbol="AAPL",
        timeframe="1d",
        ts=at("2024-01-02T05:00:00"),
        open=D("187.15"),
        high=D("188.44"),
        low=D("183.885"),  # kept exactly as sent, not rounded through a float
        close=D("185.64"),
        volume=D("82488674"),
        trade_count=1008871,
        vwap=D("185.937347"),
    )


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ("1m", "1Min"),
        ("5m", "5Min"),
        ("15m", "15Min"),
        ("1h", "1Hour"),
        ("4h", "4Hour"),
        ("1w", "1Week"),
    ],
)
def test_timeframe_names(ours, theirs):
    seen = []

    def handler(request):
        seen.append(request.url.params["timeframe"])
        return httpx.Response(200, json={"bars": {}, "next_page_token": None})

    assert alpaca(handler).get_bars("AAPL", ours, JAN2, JAN9) == []
    assert seen == [theirs]


def test_pagination_collects_every_page():
    pages = {
        None: {"bars": {"AAPL": [raw_bar("2024-01-02T05:00:00Z")]}, "next_page_token": "p2"},
        "p2": {"bars": {"AAPL": [raw_bar("2024-01-03T05:00:00Z")]}, "next_page_token": "p3"},
        "p3": {"bars": {"AAPL": [raw_bar("2024-01-04T05:00:00Z")]}, "next_page_token": None},
    }
    client = alpaca(lambda r: httpx.Response(200, json=pages[r.url.params.get("page_token")]))
    bars = client.get_bars("AAPL", "1d", JAN2, JAN9)
    assert [b.ts.day for b in bars] == [2, 3, 4] and client.requests_made == 3


def test_pagination_that_does_not_advance_is_an_error():
    stuck = {"bars": {"AAPL": [raw_bar()]}, "next_page_token": "same"}
    with pytest.raises(MarketDataError, match="pagination did not advance"):
        alpaca(serving(stuck)).get_bars("AAPL", "1d", JAN2, JAN9)


@pytest.mark.parametrize(
    "body",
    [{"bars": None}, {"bars": {}}, {"bars": {"AAPL": None}}, {"bars": {"MSFT": [raw_bar()]}}, {}],
)
def test_no_data_is_an_empty_list(body):
    assert alpaca(serving(body)).get_bars("AAPL", "1d", JAN2, JAN9) == []


def test_only_bars_inside_the_half_open_range_are_returned():
    body = {
        "bars": {
            "AAPL": [
                raw_bar("2024-01-01T05:00:00Z"),
                raw_bar("2024-01-02T00:00:00Z"),
                raw_bar("2024-01-08T23:59:00Z"),
                raw_bar("2024-01-09T00:00:00Z"),
            ]
        }
    }
    bars = alpaca(serving(body)).get_bars("AAPL", "1d", JAN2, JAN9)
    assert [b.ts for b in bars] == [at("2024-01-02T00:00:00"), at("2024-01-08T23:59:00")]


def test_nanosecond_timestamps_and_missing_optional_fields():
    body = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-02T14:30:00.123456789Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}
            ]
        }
    }
    (bar,) = alpaca(serving(body)).get_bars("AAPL", "1m", JAN2, JAN9)
    assert bar.ts == datetime(2024, 1, 2, 14, 30, 0, 123456, tzinfo=UTC)
    assert bar.trade_count is None and bar.vwap is None


@pytest.mark.parametrize(
    "bad",
    [
        raw_bar(o="187.15"),  # number sent as text
        raw_bar(h=None),
        raw_bar(v=True),
        raw_bar(n=3.5),
        raw_bar(t="2024-01-02T05:00:00"),  # no timezone
        raw_bar(t="yesterday"),
        raw_bar(t=1704171600),
        {k: v for k, v in raw_bar().items() if k != "c"},
        "not a bar",
    ],
)
def test_malformed_bar_fails_the_whole_response(bad):
    with pytest.raises(MarketDataError, match="malformed bar"):
        alpaca(serving({"bars": {"AAPL": [raw_bar(), bad]}})).get_bars("AAPL", "1d", JAN2, JAN9)


def test_nan_is_not_accepted_as_a_price():
    row = b'{"t": "2024-01-02T05:00:00Z", "o": NaN, "h": 1, "l": 1, "c": 1, "v": 1}'
    body = b'{"bars": {"AAPL": [' + row + b"]}}"
    with pytest.raises(MarketDataError, match="malformed bar"):
        alpaca(lambda r: httpx.Response(200, content=body)).get_bars("AAPL", "1d", JAN2, JAN9)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>maintenance</html>"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"bars": []}),
        httpx.Response(200, json={"bars": {"AAPL": {"t": "x"}}}),
    ],
)
def test_unexpected_response_shapes_are_errors(response):
    with pytest.raises(MarketDataError):
        alpaca(lambda r: response).get_bars("AAPL", "1d", JAN2, JAN9)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {"message": "unauthorized."}, "401.*unauthorized.*check the API keys"),
        (
            403,
            {"message": "subscription does not permit querying recent SIP data"},
            "403.*SIP.*plan",
        ),
        (422, {"message": "invalid timeframe"}, "422.*invalid timeframe"),
        (404, "<html>not found</html>", "404"),
    ],
)
def test_client_errors_are_reported_once_with_alpacas_message(status, body, expected):
    kwargs = {"json": body} if isinstance(body, dict) else {"content": body.encode()}
    client = alpaca(lambda r: httpx.Response(status, **kwargs))
    with pytest.raises(MarketDataError, match=expected) as error:
        client.get_bars("AAPL", "1d", JAN2, JAN9)
    assert client.requests_made == 1
    assert KEY not in str(error.value) and SECRET not in str(error.value)


def test_rate_limit_and_server_errors_are_retried(_no_sleep):
    replies = iter([httpx.Response(429, headers={"Retry-After": "9"}), httpx.Response(503)])
    client = alpaca(
        lambda r: next(replies, httpx.Response(200, json={"bars": {"AAPL": [raw_bar()]}}))
    )
    assert len(client.get_bars("AAPL", "1d", JAN2, JAN9)) == 1
    assert client.requests_made == 3 and _no_sleep == [9.0, 2.0]


def test_persistent_failure_is_an_error_not_empty_data():
    client = alpaca(lambda r: httpx.Response(500), max_attempts=2)
    with pytest.raises(MarketDataError, match="failed after 2 attempts"):
        client.get_bars("AAPL", "1d", JAN2, JAN9)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("AA PL", "1d", JAN2, JAN9), "symbol"),
        (("AAPL", "2d", JAN2, JAN9), "timeframe"),
        (("AAPL", "1d", JAN9, JAN2), "before end"),
        (("AAPL", "1d", datetime(2024, 1, 2), JAN9), "timezone-aware"),  # noqa: DTZ001
        (("AAPL", "1d", JAN2, JAN9, "magic"), "adjustment"),
    ],
)
def test_invalid_requests_never_reach_the_network(args, message):
    client = alpaca(serving({"bars": {}}))
    with pytest.raises(ValueError, match=message):
        client.get_bars(*args)
    assert client.requests_made == 0


def test_latest_quote():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            content=b'{"quotes": {"AAPL": {"t": "2024-01-02T20:59:59.987654321Z", "ax": "V",'
            b' "ap": 185.66, "as": 3, "bx": "V", "bp": 185.63, "bs": 2, "c": ["R"], "z": "C"}}}',
        )

    quote = alpaca(handler).get_latest_quote("aapl")
    assert seen[0].url.path == "/v2/stocks/quotes/latest"
    assert dict(seen[0].url.params) == {"symbols": "AAPL", "feed": "iex"}
    assert quote == Quote(
        "AAPL",
        datetime(2024, 1, 2, 20, 59, 59, 987654, tzinfo=UTC),
        D("185.63"),
        D("2"),
        D("185.66"),
        D("3"),
    )


@pytest.mark.parametrize(
    "body", [{"quotes": {}}, {"quotes": None}, {}, {"quotes": {"AAPL": {"t": "x"}}}]
)
def test_missing_or_malformed_quote_is_an_error(body):
    with pytest.raises(MarketDataError, match="quote"):
        alpaca(serving(body)).get_latest_quote("AAPL")


# --- integrity checks (made-up bars) ---


def bar(ts: datetime, close="10", **changes) -> Bar:
    fields = {
        "symbol": "XYZ",
        "timeframe": "1d",
        "ts": ts,
        "open": D("10"),
        "high": D("11"),
        "low": D("9"),
        "close": D(close),
        "volume": D("100"),
        "trade_count": 5,
        "vwap": D("10"),
    } | changes
    return Bar(**fields)


def test_clean_bars_pass_in_order():
    bars = [bar(at("2024-01-03T05:00")), bar(at("2024-01-02T05:00"))]
    report = check_bars(bars, "XYZ", "1d", JAN2, at("2024-01-04"))
    assert [b.ts.day for b in report.accepted] == [2, 3] and not report.rejected
    assert report.warnings == ["provider returned bars out of chronological order"]


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"symbol": "ABC"}, "wrong_symbol"),
        ({"timeframe": "1h"}, "wrong_timeframe"),
        ({"ts": datetime(2024, 1, 2, 5)}, "naive_timestamp"),  # noqa: DTZ001
        ({"ts": at("2024-01-01T05:00")}, "outside_requested_range"),
        ({"ts": at("2024-01-04T00:00")}, "outside_requested_range"),
        ({"low": D("0"), "open": D("0")}, "non_positive_price"),
        ({"open": D("-10"), "low": D("-11")}, "non_positive_price"),
        ({"volume": D("-1")}, "negative_volume"),
        ({"trade_count": -1}, "negative_trade_count"),
        ({"high": D("8")}, "high_below_low"),
        ({"open": D("12")}, "open_outside_high_low"),
        ({"close": D("8.99")}, "close_outside_high_low"),
        ({"high": D("Infinity")}, "non_finite_number"),
        ({"vwap": D("NaN")}, "non_finite_number"),
    ],
)
def test_impossible_bars_are_rejected_with_a_reason(changes, problem):
    good = bar(at("2024-01-03T05:00"))
    bad = bar(**{"ts": at("2024-01-02T05:00")} | changes)
    report = check_bars([bad, good], "XYZ", "1d", JAN2, at("2024-01-04"))
    assert report.accepted == [good]
    assert [(b, problems) for b, problems in report.rejected] == [(bad, [problem])]


def test_repeated_identical_bar_is_kept_once_conflicting_ones_are_rejected():
    same = bar(at("2024-01-02T05:00"))
    a, b = bar(at("2024-01-03T05:00")), bar(at("2024-01-03T05:00"), close="10.5")
    report = check_bars([same, same, a, b], "XYZ", "1d", JAN2, at("2024-01-04"))
    assert report.accepted == [same]
    assert {tuple(problems) for _, problems in report.rejected} == {
        ("conflicting_duplicate_timestamp",)
    }
    assert len(report.rejected) == 2
    assert "2 repeated timestamp(s) in the provider response" in report.warnings


def test_warnings_for_things_that_may_be_legitimate():
    daily = [
        bar(at("2024-01-02T05:00")),
        bar(at("2024-01-03T05:00"), close="4.9", low=D("4"), open=D("5"), high=D("5"), vwap=D("6")),
    ]
    report = check_bars(daily, "XYZ", "1d", JAN2, JAN9)
    assert len(report.accepted) == 2
    assert any("close moved 51%" in w and "unadjusted split" in w for w in report.warnings)
    assert "1 bar(s) have a VWAP outside their high-low range" in report.warnings
    # 2-8 January 2024 has five weekdays; two have bars.
    assert any(w.startswith("3 weekday(s) in the range have no daily bar") for w in report.warnings)

    minute = [
        bar(at("2024-01-02T14:30:00"), timeframe="5m"),
        bar(at("2024-01-02T14:32:30"), timeframe="5m"),
    ]
    report = check_bars(minute, "XYZ", "5m", JAN2, JAN9)
    assert report.warnings == ["1 bar(s) do not start on a 5m boundary"]


# --- which ranges still need fetching ---


@pytest.mark.parametrize(
    ("covered", "expected"),
    [
        ([], [(2, 9)]),
        ([(2, 9)], []),
        ([(1, 12)], []),
        ([(2, 5)], [(5, 9)]),
        ([(4, 6)], [(2, 4), (6, 9)]),
        ([(1, 3), (8, 20)], [(3, 8)]),
        ([(2, 4), (4, 6), (6, 9)], []),
        ([(10, 12)], [(2, 9)]),
        ([(3, 4), (3, 7)], [(2, 3), (7, 9)]),
    ],
)
def test_uncovered(covered, expected):
    day = lambda n: at(f"2024-01-{n:02d}")  # noqa: E731
    gaps = uncovered((day(2), day(9)), [(day(a), day(b)) for a, b in covered])
    assert gaps == [(day(a), day(b)) for a, b in expected]


# --- caching service (a fake provider with made-up prices) ---


class FakeProvider:
    name, feed = "fake", "test"

    def __init__(self):
        self.calls: list[tuple] = []
        self.price = D("100.125")
        self.extra: list[Bar] = []
        self.fail = False

    def get_bars(self, symbol, timeframe, start, end, adjustment):
        self.calls.append((start, end, adjustment))
        if self.fail:
            raise MarketDataError("provider is down")
        day, bars = start.replace(hour=5, minute=0, second=0, microsecond=0), []
        while day < end:
            if day >= start and day.weekday() < 5:
                bars.append(
                    bar(
                        day,
                        symbol=symbol,
                        open=self.price,
                        high=self.price,
                        low=self.price,
                        close=self.price,
                        vwap=self.price,
                        volume=D("1234.5"),
                    )
                )
            day += timedelta(days=1)
        return bars + [b for b in self.extra if start <= b.ts < end]

    def get_latest_quote(self, symbol):
        return self.quote


NOW = at("2024-03-01T12:00")


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def service(provider):
    return MarketDataService(provider)


def rows(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_second_request_is_served_from_storage_with_exact_values(db_session, service, provider):
    first = service.get_bars(db_session, "xyz", "1d", JAN2, JAN9, now=NOW)
    assert (first.source, first.fetched_ranges, len(first.bars)) == ("fake:test", 1, 5)
    again = service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW)
    assert again.fetched_ranges == 0 and again.bars == first.bars
    assert len(provider.calls) == 1
    assert again.bars[0].close == D("100.125") and again.bars[0].volume == D("1234.5")
    assert again.bars[0].ts == at("2024-01-02T05:00")
    assert (rows(db_session, PriceBar), rows(db_session, PriceCoverage)) == (5, 1)


def test_only_the_missing_part_of_a_range_is_fetched(db_session, service, provider):
    service.get_bars(db_session, "XYZ", "1d", at("2024-01-04"), JAN9, now=NOW)
    result = service.get_bars(db_session, "XYZ", "1d", JAN2, at("2024-01-12"), now=NOW)
    assert provider.calls[1:] == [
        (JAN2, at("2024-01-04"), "raw"),
        (JAN9, at("2024-01-12"), "raw"),
    ]
    assert result.fetched_ranges == 2
    assert [b.ts.day for b in result.bars] == [2, 3, 4, 5, 8, 9, 10, 11]


def test_bars_that_may_still_change_are_fetched_fresh_and_not_stored(db_session, service, provider):
    now = at("2024-01-10T15:00")  # Wednesday; that day's bar is not final yet
    for _ in range(2):
        result = service.get_bars(db_session, "XYZ", "1d", JAN2, at("2024-01-11"), now=now)
        assert [b.ts.day for b in result.bars] == [2, 3, 4, 5, 8, 9, 10]
    stored_until = db_session.scalar(select(func.max(PriceBar.ts)))
    assert stored_until == at("2024-01-09T05:00")
    assert len(provider.calls) == 3  # history once, the unsettled tail twice
    assert provider.calls[1][1] == provider.calls[2][1] == now  # never asks about the future


def test_rejected_bars_are_reported_and_never_stored(db_session, service, provider):
    provider.extra = [bar(at("2024-01-06T05:00"), high=D("1"))]
    result = service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW)
    assert result.rejected == [{"ts": "2024-01-06T05:00:00+00:00", "problems": ["high_below_low"]}]
    assert len(result.bars) == rows(db_session, PriceBar) == 5
    assert db_session.scalar(select(PriceCoverage.rejected_bars)) == 1


def test_adjusted_history_expires_but_raw_history_does_not(db_session, service, provider):
    for adjustment in ("raw", "split"):
        service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, adjustment, now=NOW)
    provider.price = D("50.0625")  # a later split rewrites adjusted history
    later = NOW + timedelta(hours=25)
    raw = service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, "raw", now=later)
    split = service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, "split", now=later)
    assert raw.fetched_ranges == 0 and {b.close for b in raw.bars} == {D("100.125")}
    assert split.fetched_ranges == 1 and {b.close for b in split.bars} == {D("50.0625")}
    assert rows(db_session, PriceBar) == 10 and rows(db_session, PriceCoverage) == 2
    soon = service.get_bars(
        db_session, "XYZ", "1d", JAN2, JAN9, "split", now=later + timedelta(hours=1)
    )
    assert soon.fetched_ranges == 0


def test_provider_failure_stores_nothing(db_session, service, provider):
    provider.fail = True
    with pytest.raises(MarketDataError, match="provider is down"):
        service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW)
    assert (rows(db_session, PriceBar), rows(db_session, PriceCoverage)) == (0, 0)
    provider.fail = False
    assert len(service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW).bars) == 5


def test_without_a_provider_stored_bars_are_served_and_the_rest_is_unavailable(db_session, service):
    service.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW)
    offline = MarketDataService(None, source="fake:test")
    assert len(offline.get_bars(db_session, "XYZ", "1d", JAN2, JAN9, now=NOW).bars) == 5
    with pytest.raises(ProviderNotConfigured, match="unavailable"):
        offline.get_bars(db_session, "XYZ", "1d", JAN2, at("2024-01-12"), now=NOW)
    with pytest.raises(ProviderNotConfigured):
        offline.get_bars(db_session, "ABC", "1d", JAN2, JAN9, now=NOW)
    with pytest.raises(ProviderNotConfigured):
        offline.get_latest_quote("XYZ")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("X Y", "1d", JAN2, JAN9), "symbol"),
        (("XYZ", "3d", JAN2, JAN9), "timeframe"),
        (("XYZ", "1d", JAN2, datetime(2024, 1, 9)), "timezone-aware"),  # noqa: DTZ001
        (("XYZ", "1m", at("2023-01-01"), JAN9), "range too large"),
        (("XYZ", "1d", NOW + timedelta(days=1), NOW + timedelta(days=2)), "in the past"),
    ],
)
def test_service_validates_requests(db_session, service, provider, args, message):
    with pytest.raises(ValueError, match=message):
        service.get_bars(db_session, *args, now=NOW)
    assert provider.calls == []


@pytest.mark.parametrize(
    ("bid", "ask", "age", "problems"),
    [
        ("10.00", "10.02", 5, []),
        ("10.02", "10.00", 5, ["crossed_market"]),
        ("0", "10.00", 5, ["non_positive_price"]),
        ("10.00", "10.02", 3600, ["stale"]),
    ],
)
def test_quote_is_marked_unusable_when_it_should_not_be_traded_on(
    service, provider, bid, ask, age, problems
):
    provider.quote = Quote("XYZ", NOW - timedelta(seconds=age), D(bid), D("1"), D(ask), D("2"))
    quote = service.get_latest_quote("xyz", now=NOW)
    assert (quote["problems"], quote["usable"]) == (problems, not problems)
    assert (quote["bid_price"], quote["ask_price"], quote["age_seconds"]) == (bid, ask, float(age))
    assert quote["source"] == "fake:test"


# --- API ---

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(load_settings())) as client:
        yield client


def test_api_reports_unavailable_without_keys(api):
    for path in ("/api/v1/market/AAPL/bars", "/api/v1/market/AAPL/quote"):
        response = api.get(path, headers=AUTH)
        assert response.status_code == 503 and "unavailable" in response.json()["detail"]
    assert api.get("/api/v1/status", headers=AUTH).json()["providers_configured"]["alpaca"] is False


def test_api_bars(api, provider):
    api.app.state.market_data = MarketDataService(provider)
    response = api.get(
        "/api/v1/market/xyz/bars",
        params={"start": "2024-01-02T00:00:00Z", "end": "2024-01-09T00:00:00Z"},
        headers=AUTH,
    )
    body = response.json()
    assert response.status_code == 200
    assert (body["symbol"], body["timeframe"], body["adjustment"]) == ("XYZ", "1d", "raw")
    assert (body["source"], body["fetched_ranges"], len(body["bars"])) == ("fake:test", 1, 5)
    assert body["bars"][0] == {
        "ts": "2024-01-02T05:00:00+00:00",
        "open": "100.12500000",
        "high": "100.12500000",
        "low": "100.12500000",
        "close": "100.12500000",
        "volume": "1234.50000000",
        "trade_count": 5,
        "vwap": "100.12500000",
    }


def test_api_maps_provider_failure_to_bad_gateway(api, provider):
    provider.fail = True
    api.app.state.market_data = MarketDataService(provider)
    response = api.get(
        "/api/v1/market/XYZ/bars",
        params={"start": "2024-01-02T00:00:00Z", "end": "2024-01-09T00:00:00Z"},
        headers=AUTH,
    )
    assert response.status_code == 502 and "provider is down" in response.json()["detail"]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/market/XYZ/bars", {"timeframe": "2d"}),
        ("/api/v1/market/XYZ/bars", {"adjustment": "magic"}),
        ("/api/v1/market/XYZ/bars", {"start": "2024-01-02T00:00:00"}),
        (
            "/api/v1/market/XYZ/bars",
            {"start": "2024-01-09T00:00:00Z", "end": "2024-01-02T00:00:00Z"},
        ),
        ("/api/v1/market/X$Z/bars", {}),
        ("/api/v1/market/TOOLONGSYMBOL/quote", {}),
    ],
)
def test_api_validates_input(api, provider, path, params):
    api.app.state.market_data = MarketDataService(provider)
    assert api.get(path, params=params, headers=AUTH).status_code == 422
    assert provider.calls == []


def test_api_requires_token(api):
    assert api.get("/api/v1/market/AAPL/bars").status_code == 401
