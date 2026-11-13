"""Mocked tests for the Alpaca market-data adapter; no API key or network required."""

from datetime import UTC, datetime

import httpx
import pytest

from backend.services.market_data.alpaca import AlpacaMarketDataClient
from backend.services.market_data.cache import TTLCache
from backend.services.market_data.models import ProviderConfigurationError, ProviderRequestError


START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 3, tzinfo=UTC)


def bar(timestamp: str = "2026-01-02T00:00:00Z") -> dict:
    return {"t": timestamp, "o": "100.10", "h": "105.00", "l": "99.50", "c": "103.25", "v": "1200", "n": 42, "vw": "102.40"}


def client(handler, **kwargs):
    return AlpacaMarketDataClient(
        "test-key", "test-secret", transport=httpx.MockTransport(handler), **kwargs
    )


def test_normalizes_bars_and_uses_iex_feed():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        assert request.headers["APCA-API-KEY-ID"] == "test-key"
        return httpx.Response(200, json={"bars": [bar()], "next_page_token": None})

    with client(handler) as api:
        result = api.get_bars("aapl", start=START, end=END)
    assert len(result) == 1
    assert result[0].symbol == "AAPL"
    assert result[0].timestamp == datetime(2026, 1, 2, tzinfo=UTC)
    assert str(result[0].close) == "103.25"
    assert seen["feed"] == "iex"
    assert seen["sort"] == "asc"


def test_missing_credentials_fails_closed():
    api = AlpacaMarketDataClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ProviderConfigurationError):
        api.get_bars("AAPL", start=START, end=END)
    api.close()


def test_paginates_and_caches_complete_result():
    calls = []

    def handler(request):
        calls.append(request.url.params.get("page_token"))
        if len(calls) == 1:
            return httpx.Response(200, json={"bars": [bar("2026-01-01T00:00:00Z")], "next_page_token": "next"})
        return httpx.Response(200, json={"bars": [bar("2026-01-02T00:00:00Z")], "next_page_token": None})

    with client(handler) as api:
        first = api.get_bars("AAPL", start=START, end=END)
        second = api.get_bars("AAPL", start=START, end=END)
    assert len(first) == len(second) == 2
    assert calls == [None, "next"]


def test_rejects_invalid_ohlc_integrity():
    invalid = bar()
    invalid["h"] = "90"
    with client(lambda r: httpx.Response(200, json={"bars": [invalid]})) as api:
        with pytest.raises(ProviderRequestError, match="invalid bar"):
            api.get_bars("AAPL", start=START, end=END)


def test_provider_http_errors_do_not_expose_response_body():
    with client(lambda r: httpx.Response(403, text="sensitive provider response")) as api:
        with pytest.raises(ProviderRequestError, match="HTTP 403") as error:
            api.get_bars("AAPL", start=START, end=END)
    assert "sensitive" not in str(error.value)


def test_rejects_naive_dates_and_bad_symbols():
    with client(lambda r: httpx.Response(200, json={"bars": []})) as api:
        with pytest.raises(ValueError, match="timezone-aware"):
            api.get_bars("AAPL", start=datetime(2026, 1, 1), end=END)
        with pytest.raises(ValueError, match="ticker"):
            api.get_bars("AAPL/EVIL", start=START, end=END)


def test_ttl_cache_evicts_oldest_entry():
    cache = TTLCache[int](ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
