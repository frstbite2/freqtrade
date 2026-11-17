"""Chart pattern recognition.

The detector walks the bars once, in order. At each bar it knows only the swings confirmed so
far. A swing can set up a pattern (two matching highs, a head between shoulders, a pole); the
pattern is reported at the bar whose close completes it (a neckline break, a breakout), or is
dropped if price invalidates it or time runs out. Triangles and wedges are reported when their
sixth swing confirms. Distances are measured in ATR so the rules scale with the instrument.

These are rule matches, not predictions; `confidence` says how cleanly the rules were met.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.services.technical_analysis.detection import Detection, with_levels
from backend.services.technical_analysis.structure import Swing, zigzag


MATCH = 0.75  # two extremes within this many ATR count as "the same level"
MIN_DEPTH = 2.0  # a reversal pattern must be at least this many ATR tall
POLE = 4.0  # a flag pole moves at least this many ATR ...
POLE_BARS = 15  # ... within this many bars
FLAG_RETRACE = 0.382  # and the pause gives back no more than this share of it
DONCHIAN = 20
CUP_BARS = (20, 150)


@dataclass
class _Setup:
    name: str
    sign: int  # +1 completes on a close above the line, -1 on a close below
    line: tuple[int, float, int, float]  # the trigger line, through two (bar, price) points
    invalid: float  # a close beyond this, against the pattern, cancels it
    expires: int
    height: float  # the measured move projected from the break
    stop: float | None  # stop reference; None: the extreme since `since`
    since: int
    confidence: float
    note: str
    key: tuple

    def level(self, j: int) -> float:
        i1, p1, i2, p2 = self.line
        return p1 if i1 == i2 else p1 + (p2 - p1) * (j - i1) / (i2 - i1)


def _reversal_setups(zz: list[Swing], atr: float, j: int) -> list[_Setup]:
    """Double/triple tops and bottoms and (inverse) head and shoulders ending at the last swing."""
    setups = []
    if len(zz) < 3:
        return setups
    last = zz[-1]
    sign = -1 if last.kind == "high" else 1  # a top completes downward
    side = "top" if sign < 0 else "bottom"

    def extreme(
        values,
    ):  # the far side of the pattern: highest high of a top, lowest low of a bottom
        return max(values) if sign < 0 else min(values)

    def neck(values):  # the side price must break: the lowest low under a top
        return min(values) if sign < 0 else max(values)

    a, mid, b = zz[-3], zz[-2], zz[-1]
    depth = abs(extreme([a.price, b.price]) - mid.price)
    if abs(a.price - b.price) <= MATCH * atr and depth >= MIN_DEPTH * atr and b.i - a.i >= 5:
        setups.append(
            _Setup(
                f"double_{side}",
                sign,
                (mid.i, mid.price, mid.i, mid.price),
                invalid=extreme([a.price, b.price]),
                expires=j + max(40, 2 * (b.i - a.i)),
                height=depth,
                stop=extreme([a.price, b.price]),
                since=b.i,
                confidence=round(0.5 + 0.2 * (1 - abs(a.price - b.price) / (MATCH * atr)), 2),
                note=f"two {'highs' if sign < 0 else 'lows'} at {a.price:.2f} and {b.price:.2f} "
                f"around {mid.price:.2f}",
                key=(f"double_{side}", a.i, b.i),
            )
        )
    if len(zz) >= 5:
        p1, n1, p2, n2, p3 = zz[-5:]
        peaks = [p1.price, p2.price, p3.price]
        neckline = neck([n1.price, n2.price])
        height = abs(extreme(peaks) - neckline)
        if max(peaks) - min(peaks) <= MATCH * atr and height >= MIN_DEPTH * atr:
            setups.append(
                _Setup(
                    f"triple_{side}",
                    sign,
                    (n1.i, neckline, n1.i, neckline),
                    invalid=extreme(peaks),
                    expires=j + max(40, p3.i - p1.i),
                    height=height,
                    stop=extreme(peaks),
                    since=p3.i,
                    confidence=0.6,
                    note=f"three {'highs' if sign < 0 else 'lows'} near {np.mean(peaks):.2f}",
                    key=(f"triple_{side}", p1.i, p3.i),
                )
            )
        head_beyond = (p2.price - max(p1.price, p3.price)) * -sign  # head clears both shoulders
        head_height = abs(p2.price - (n1.price + n2.price) / 2)
        # The head must clear the shoulders by more than MATCH, or it is a triple top instead.
        if (
            head_beyond > MATCH * atr
            and abs(p1.price - p3.price) <= 0.5 * head_height
            and head_height >= MIN_DEPTH * atr
        ):
            name = "head_and_shoulders" if sign < 0 else "inverse_head_and_shoulders"
            setups.append(
                _Setup(
                    name,
                    sign,
                    (n1.i, n1.price, n2.i, n2.price),
                    invalid=p2.price,
                    expires=j + max(40, p3.i - p1.i),
                    height=head_height,
                    stop=p3.price,
                    since=p3.i,
                    confidence=round(
                        0.55 + 0.15 * (1 - abs(p1.price - p3.price) / (0.5 * head_height)), 2
                    ),
                    note=f"head at {p2.price:.2f} between shoulders at {p1.price:.2f} "
                    f"and {p3.price:.2f}",
                    key=(name, p1.i, p3.i),
                )
            )
    return setups


def _flag_setup(zz: list[Swing], atr: float, j: int) -> _Setup | None:
    if len(zz) < 2:
        return None
    start, end = zz[-2], zz[-1]
    pole = abs(end.price - start.price)
    if pole < POLE * atr or end.i - start.i > POLE_BARS:
        return None
    sign = 1 if end.kind == "high" else -1  # a rally's flag breaks upward
    return _Setup(
        "bull_flag" if sign > 0 else "bear_flag",
        sign,
        (end.i, end.price, end.i, end.price),
        invalid=end.price - sign * FLAG_RETRACE * pole,
        expires=end.i + 25,
        height=pole,
        stop=None,
        since=end.i,
        confidence=0.5,
        note=f"a {pole / atr:.1f} ATR move in {end.i - start.i} bars, then a shallow pause",
        key=("flag", start.i, end.i),
    )


def _converging(df: pd.DataFrame, zz: list[Swing], atr: float, j: int) -> Detection | None:
    """Triangle or wedge from the last three highs and three lows."""
    if len(zz) < 6:
        return None
    recent = zz[-6:]
    highs, lows = [s for s in recent if s.kind == "high"], [s for s in recent if s.kind == "low"]
    first, last = recent[0].i, recent[-1].i
    fits = []
    for points in (highs, lows):
        x, y = np.array([s.i for s in points], dtype=float), np.array([s.price for s in points])
        slope, intercept = np.polyfit(x, y, 1)
        if np.abs(y - (slope * x + intercept)).max() > 0.5 * atr:
            return None  # the swings do not sit on a line
        fits.append((slope, intercept))
    (hs, hi), (ls, li) = fits
    gap_start, gap_end = (hs * first + hi) - (ls * first + li), (hs * j + hi) - (ls * j + li)
    if not 0 < gap_end < 0.75 * gap_start:
        return None  # not converging, or already crossed
    drift_h, drift_l = hs * (last - first) / atr, ls * (last - first) / atr

    def shape(drift):
        return "flat" if abs(drift) < 0.75 else "rising" if drift > 0 else "falling"

    name, direction = {
        ("flat", "rising"): ("ascending_triangle", "bullish"),
        ("falling", "flat"): ("descending_triangle", "bearish"),
        ("falling", "rising"): ("symmetrical_triangle", "neutral"),
        ("rising", "rising"): ("rising_wedge", "bearish"),
        ("falling", "falling"): ("falling_wedge", "bullish"),
    }.get((shape(drift_h), shape(drift_l)), (None, None))
    if name is None:
        return None
    upper, lower = hs * j + hi, ls * j + li
    detection = Detection(
        name,
        "chart",
        direction,
        df.index[j].to_pydatetime(),
        0.5,
        f"Highs are {shape(drift_h)} and lows are {shape(drift_l)} over {last - first} bars; "
        f"the range narrowed from {gap_start:.2f} to {gap_end:.2f}.",
        zone=(float(lower), float(upper)),
    )
    if direction == "bullish":
        with_levels(detection, float(upper), float(lower), float(upper + gap_start))
    elif direction == "bearish":
        with_levels(detection, float(lower), float(upper), float(lower - gap_start))
    return detection


def _cup(df: pd.DataFrame, rim: Swing, j: int, atr: float) -> Detection | None:
    """A rounded bottom from the rim high back up to the rim."""
    closes = df["close"].to_numpy(dtype=float)[rim.i : j + 1]
    depth = rim.price - float(df["low"].to_numpy(dtype=float)[rim.i : j + 1].min())
    if depth < 3 * atr:
        return None
    x = np.arange(len(closes), dtype=float)
    a, b, _ = np.polyfit(x, closes, 2)
    bottom = -b / (2 * a) / (len(closes) - 1) if a > 0 else -1.0  # where the low sits, 0 to 1
    # A rounded base lingers near its low: a parabola spends 58% of its bars in the lowest
    # third of its depth, a V-shaped reversal only 33%.
    floor = closes.min()
    near_low = float((closes <= floor + (rim.price - floor) / 3).mean())
    if a <= 0 or not 0.25 <= bottom <= 0.75 or near_low < 0.45:
        return None
    detection = Detection(
        "rounded_bottom",
        "chart",
        "bullish",
        df.index[j].to_pydatetime(),
        round(min(0.4 + 0.5 * near_low, 0.75), 2),
        f"A {len(closes)}-bar rounded decline and recovery, {depth / atr:.1f} ATR deep, back at "
        f"the {rim.price:.2f} rim ({near_low:.0%} of the bars near the low).",
        zone=(rim.price - depth, rim.price),
    )
    return with_levels(detection, rim.price, rim.price - depth / 2, rim.price + depth)


# One pass over the bars that keeps every open setup's state; splitting it would scatter that
# state across helpers without making any rule easier to read.
def detect_chart_patterns(df: pd.DataFrame, swings: list[Swing]) -> list[Detection]:  # noqa: C901
    """`df` must carry atr_14 and rel_volume; `swings` come from structure.find_swings."""
    h, l, c = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))  # noqa: E741
    atr_series, rel_volume = (
        df["atr_14"].to_numpy(dtype=float),
        df["rel_volume"].to_numpy(dtype=float),
    )
    by_bar: dict[int, list[Swing]] = {}
    for swing in swings:
        by_bar.setdefault(swing.confirmed, []).append(swing)

    found: list[Detection] = []
    known: list[Swing] = []
    setups: list[_Setup] = []
    seen: set[tuple] = set()
    cups: list[Swing] = []  # rim highs still waiting for price to come back
    handles: list[tuple[int, float, float]] = []  # (bar the cup completed, rim, cup depth)
    last_break = -DONCHIAN
    narrowing: dict[str, int] = {}  # pattern name -> last swing of the latest one reported

    def emit(detection: Detection, key: tuple) -> None:
        if key not in seen:
            seen.add(key)
            found.append(detection)

    for j in range(len(df)):
        atr = atr_series[j]
        if j in by_bar:
            known += by_bar[j]
            cups += [s for s in by_bar[j] if s.kind == "high"]
        if np.isnan(atr) or atr <= 0:
            continue  # no volatility estimate yet: nothing can be measured
        if j in by_bar:
            zz = zigzag(known)
            new = [
                s
                for s in [*_reversal_setups(zz, atr, j), _flag_setup(zz, atr, j)]
                if s and s.key not in seen
            ]
            seen.update(s.key for s in new)
            setups += new
            for triple in (s for s in new if s.name.startswith("triple")):
                # The same swings also look like double tops; report the triple only.
                side, first, last = triple.name[7:], triple.key[1], triple.key[2]
                setups = [
                    s
                    for s in setups
                    if not (s.name == f"double_{side}" and first <= s.key[1] and s.key[2] <= last)
                ]
            converging = _converging(df, zz, atr, j)
            # Report a narrowing range once, not again each time another swing extends it.
            if converging and zz[-6].i > narrowing.get(converging.name, -1):
                narrowing[converging.name] = zz[-1].i
                found.append(converging)

        volume_note = f" on {rel_volume[j]:.1f}x average volume" if rel_volume[j] >= 1.5 else ""
        remaining = []
        for setup in setups:
            level = setup.level(j)
            if (c[j] - level) * setup.sign > 0:
                detection = Detection(
                    setup.name,
                    "chart",
                    "bullish" if setup.sign > 0 else "bearish",
                    df.index[j].to_pydatetime(),
                    round(min(setup.confidence + (0.1 if volume_note else 0), 1), 2),
                    f"{setup.note.capitalize()}; completed by a close at {c[j]:.2f} "
                    f"beyond {level:.2f}{volume_note}.",
                )
                stop = setup.stop
                if stop is None:  # flags: the far side of the pause
                    stop = (
                        l[setup.since : j + 1].min()
                        if setup.sign > 0
                        else h[setup.since : j + 1].max()
                    )
                stop += -setup.sign * 0.25 * atr
                found.append(
                    with_levels(
                        detection,
                        float(level),
                        float(stop),
                        float(level + setup.sign * setup.height),
                    )
                )
            elif (c[j] - setup.invalid) * setup.sign >= 0 and j <= setup.expires:
                remaining.append(setup)
        setups = remaining

        waiting = []
        for rim in cups:
            age = j - rim.i
            if age > CUP_BARS[1]:
                continue
            if age >= CUP_BARS[0] and c[j] >= rim.price - 0.25 * atr:  # back at the rim: judge it
                cup = _cup(df, rim, j, atr)
                if cup:
                    emit(cup, ("rounded_bottom", rim.i))
                    handles.append((j, rim.price, rim.price - l[rim.i : j + 1].min()))
            elif c[j] <= rim.price + 0.5 * atr:  # above that, price carried on without a base
                waiting.append(rim)
        cups = waiting

        still = []
        for done, rim, depth in handles:
            pullback = max(rim, h[done : j + 1].max()) - l[done : j + 1].min()
            if j - done > 25 or pullback > depth / 2:
                continue
            ceiling = max(rim, h[done:j].max()) if j > done else rim
            if j - done >= 3 and c[j] > ceiling and 0.5 * atr <= pullback <= depth / 3:
                detection = Detection(
                    "cup_and_handle",
                    "chart",
                    "bullish",
                    df.index[j].to_pydatetime(),
                    0.6,
                    f"A rounded bottom to {rim:.2f}, a {pullback / atr:.1f} ATR pullback, "
                    f"then a close at {c[j]:.2f} "
                    f"above {ceiling:.2f}{volume_note}.",
                )
                found.append(
                    with_levels(
                        detection,
                        float(ceiling),
                        float(l[done : j + 1].min()),
                        float(ceiling + depth),
                    )
                )
            else:
                still.append((done, rim, depth))
        handles = still

        if j >= DONCHIAN and j - last_break > 5 and rel_volume[j] >= 1.5:
            top, bottom = h[j - DONCHIAN : j].max(), l[j - DONCHIAN : j].min()
            sign = 1 if c[j] > top else -1 if c[j] < bottom else 0
            if sign:
                last_break = j
                level = top if sign > 0 else bottom
                detection = Detection(
                    "breakout" if sign > 0 else "breakdown",
                    "chart",
                    "bullish" if sign > 0 else "bearish",
                    df.index[j].to_pydatetime(),
                    0.6 if rel_volume[j] >= 2 else 0.5,
                    f"Close at {c[j]:.2f} beyond the {DONCHIAN}-bar "
                    f"{'high' if sign > 0 else 'low'} of {level:.2f} "
                    f"on {rel_volume[j]:.1f}x average volume.",
                )
                found.append(with_levels(detection, float(level), float(level - sign * atr)))
    return found
