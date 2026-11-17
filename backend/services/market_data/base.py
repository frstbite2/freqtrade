"""Provider-neutral market data types and the interface every provider adapter implements."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol


# The platform's timeframes and the length of one bar.
TIMEFRAMES: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}
ADJUSTMENTS = ("raw", "split", "dividend", "all")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class MarketDataError(Exception):
    """The provider failed or returned something unusable."""


class ProviderNotConfigured(MarketDataError):
    """No credentials: prices are unavailable, which is not the same as 'no trading'."""


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    ts: datetime  # UTC, start of the bar
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int | None
    vwap: Decimal | None


@dataclass(frozen=True)
class Quote:
    symbol: str
    ts: datetime  # UTC, when the quote was made
    bid_price: Decimal
    bid_size: Decimal
    ask_price: Decimal
    ask_size: Decimal


class MarketDataProvider(Protocol):
    name: str
    feed: str  # which venue(s) the prices and volumes come from

    def get_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime, adjustment: str
    ) -> list[Bar]:
        """Bars with start <= ts < end, oldest first."""
        ...

    def get_latest_quote(self, symbol: str) -> Quote: ...


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not _SYMBOL.match(symbol):
        raise ValueError(f"invalid symbol {symbol!r}")
    return symbol


def check_request(timeframe: str, start: datetime, end: datetime, adjustment: str) -> None:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {timeframe!r}; use one of {list(TIMEFRAMES)}")
    if adjustment not in ADJUSTMENTS:
        raise ValueError(f"unsupported adjustment {adjustment!r}; use one of {ADJUSTMENTS}")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start >= end:
        raise ValueError("start must be before end")
