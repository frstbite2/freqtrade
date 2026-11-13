"""Technical indicators on a price frame.

Standard indicators come from TA-Lib, the reference implementation. A value that cannot be
computed yet (not enough history) is NaN, never zero. Smoothed indicators (RSI, EMA, ATR, ADX)
depend on how much history precedes them: give them a few hundred bars before trusting a value.

Prices are converted from exact decimals to floats here. That is fine for analysis; stored
prices and money calculations elsewhere stay exact.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
import talib

from backend.services.market_data.base import TIMEFRAMES, Bar


EMA_PERIODS = (9, 21, 50, 100, 200)
SMA_PERIODS = (20, 50, 100, 200)
SESSION_ZONE = "America/New_York"
# Bars per year, for annualising volatility. US equities: 252 sessions of 6.5 hours.
BARS_PER_YEAR = {"1m": 252 * 390, "5m": 252 * 78, "15m": 252 * 26, "1h": 252 * 7, "4h": 252 * 2,
                 "1d": 252, "1w": 52}  # fmt: skip
FIBONACCI_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)


def to_frame(bars: list[Bar]) -> pd.DataFrame:
    """Bars as a float frame indexed by bar start (UTC), oldest first."""
    frame = pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
        },
        index=pd.DatetimeIndex([b.ts for b in bars], name="ts"),
    )
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("bars must be unique and in chronological order")
    return frame


def add_indicators(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """A copy of `frame` with indicator columns. Every value uses only that bar and earlier ones."""
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {timeframe!r}")
    df = frame.copy()
    h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close", "volume"))  # noqa: E741

    df["rsi_14"] = talib.RSI(c, 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = talib.MACD(c, 12, 26, 9)
    for n in EMA_PERIODS:
        df[f"ema_{n}"] = talib.EMA(c, n)
    for n in SMA_PERIODS:
        df[f"sma_{n}"] = talib.SMA(c, n)
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = talib.BBANDS(c, 20, 2.0, 2.0)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["atr_14"] = talib.ATR(h, l, c, 14)
    df["adx_14"] = talib.ADX(h, l, c, 14)
    df["plus_di_14"] = talib.PLUS_DI(h, l, c, 14)
    df["minus_di_14"] = talib.MINUS_DI(h, l, c, 14)
    df["obv"] = talib.OBV(c, v)
    df["mfi_14"] = talib.MFI(h, l, c, v, 14)

    df["avg_volume_20"] = df["volume"].rolling(20).mean()
    # Compared with the 20 bars *before* this one, so a spike is not diluted by itself.
    df["rel_volume"] = df["volume"] / df["avg_volume_20"].shift(1).where(lambda s: s > 0)
    returns = np.log(df["close"] / df["close"].shift(1))
    df["hist_vol_20"] = returns.rolling(20).std() * np.sqrt(BARS_PER_YEAR[timeframe])

    typical = (df["high"] + df["low"] + df["close"]) / 3
    if TIMEFRAMES[timeframe] < timedelta(days=1):
        # VWAP restarts each trading day (US Eastern calendar date).
        session = df.index.tz_convert(SESSION_ZONE).date
        traded = df["volume"].groupby(session).cumsum()
        df["vwap"] = (typical * df["volume"]).groupby(session).cumsum() / traded.where(traded > 0)
    else:
        df["vwap"] = np.nan  # a session VWAP has no meaning on daily or weekly bars
    return df


def fibonacci_levels(low: float, high: float, direction: str) -> dict[str, float]:
    """Retracement levels of a move from low to high ("up") or high to low ("down")."""
    if not low < high:
        raise ValueError("low must be below high")
    if direction not in ("up", "down"):
        raise ValueError("direction must be 'up' or 'down'")
    span = high - low
    return {
        f"{ratio:.3f}": (high - ratio * span) if direction == "up" else (low + ratio * span)
        for ratio in FIBONACCI_RATIOS
    }


def volume_profile(frame: pd.DataFrame, bins: int = 24, value_area: float = 0.70) -> dict | None:
    """Volume by price over the frame, with the point of control and the value area.

    shortcut: each bar's volume is spread evenly over its high-low range, the usual approximation
    from bars; a profile built from trades would be exact.
    """
    low, high = float(frame["low"].min()), float(frame["high"].max())
    total = float(frame["volume"].sum())
    if not (len(frame) and high > low and total > 0):
        return None
    edges = np.linspace(low, high, bins + 1)
    volume = np.zeros(bins)
    for bar_low, bar_high, bar_volume in zip(
        frame["low"], frame["high"], frame["volume"], strict=True
    ):
        if bar_high == bar_low:
            volume[min(np.searchsorted(edges, bar_low, side="right") - 1, bins - 1)] += bar_volume
            continue
        overlap = np.clip(
            np.minimum(edges[1:], bar_high) - np.maximum(edges[:-1], bar_low), 0, None
        )
        volume += bar_volume * overlap / (bar_high - bar_low)
    poc = int(volume.argmax())
    lo = hi = poc
    inside = volume[poc]
    while inside < value_area * total and (lo > 0 or hi < bins - 1):
        below = volume[lo - 1] if lo > 0 else -1.0
        above = volume[hi + 1] if hi < bins - 1 else -1.0
        if above >= below:
            hi += 1
            inside += above
        else:
            lo -= 1
            inside += below
    return {
        "point_of_control": float((edges[poc] + edges[poc + 1]) / 2),
        "value_area_low": float(edges[lo]),
        "value_area_high": float(edges[hi + 1]),
        "bins": [
            {"low": float(edges[i]), "high": float(edges[i + 1]), "volume": float(volume[i])}
            for i in range(bins)
        ],
    }
