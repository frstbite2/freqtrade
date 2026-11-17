"""Technical analysis endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from backend.api.market import _call
from backend.api.routes import require_token
from backend.services.market_data.base import TIMEFRAMES
from backend.services.technical_analysis.engine import analyze


router = APIRouter(prefix="/api/v1/technical", dependencies=[Depends(require_token)])

Symbol = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")]

# Calendar span fetched per timeframe: enough for about 300+ bars, so a 200-period average
# has history behind it, given that US stocks trade 6.5 hours a day, 5 days a week.
LOOKBACK = {
    "1m": timedelta(days=5),
    "5m": timedelta(days=10),
    "15m": timedelta(days=25),
    "1h": timedelta(days=90),
    "4h": timedelta(days=290),
    "1d": timedelta(days=580),
    "1w": timedelta(days=2800),
}


def _timeframes(raw: str) -> list[str]:
    names = raw.split(",")
    if not raw or any(n not in TIMEFRAMES for n in names) or len(set(names)) != len(names):
        raise HTTPException(
            422, f"timeframes must be distinct, comma-separated values from {list(TIMEFRAMES)}"
        )
    return names


@router.get("/{symbol}")
def technical(
    request: Request,
    symbol: Symbol,
    timeframes: str = "1d,1w",
    # 0.5 hides bare candlesticks and minor structure events (gaps, imbalances, zones).
    min_confidence: Annotated[float, Query(ge=0, le=1)] = 0.5,
) -> dict:
    wanted = _timeframes(timeframes)
    service = request.app.state.market_data
    end = datetime.now(UTC)
    bars, data_quality = {}, {}
    with request.app.state.sessions() as session:
        for timeframe in wanted:
            # Split-adjusted, so a split does not look like a crash to the pattern detectors.
            result = _call(
                service.get_bars,
                session,
                symbol,
                timeframe,
                end - LOOKBACK[timeframe],
                end,
                "split",
            )
            bars[timeframe] = result.bars
            data_quality[timeframe] = {
                "rejected_bars": len(result.rejected),
                "warnings": result.warnings,
            }
    body = analyze(symbol.upper(), bars, min_confidence=min_confidence)
    return body | {"source": service.source, "adjustment": "split", "data_quality": data_quality}
