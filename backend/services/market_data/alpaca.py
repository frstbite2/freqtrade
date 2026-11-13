"""Alpaca market-data adapter (stocks bars API; no order placement)."""

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.services.market_data.cache import TTLCache
from backend.services.market_data.models import (
    Bar,
    ProviderConfigurationError,
    ProviderRequestError,
    decimal_value,
)


_BASE_URL = "https://data.alpaca.markets/v2"
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\\-]{0,14}$")
_ALLOWED_TIMEFRAMES = {"1Min", "5Min", "15Min", "30Min", "1Hour", "1Day", "1Week", "1Month"}


class AlpacaMarketDataClient:
    """Fetch and normalize historical stock bars from Alpaca's data API.

    This client only reads market data. It has no trading/order endpoints.
    Use the IEX feed by default; SIP access depends on the Alpaca subscription.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        *,
        feed: str = "iex",
        base_url: str = _BASE_URL,
        timeout_seconds: float = 10.0,
        max_pages: int = 20,
        cache: TTLCache[tuple[Bar, ...]] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.feed = feed
        self.base_url = base_url.rstrip("/")
        self.max_pages = max_pages
        self.cache = cache or TTLCache()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "APCA-API-KEY-ID": api_key or "",
                "APCA-API-SECRET-KEY": secret_key or "",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AlpacaMarketDataClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str = "1Day",
        start: datetime,
        end: datetime,
        limit: int = 1000,
        adjustment: str = "raw",
    ) -> list[Bar]:
        if not self.api_key or not self.secret_key:
            raise ProviderConfigurationError("Alpaca credentials are not configured")
        symbol = symbol.strip().upper()
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("symbol must be a valid US equity ticker")
        if timeframe not in _ALLOWED_TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if start >= end:
            raise ValueError("start must be earlier than end")
        if not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        if adjustment not in {"raw", "split", "dividend", "spin-off", "all"}:
            raise ValueError("unsupported adjustment")

        cache_key = "|".join((symbol, timeframe, start.isoformat(), end.isoformat(), str(limit), adjustment, self.feed))
        cached = self.cache.get(cache_key)
        if cached is not None:
            return list(cached)

        bars: list[Bar] = []
        page_token: str | None = None
        for _ in range(self.max_pages):
            params: dict[str, Any] = {
                "timeframe": timeframe,
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": limit,
                "adjustment": adjustment,
                "feed": self.feed,
                "sort": "asc",
            }
            if page_token:
                params["page_token"] = page_token
            try:
                response = self._client.get(f"/stocks/{symbol}/bars", params=params)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                raise ProviderRequestError(f"Alpaca market-data request failed (HTTP {status})") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderRequestError("Alpaca market-data request failed") from exc

            raw_bars = payload.get("bars") if isinstance(payload, dict) else None
            if not isinstance(raw_bars, list):
                raise ProviderRequestError("Alpaca returned an invalid bars payload")
            for raw in raw_bars:
                if not isinstance(raw, dict):
                    raise ProviderRequestError("Alpaca returned an invalid bar record")
                try:
                    timestamp = datetime.fromisoformat(str(raw["t"]).replace("Z", "+00:00"))
                    bar = Bar(
                        symbol=symbol,
                        timestamp=timestamp,
                        open=decimal_value(raw["o"], "open"),
                        high=decimal_value(raw["h"], "high"),
                        low=decimal_value(raw["l"], "low"),
                        close=decimal_value(raw["c"], "close"),
                        volume=decimal_value(raw["v"], "volume"),
                        trade_count=int(raw["n"]) if raw.get("n") is not None else None,
                        vwap=decimal_value(raw["vw"], "vwap") if raw.get("vw") is not None else None,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ProviderRequestError("Alpaca returned a malformed or invalid bar") from exc
                bars.append(bar)

            next_token = payload.get("next_page_token")
            if not next_token:
                break
            if not isinstance(next_token, str) or next_token == page_token:
                raise ProviderRequestError("Alpaca returned an invalid pagination token")
            page_token = next_token
        else:
            raise ProviderRequestError(f"Alpaca pagination exceeded the {self.max_pages}-page safety limit")

        bars.sort(key=lambda item: item.timestamp)
        result = tuple(bars)
        self.cache.set(cache_key, result)
        return list(result)
