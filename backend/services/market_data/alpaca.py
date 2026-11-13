"""Alpaca Market Data API v2 adapter (US stocks).

LIVE VERIFICATION PENDING: this adapter has not yet been run against Alpaca, because no API
keys were available when it was written. Endpoints, parameters, field names and timeframe
limits follow Alpaca's official Python SDK (alpaca-py 0.45.0, read from PyPI). Behaviour the SDK
does not state is handled defensively and listed in PROJECT_STATUS.md as unverified.
"""

import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from backend.core.http import RetriesExhausted, Throttle, get_with_retry
from backend.services.market_data.base import (
    Bar,
    MarketDataError,
    ProviderNotConfigured,
    Quote,
    check_request,
    normalize_symbol,
)


logger = logging.getLogger(__name__)

BASE_URL = "https://data.alpaca.markets"
PAGE_LIMIT = 10_000  # most items Alpaca returns per request
MAX_PAGES = 500
FEEDS = ("iex", "sip", "delayed_sip")
_TIMEFRAME = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
    "1w": "1Week",
}
_FRACTION = re.compile(r"(\.\d{6})\d+")  # Alpaca sends nanoseconds; Python keeps microseconds


def _timestamp(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError(f"timestamp is not a string: {raw!r}")
    parsed = datetime.fromisoformat(_FRACTION.sub(r"\1", raw))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {raw!r}")
    return parsed.astimezone(UTC)


def _number(item: dict, key: str, required: bool = True) -> Decimal | None:
    raw = item.get(key)
    if raw is None and not required:
        return None
    # bool is an int in Python; a true/false here would be a malformed payload.
    if isinstance(raw, bool) or not isinstance(raw, int | Decimal):
        raise ValueError(f"field {key!r} is not a number: {raw!r}")
    return Decimal(raw)


class AlpacaMarketData:
    name = "alpaca"

    def __init__(
        self,
        api_key: str | None,
        secret_key: str | None,
        feed: str = "iex",
        min_interval: float = 0.35,  # about 170 requests/minute
        max_attempts: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise ProviderNotConfigured("ALPACA_API_KEY and ALPACA_SECRET_KEY are not set")
        if feed not in FEEDS:
            raise ValueError(f"unsupported Alpaca feed {feed!r}; use one of {FEEDS}")
        self.feed = feed
        self._http = httpx.Client(
            headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
            timeout=30,
            transport=transport,
        )
        self._throttle = Throttle(min_interval)
        self._max_attempts = max_attempts

    @property
    def requests_made(self) -> int:
        return self._throttle.requests_made

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict) -> dict:
        url = f"{BASE_URL}{path}"
        try:
            response = get_with_retry(
                self._http, url, self._throttle, params=params, max_attempts=self._max_attempts
            )
        except RetriesExhausted as exc:
            raise MarketDataError(f"Alpaca: {exc}") from exc
        if response.status_code != 200:
            raise MarketDataError(
                f"Alpaca answered {response.status_code} for {path}: {_message(response)}"
                + (
                    " (check the API keys and that the plan includes this feed)"
                    if response.status_code in (401, 403)
                    else ""
                )
            )
        try:
            # Decimal keeps prices exactly as sent instead of rounding through binary floats.
            body = json.loads(response.content, parse_float=Decimal)
        except ValueError as exc:
            raise MarketDataError(f"Alpaca sent invalid JSON for {path}") from exc
        if not isinstance(body, dict):
            raise MarketDataError(f"Alpaca sent an unexpected response for {path}")
        return body

    def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime, adjustment: str = "raw"
    ) -> list[Bar]:
        symbol = normalize_symbol(symbol)
        check_request(timeframe, start, end, adjustment)
        params = {
            "symbols": symbol,
            "timeframe": _TIMEFRAME[timeframe],
            "start": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "limit": PAGE_LIMIT,
            "adjustment": adjustment,
            "feed": self.feed,
            "sort": "asc",
        }
        bars: list[Bar] = []
        tokens: set[str] = set()
        for _ in range(MAX_PAGES):
            body = self._get("/v2/stocks/bars", params)
            by_symbol = body.get("bars")
            if by_symbol is None:  # null or absent when nothing matched
                by_symbol = {}
            if not isinstance(by_symbol, dict):
                raise MarketDataError("Alpaca: 'bars' is not an object keyed by symbol")
            raw_bars = by_symbol.get(symbol) or []
            if not isinstance(raw_bars, list):
                raise MarketDataError(f"Alpaca: bars for {symbol} are not a list")
            bars += [self._bar(symbol, timeframe, raw) for raw in raw_bars]
            token = body.get("next_page_token")
            if not token:
                # Alpaca's own bounds are not relied on: enforce start <= ts < end here.
                return [bar for bar in bars if start <= bar.ts < end]
            if not isinstance(token, str) or token in tokens:
                raise MarketDataError("Alpaca: pagination did not advance")
            tokens.add(token)
            params = {**params, "page_token": token}
        raise MarketDataError(f"Alpaca: more than {MAX_PAGES} pages for one request")

    @staticmethod
    def _bar(symbol: str, timeframe: str, raw: object) -> Bar:
        try:
            if not isinstance(raw, dict):
                raise ValueError(f"bar is not an object: {raw!r}")
            count = _number(raw, "n", required=False)
            if count is not None and count != count.to_integral_value():
                raise ValueError(f"trade count is not a whole number: {count}")
            return Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=_timestamp(raw.get("t")),
                open=_number(raw, "o"),
                high=_number(raw, "h"),
                low=_number(raw, "l"),
                close=_number(raw, "c"),
                volume=_number(raw, "v"),
                trade_count=None if count is None else int(count),
                vwap=_number(raw, "vw", required=False),
            )
        except ValueError as exc:
            raise MarketDataError(f"Alpaca sent a malformed bar for {symbol}: {exc}") from exc

    def get_latest_quote(self, symbol: str) -> Quote:
        symbol = normalize_symbol(symbol)
        body = self._get("/v2/stocks/quotes/latest", {"symbols": symbol, "feed": self.feed})
        quotes = body.get("quotes")
        raw = quotes.get(symbol) if isinstance(quotes, dict) else None
        if not isinstance(raw, dict):
            raise MarketDataError(f"Alpaca returned no quote for {symbol}")
        try:
            return Quote(
                symbol=symbol,
                ts=_timestamp(raw.get("t")),
                bid_price=_number(raw, "bp"),
                bid_size=_number(raw, "bs"),
                ask_price=_number(raw, "ap"),
                ask_size=_number(raw, "as"),
            )
        except ValueError as exc:
            raise MarketDataError(f"Alpaca sent a malformed quote for {symbol}: {exc}") from exc


def _message(response: httpx.Response) -> str:
    """Alpaca's error text, bounded, for an exception message."""
    try:
        body = response.json()
        text = body.get("message") if isinstance(body, dict) else None
    except ValueError:
        text = None
    return str(text or response.text or "no details")[:200]
