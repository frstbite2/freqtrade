"""Market structure: swings, trend, breaks, levels, gaps, sweeps, zones, squeeze, exhaustion.

Everything is built on confirmed swing points. A swing high is a bar whose high is the highest of
the SWING_BARS bars on each side, so it is only known SWING_BARS bars later. Each event is dated
at the bar that completed it and never uses a later bar.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.services.technical_analysis.detection import Detection


SWING_BARS = 3


@dataclass(frozen=True)
class Swing:
    i: int  # bar position of the extreme
    price: float
    kind: str  # "high" | "low"
    confirmed: int  # bar position at which it became known
    label: str = ""  # HH, LH, HL, LL once compared with the previous swing of its kind


def find_swings(df: pd.DataFrame, k: int = SWING_BARS) -> list[Swing]:
    """Swing highs and lows in the order they became known, each labelled against the previous
    swing of its kind. Later bars never change an earlier swing."""
    high, low = df["high"].to_numpy(dtype=float), df["low"].to_numpy(dtype=float)
    swings, last = [], {}
    for i in range(k, len(df) - k):
        for kind, series, pick in (("high", high, max), ("low", low, min)):
            window = series[i - k : i + k + 1]
            # The extreme of its window, and strictly beyond everything before it in the window.
            if series[i] != pick(window) or series[i] == pick(series[i - k : i]):
                continue
            previous, label = last.get(kind), ""
            if previous is not None:
                higher = series[i] > previous.price
                label = ("HH" if higher else "LH") if kind == "high" else ("HL" if higher else "LL")
            last[kind] = Swing(i, float(series[i]), kind, i + k, label)
            swings.append(last[kind])
    return swings


def zigzag(swings: list[Swing]) -> list[Swing]:
    """`swings` reduced to alternating highs and lows: of several highs with no low between
    them, the highest is kept. Call it only with the swings known at the moment of interest."""
    path: list[Swing] = []
    for swing in sorted(swings, key=lambda s: s.i):
        if path and path[-1].kind == swing.kind:
            beats = (
                swing.price > path[-1].price
                if swing.kind == "high"
                else swing.price < path[-1].price
            )
            if beats:
                path[-1] = swing
        else:
            path.append(swing)
    return path


def trend_from_swings(swings: list[Swing]) -> str:
    """ "up" (higher highs and higher lows), "down", or "range", from the two latest labels."""
    labels = {s.kind: s.label for s in swings if s.label}
    if labels.get("high") == "HH" and labels.get("low") == "HL":
        return "up"
    if labels.get("high") == "LH" and labels.get("low") == "LL":
        return "down"
    return "range"


def _at(df: pd.DataFrame, i: int):
    return df.index[i].to_pydatetime()


def _event(df, i, name, direction, confidence, explanation, zone=None) -> Detection:
    zone = None if zone is None else (float(zone[0]), float(zone[1]))
    return Detection(name, "structure", direction, _at(df, i), confidence, explanation, zone=zone)


def detect_breaks(df: pd.DataFrame, swings: list[Swing]) -> list[Detection]:
    """Break of structure (trend continues), change of character (trend turns), liquidity sweeps
    (a level is pierced but the bar closes back inside) and the order block behind each break."""
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))  # noqa: E741
    events: list[Detection] = []
    trend = 0  # +1 up, -1 down, 0 not yet established
    levels: dict[str, Swing | None] = {
        "high": None,
        "low": None,
    }  # latest unbroken swing of each kind
    pending = sorted(swings, key=lambda s: s.confirmed)
    leg_start = 0
    swept: set[tuple[str, int]] = set()
    for j in range(len(df)):
        while pending and pending[0].confirmed <= j:
            swing = pending.pop(0)
            levels[swing.kind] = swing
        for kind, sign in (("high", 1), ("low", -1)):
            level = levels[kind]
            if level is None or level.i >= j:
                continue
            pierced = h[j] > level.price if sign > 0 else l[j] < level.price
            closed_beyond = c[j] > level.price if sign > 0 else c[j] < level.price
            side = "bullish" if sign > 0 else "bearish"
            if closed_beyond:
                turning = trend == -sign
                name = "change_of_character" if turning else "break_of_structure"
                events.append(
                    _event(
                        df,
                        j,
                        name,
                        side,
                        0.6 if turning else 0.5,
                        f"Close {c[j]:.2f} beyond the swing {kind} at {level.price:.2f}"
                        + (", against the prior trend." if turning else ", with the trend."),
                        zone=(min(level.price, c[j]), max(level.price, c[j])),
                    )
                )
                # Order block: the last candle against the move before price broke the level.
                against = [i for i in range(max(leg_start, level.i), j) if (c[i] - o[i]) * sign < 0]
                if against:
                    block = against[-1]
                    events.append(
                        _event(
                            df,
                            j,
                            "order_block",
                            side,
                            0.4,
                            f"Last {'down' if sign > 0 else 'up'} candle before the break, "
                            f"at {_at(df, block):%Y-%m-%d %H:%M}.",
                            zone=(l[block], h[block]),
                        )
                    )
                trend, levels[kind], leg_start = sign, None, j
            elif pierced and (kind, level.i) not in swept:
                events.append(
                    _event(
                        df,
                        j,
                        "liquidity_sweep",
                        "bearish" if sign > 0 else "bullish",
                        0.5,
                        f"Traded through the swing {kind} at {level.price:.2f} "
                        f"and closed back at {c[j]:.2f}.",
                        zone=(level.price, h[j]) if sign > 0 else (l[j], level.price),
                    )
                )
                swept.add((kind, level.i))  # report a level's sweep once; it can still break
    return events


def detect_gaps_and_zones(df: pd.DataFrame) -> list[Detection]:
    """Fair value gaps, volume imbalances, and supply/demand zones left by impulsive candles."""
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))  # noqa: E741
    atr = df["atr_14"].to_numpy(dtype=float)
    top, bottom = np.maximum(o, c), np.minimum(o, c)
    events = []
    for i in range(1, len(df)):
        if i >= 2 and l[i] > h[i - 2]:
            events.append(
                _event(
                    df,
                    i,
                    "fair_value_gap",
                    "bullish",
                    0.4,
                    "Three candles left untraded prices between the first high and the third low.",
                    zone=(h[i - 2], l[i]),
                )
            )
        elif i >= 2 and h[i] < l[i - 2]:
            events.append(
                _event(
                    df,
                    i,
                    "fair_value_gap",
                    "bearish",
                    0.4,
                    "Three candles left untraded prices between the first low and the third high.",
                    zone=(h[i], l[i - 2]),
                )
            )
        # Bodies do not overlap but wicks do: thin trading between the two closes.
        if bottom[i] > top[i - 1] and l[i] <= h[i - 1]:
            events.append(
                _event(
                    df,
                    i,
                    "volume_imbalance",
                    "bullish",
                    0.3,
                    "Candle bodies gapped up while the wicks overlapped.",
                    zone=(top[i - 1], bottom[i]),
                )
            )
        elif top[i] < bottom[i - 1] and h[i] >= l[i - 1]:
            events.append(
                _event(
                    df,
                    i,
                    "volume_imbalance",
                    "bearish",
                    0.3,
                    "Candle bodies gapped down while the wicks overlapped.",
                    zone=(top[i], bottom[i - 1]),
                )
            )
        body = c[i] - o[i]
        if not np.isnan(atr[i - 1]) and abs(body) >= 1.5 * atr[i - 1]:
            up = body > 0
            events.append(
                _event(
                    df,
                    i,
                    "demand_zone" if up else "supply_zone",
                    "bullish" if up else "bearish",
                    0.4,
                    f"A candle {abs(body) / atr[i - 1]:.1f}x the average range "
                    "left from the previous candle's area.",
                    zone=(l[i - 1], h[i - 1]),
                )
            )
    return events


def detect_squeeze_and_expansion(
    df: pd.DataFrame, lookback: int = 120, recent: int = 10
) -> list[Detection]:
    """Consolidation: Bollinger width in the lowest 15% of its own recent history.
    Expansion: a wide candle closing outside the bands within `recent` bars of a consolidation."""
    width = df["bb_width"]
    rank = width.rolling(lookback, min_periods=40).rank(pct=True)
    squeezed = (rank <= 0.15).to_numpy()
    c, h, l = (df[k].to_numpy(dtype=float) for k in ("close", "high", "low"))  # noqa: E741
    atr, upper, lower = (df[k].to_numpy(dtype=float) for k in ("atr_14", "bb_upper", "bb_lower"))
    events, last_squeeze, expanded = [], None, True
    for i in range(1, len(df)):
        if squeezed[i]:
            if not squeezed[i - 1]:
                events.append(
                    _event(
                        df,
                        i,
                        "consolidation",
                        "neutral",
                        0.5,
                        f"Bollinger band width is in the lowest 15% of the last {lookback} bars.",
                    )
                )
            last_squeeze, expanded = i, False
        if (
            not expanded
            and last_squeeze is not None
            and i - last_squeeze <= recent
            and not np.isnan(atr[i - 1])
            and h[i] - l[i] >= 1.5 * atr[i - 1]
        ):
            direction = "bullish" if c[i] > upper[i] else "bearish" if c[i] < lower[i] else None
            if direction:
                expanded = True
                events.append(
                    _event(
                        df,
                        i,
                        "expansion",
                        direction,
                        0.55,
                        "A wide candle closed outside the Bollinger bands "
                        "right after a consolidation.",
                    )
                )
    return events


def detect_exhaustion(df: pd.DataFrame, swings: list[Swing]) -> list[Detection]:
    """Momentum divergence: price makes a new extreme while RSI does not."""
    rsi = df["rsi_14"].to_numpy(dtype=float)
    events, previous = [], {}
    for swing in swings:
        before = previous.get(swing.kind)
        previous[swing.kind] = swing
        if before is None or np.isnan(rsi[swing.i]) or np.isnan(rsi[before.i]):
            continue
        if (
            swing.kind == "high"
            and swing.label == "HH"
            and rsi[swing.i] < rsi[before.i]
            and rsi[before.i] >= 60
        ):
            events.append(
                _event(
                    df,
                    swing.confirmed,
                    "trend_exhaustion",
                    "bearish",
                    0.5,
                    f"Higher high in price ({before.price:.2f} to {swing.price:.2f}) "
                    "with lower RSI "
                    f"({rsi[before.i]:.0f} to {rsi[swing.i]:.0f}).",
                    zone=(before.price, swing.price),
                )
            )
        if (
            swing.kind == "low"
            and swing.label == "LL"
            and rsi[swing.i] > rsi[before.i]
            and rsi[before.i] <= 40
        ):
            events.append(
                _event(
                    df,
                    swing.confirmed,
                    "trend_exhaustion",
                    "bullish",
                    0.5,
                    f"Lower low in price ({before.price:.2f} to {swing.price:.2f}) with higher RSI "
                    f"({rsi[before.i]:.0f} to {rsi[swing.i]:.0f}).",
                    zone=(swing.price, before.price),
                )
            )
    return events


def support_resistance(df: pd.DataFrame, swings: list[Swing], min_touches: int = 2) -> list[dict]:
    """Price levels where at least `min_touches` swings turned, as of the last bar."""
    atr = df["atr_14"].iloc[-1]
    close = float(df["close"].iloc[-1])
    tolerance = 0.5 * atr if not np.isnan(atr) else 0.005 * close
    levels: list[list[Swing]] = []
    for swing in sorted(swings, key=lambda s: s.price):
        if levels and swing.price - levels[-1][-1].price <= tolerance:
            levels[-1].append(swing)
        else:
            levels.append([swing])
    return [
        {
            "price": float(np.mean([s.price for s in group])),
            "kind": "support" if np.mean([s.price for s in group]) < close else "resistance",
            "touches": len(group),
            "last_touch": _at(df, max(s.i for s in group)).isoformat(),
        }
        for group in levels
        if len(group) >= min_touches
    ]


def open_fair_value_gaps(df: pd.DataFrame) -> list[dict]:
    """Fair value gaps that price has not traded back through, as of the last bar."""
    h, l = df["high"].to_numpy(dtype=float), df["low"].to_numpy(dtype=float)  # noqa: E741
    gaps = []
    for i in range(2, len(df)):
        if l[i] > h[i - 2] and l[i + 1 :].min(initial=np.inf) > h[i - 2]:
            gaps.append(
                {
                    "direction": "bullish",
                    "low": float(h[i - 2]),
                    "high": float(l[i]),
                    "since": _at(df, i).isoformat(),
                }
            )
        elif h[i] < l[i - 2] and h[i + 1 :].max(initial=-np.inf) < l[i - 2]:
            gaps.append(
                {
                    "direction": "bearish",
                    "low": float(h[i]),
                    "high": float(l[i - 2]),
                    "since": _at(df, i).isoformat(),
                }
            )
    return gaps
