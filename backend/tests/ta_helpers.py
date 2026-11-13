"""Constructed price series for technical-analysis tests. None of this is market data."""

import numpy as np
import pandas as pd

from backend.services.technical_analysis.indicators import add_indicators


def frame(
    closes, wick=0.3, volume=1000.0, opens=None, freq="B", start="2022-01-03 05:00"
) -> pd.DataFrame:
    """Bars whose open is the previous close, with a fixed wick on both ends."""
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, dtype=float)
    volumes = (
        np.full(len(closes), float(volume))
        if np.isscalar(volume)
        else np.asarray(volume, dtype=float)
    )
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + wick,
            "low": np.minimum(opens, closes) - wick,
            "close": closes,
            "volume": volumes,
        },
        index=pd.date_range(start, periods=len(closes), freq=freq, tz="UTC", name="ts"),
    )


def path(start: float, *legs: tuple[int, float]) -> np.ndarray:
    """Closes moving in straight legs: path(100, (10, 120), (5, 110)) rises to 120 in 10 bars."""
    closes, price = [start], start
    for bars, target in legs:
        closes += list(np.linspace(price, target, bars + 1)[1:])
        price = target
    return np.array(closes)


def analysed(closes, timeframe="1d", **kwargs) -> pd.DataFrame:
    return add_indicators(frame(closes, **kwargs), timeframe)


def ohlc(rows, volume=1000.0, freq="B") -> pd.DataFrame:
    """Bars from explicit (open, high, low, close) rows."""
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows, strict=True))  # noqa: E741
    volumes = (
        np.full(len(c), float(volume)) if np.isscalar(volume) else np.asarray(volume, dtype=float)
    )
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": volumes},
        index=pd.date_range("2022-01-03 05:00", periods=len(c), freq=freq, tz="UTC", name="ts"),
    )
