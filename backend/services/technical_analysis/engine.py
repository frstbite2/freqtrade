"""Technical analysis of one symbol across timeframes.

UNVERIFIED ON REAL DATA: built while no price provider was verified, so every test of this
engine runs on constructed price series. The rules are standard definitions, but thresholds have
not been tuned or checked against real markets. See PROJECT_STATUS.md.

A detection on one timeframe is compared with the bias of the next higher timeframe, using only
higher-timeframe bars that had already closed at that moment.
"""

from dataclasses import asdict

import numpy as np
import pandas as pd

from backend.services.market_data.base import TIMEFRAMES, Bar
from backend.services.technical_analysis.candles import detect_candlesticks
from backend.services.technical_analysis.detection import Detection
from backend.services.technical_analysis.indicators import (
    add_indicators,
    fibonacci_levels,
    to_frame,
    volume_profile,
)
from backend.services.technical_analysis.patterns import detect_chart_patterns
from backend.services.technical_analysis.structure import (
    detect_breaks,
    detect_exhaustion,
    detect_gaps_and_zones,
    detect_squeeze_and_expansion,
    find_swings,
    open_fair_value_gaps,
    support_resistance,
    trend_from_swings,
    zigzag,
)


MIN_BARS = 60  # below this, most indicators have no value yet
DISCLAIMER = (
    "Rule-based pattern matches, not predictions. Confidence measures how cleanly the rules were "
    "met, not the chance of profit. Not yet verified on real market data."
)


def bias_series(df: pd.DataFrame) -> pd.Series:
    """Per bar: +1 bullish, -1 bearish, 0 neutral, NaN when too little history.

    The average of four votes (price above the 21 EMA, 21 above 50, 50 above 200, MACD histogram
    positive), counting only those that can be computed; at least +/-0.5 makes a bias.
    """
    votes = pd.concat(
        [
            np.sign(df["close"] - df["ema_21"]),
            np.sign(df["ema_21"] - df["ema_50"]),
            np.sign(df["ema_50"] - df["ema_200"]),
            np.sign(df["macd_hist"]),
        ],
        axis=1,
    )
    score = votes.mean(axis=1).where(votes.notna().sum(axis=1) >= 2)
    return score.apply(lambda s: s if np.isnan(s) else float(s >= 0.5) - float(s <= -0.5))


def _bias_word(value: float) -> str:
    return (
        "unavailable"
        if np.isnan(value)
        else {1.0: "bullish", -1.0: "bearish"}.get(value, "neutral")
    )


def detect_all(df: pd.DataFrame) -> list[Detection]:
    """Every detector on an indicator frame, oldest detection first."""
    swings = find_swings(df)
    detections = [
        *detect_candlesticks(df),
        *detect_chart_patterns(df, swings),
        *detect_breaks(df, swings),
        *detect_gaps_and_zones(df),
        *detect_squeeze_and_expansion(df),
        *detect_exhaustion(df, swings),
    ]
    return sorted(detections, key=lambda d: (d.detected_at, d.kind, d.name, d.direction))


def analyze(
    symbol: str,
    bars_by_timeframe: dict[str, list[Bar]],
    recent_bars: int = 30,
    min_confidence: float = 0.0,
) -> dict:
    """Indicators, levels and the detections of the last `recent_bars` bars per timeframe.

    `min_confidence` drops weaker detections after the higher-timeframe adjustment."""
    frames, biases, out = {}, {}, {}
    for timeframe in TIMEFRAMES:  # shortest first
        bars = bars_by_timeframe.get(timeframe)
        if bars is None:
            continue
        if len(bars) < MIN_BARS:
            out[timeframe] = {
                "status": "insufficient_data",
                "bars": len(bars),
                "detail": f"needs at least {MIN_BARS} bars",
            }
            continue
        frames[timeframe] = add_indicators(to_frame(bars), timeframe)
        # Indexed by the moment each bar closed, which is when its bias became known.
        bias = bias_series(frames[timeframe])
        biases[timeframe] = bias.set_axis(bias.index + TIMEFRAMES[timeframe])

    for timeframe, df in frames.items():
        higher = next(
            (t for t in list(TIMEFRAMES)[list(TIMEFRAMES).index(timeframe) + 1 :] if t in biases),
            None,
        )
        detections = [
            d for d in detect_all(df) if d.detected_at >= df.index[-min(recent_bars, len(df))]
        ]
        for d in detections:
            d.symbol, d.timeframe = symbol, timeframe
            if higher is None or d.direction == "neutral":
                continue
            closed = pd.Timestamp(d.detected_at) + TIMEFRAMES[timeframe]
            known = biases[higher].loc[:closed]
            value = known.iloc[-1] if len(known) else np.nan
            agrees = (
                None
                if np.isnan(value) or value == 0
                else bool((value > 0) == (d.direction == "bullish"))
            )
            d.higher_timeframe = {"timeframe": higher, "bias": _bias_word(value), "agrees": agrees}
            if agrees is not None:
                d.confidence = round(
                    min(0.95, max(0.05, d.confidence + (0.1 if agrees else -0.15))), 2
                )
                verb = "agrees" if agrees else "disagrees"
                d.explanation += f" The {higher} trend {verb} ({_bias_word(value)})."

        swings = find_swings(df)
        path = zigzag(swings)
        last = df.iloc[-1]
        out[timeframe] = {
            "status": "ok",
            "bars": len(df),
            "last_bar": df.index[-1].isoformat(),
            "bias": _bias_word(bias_series(df).iloc[-1]),
            "structure": trend_from_swings(swings),
            "indicators": {
                k: None if pd.isna(v) else round(float(v), 6)
                for k, v in last.items()
                if k not in ("open", "high", "low", "close", "volume")
            },
            "levels": {
                "support_resistance": support_resistance(df, swings),
                "fibonacci": _fibonacci(path),
                "volume_profile": volume_profile(df.iloc[-120:]),
                "open_fair_value_gaps": open_fair_value_gaps(df)[-10:],
            },
            "detections": [
                asdict(d) | {"detected_at": d.detected_at.isoformat()}
                for d in detections
                if d.confidence >= min_confidence
            ],
        }
    return {"symbol": symbol, "timeframes": out, "disclaimer": DISCLAIMER}


def _fibonacci(path: list) -> dict | None:
    """Retracement levels of the latest swing leg."""
    if len(path) < 2 or path[-1].price == path[-2].price:
        return None
    start, end = path[-2], path[-1]
    up = end.kind == "high"
    low, high = (start.price, end.price) if up else (end.price, start.price)
    return {
        "from": start.price,
        "to": end.price,
        "levels": fibonacci_levels(low, high, "up" if up else "down"),
    }
