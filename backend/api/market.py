"""Market data endpoints."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from backend.api.routes import require_token
from backend.services.market_data.base import (
    ADJUSTMENTS,
    TIMEFRAMES,
    MarketDataError,
    ProviderNotConfigured,
)


router = APIRouter(prefix="/api/v1/market", dependencies=[Depends(require_token)])

Symbol = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")]
Timeframe = Literal[tuple(TIMEFRAMES)]  # type: ignore[valid-type]
Adjustment = Literal[ADJUSTMENTS]  # type: ignore[valid-type]


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ProviderNotConfigured as exc:
        # Unavailable is reported as such; it must never look like "no trading".
        raise HTTPException(503, str(exc)) from exc
    except MarketDataError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _aware(name: str, value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(422, f"{name} must include a UTC offset, e.g. 2026-01-31T00:00:00Z")
    return value


@router.get("/{symbol}/bars")
def bars(
    request: Request,
    symbol: Symbol,
    timeframe: Timeframe = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    adjustment: Adjustment = "raw",
) -> dict:
    end = _aware("end", end) if end else datetime.now(UTC)
    start = _aware("start", start) if start else end - 100 * TIMEFRAMES[timeframe]
    with request.app.state.sessions() as session:
        result = _call(
            request.app.state.market_data.get_bars,
            session,
            symbol,
            timeframe,
            start,
            end,
            adjustment,
        )
    body = asdict(result)
    body["bars"] = [
        {
            "ts": bar.ts.isoformat(),
            "open": str(bar.open),
            "high": str(bar.high),
            "low": str(bar.low),
            "close": str(bar.close),
            "volume": str(bar.volume),
            "trade_count": bar.trade_count,
            "vwap": None if bar.vwap is None else str(bar.vwap),
        }
        for bar in result.bars
    ]
    return body


@router.get("/{symbol}/quote")
def quote(request: Request, symbol: Symbol) -> dict:
    return _call(request.app.state.market_data.get_latest_quote, symbol)
