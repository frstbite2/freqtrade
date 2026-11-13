"""Candlestick pattern recognition.

Textbook patterns use TA-Lib's recognisers; inside bars and pin bars are defined here. A pattern
alone is weak evidence, so confidence starts low and rises only with context: the pattern
appearing after a move it would reverse, and unusual volume.
"""

import numpy as np
import pandas as pd
import talib

from backend.services.technical_analysis.detection import Detection, with_levels


# name -> (TA-Lib function, bars in the pattern, what it means)
_TALIB = {
    "engulfing": (talib.CDLENGULFING, 2, "a candle whose body engulfs the previous body"),
    "morning_star": (
        talib.CDLMORNINGSTAR,
        3,
        "a long down candle, a small one, then a strong up candle",
    ),
    "evening_star": (
        talib.CDLEVENINGSTAR,
        3,
        "a long up candle, a small one, then a strong down candle",
    ),
    "hammer": (talib.CDLHAMMER, 1, "a small body on a long lower shadow after a decline"),
    "shooting_star": (
        talib.CDLSHOOTINGSTAR,
        1,
        "a small body under a long upper shadow after a rise",
    ),
    "doji": (talib.CDLDOJI, 1, "open and close nearly equal: indecision"),
    "three_white_soldiers": (talib.CDL3WHITESOLDIERS, 3, "three strong up candles in a row"),
    "three_black_crows": (talib.CDL3BLACKCROWS, 3, "three strong down candles in a row"),
}
_NEUTRAL = {"doji", "inside_bar"}
PRIOR_MOVE_BARS = 5


def _bar_shape_hits(o, h, l, c) -> list[tuple[int, str, int, int, str]]:  # noqa: E741
    """Inside bars and pin bars, which TA-Lib does not define."""
    hits = []
    span = h - l
    body_top, body_bottom = np.maximum(o, c), np.minimum(o, c)
    for i in range(1, len(o)):
        if h[i] < h[i - 1] and l[i] > l[i - 1]:
            hits.append(
                (i, "inside_bar", 0, 2, "the whole candle sits inside the previous candle's range")
            )
        if span[i] <= 0:
            continue
        lower, upper = (body_bottom[i] - l[i]) / span[i], (h[i] - body_top[i]) / span[i]
        if 1 - lower - upper <= 1 / 3 and lower >= 2 / 3:
            hits.append((i, "pin_bar", 1, 1, "a long lower wick rejected lower prices"))
        elif 1 - lower - upper <= 1 / 3 and upper >= 2 / 3:
            hits.append((i, "pin_bar", -1, 1, "a long upper wick rejected higher prices"))
    return hits


def detect_candlesticks(df: pd.DataFrame) -> list[Detection]:
    """`df` must carry indicator columns (atr_14, rel_volume)."""
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))  # noqa: E741
    hits: list[tuple[int, str, int, int, str]] = []  # bar, name, sign, bars in pattern, meaning
    for name, (function, bars, meaning) in _TALIB.items():
        signal = function(o, h, l, c)
        hits += [
            (i, name, int(signal[i] > 0) - int(signal[i] < 0), bars, meaning)
            for i in signal.nonzero()[0]
        ]

    hits += _bar_shape_hits(o, h, l, c)

    # One candle, one name: a hammer is also a pin bar, and both have a doji-sized body.
    specific = {(i, sign) for i, name, sign, *_ in hits if name in ("hammer", "shooting_star")}
    one_sided = {i for i, name, *_ in hits if name in ("hammer", "shooting_star", "pin_bar")}
    hits = [
        hit
        for hit in hits
        if not (hit[1] == "pin_bar" and (hit[0], hit[2]) in specific)
        and not (hit[1] == "doji" and hit[0] in one_sided)
    ]

    detections = []
    for i, name, sign, bars, meaning in sorted(hits):
        direction = "neutral" if name in _NEUTRAL else "bullish" if sign > 0 else "bearish"
        confidence, notes = 0.4, [meaning]
        if direction != "neutral" and i >= PRIOR_MOVE_BARS:
            prior = (
                c[i - bars] - c[i - bars - PRIOR_MOVE_BARS] if i - bars >= PRIOR_MOVE_BARS else 0.0
            )
            if prior * sign < 0:  # these are reversal patterns: there must be a move to reverse
                confidence += 0.15
                notes.append(f"it follows a {'decline' if sign > 0 else 'rise'}")
        rel_volume = df["rel_volume"].iloc[i]
        if rel_volume >= 1.5:
            confidence += 0.15
            notes.append(f"volume was {rel_volume:.1f}x the 20-bar average")
        detection = Detection(
            name=name,
            kind="candlestick",
            direction=direction,
            detected_at=df.index[i].to_pydatetime(),
            confidence=round(confidence, 2),
            explanation="; ".join(notes).capitalize() + ".",
        )
        atr = df["atr_14"].iloc[i]
        if direction != "neutral" and not np.isnan(atr):  # levels need a volatility estimate
            low, high = l[i - bars + 1 : i + 1].min(), h[i - bars + 1 : i + 1].max()
            if sign > 0:
                with_levels(detection, entry=float(high), stop=float(low - 0.25 * atr))
            else:
                with_levels(detection, entry=float(low), stop=float(high + 0.25 * atr))
        detections.append(detection)
    return detections
