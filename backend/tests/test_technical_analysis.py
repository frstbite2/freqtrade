"""Technical analysis: indicators, candlesticks, chart patterns, market structure, engine, API.

NO REAL MARKET DATA IS USED HERE. Every price series is constructed for the test (straight legs,
explicit candles, seeded random walks). These tests show that each rule does what its definition
says and never looks ahead. They do not show that the rules work on real markets; that needs
verified price data and the backtests of Milestone 8.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.core.config import load_settings
from backend.main import create_app
from backend.services.market_data.base import Bar
from backend.services.market_data.service import MarketDataService
from backend.services.technical_analysis import structure as st
from backend.services.technical_analysis.candles import detect_candlesticks
from backend.services.technical_analysis.engine import MIN_BARS, analyze, bias_series, detect_all
from backend.services.technical_analysis.indicators import (
    add_indicators,
    fibonacci_levels,
    to_frame,
    volume_profile,
)
from backend.services.technical_analysis.patterns import detect_chart_patterns
from backend.tests.ta_helpers import analysed, frame, ohlc, path


BASE = (30, 100.0)  # thirty quiet bars so indicators have history before the pattern


def random_walk(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.003, n))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n))),
            "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n))),
            "close": close,
            "volume": rng.lognormal(13, 0.5, n),
        },
        index=pd.date_range("2022-01-03 05:00", periods=n, freq="B", tz="UTC", name="ts"),
    )


# --- indicators ---


def test_indicators_are_unavailable_until_they_have_enough_history():
    df = add_indicators(random_walk(260, 1), "1d")
    for column, first in (
        ("sma_20", 19),
        ("ema_200", 199),
        ("sma_200", 199),
        ("rsi_14", 14),
        ("atr_14", 14),
        ("bb_upper", 19),
        ("avg_volume_20", 19),
        ("rel_volume", 20),
        ("hist_vol_20", 20),
        ("macd_hist", 33),
        ("mfi_14", 14),
    ):
        assert df[column].iloc[:first].isna().all(), column  # NaN, never zero
        assert df[column].iloc[first:].notna().all(), column
    assert df["vwap"].isna().all()  # no session VWAP on daily bars


def test_standard_indicators_match_an_independent_calculation():
    raw = random_walk(400, 7)
    df = add_indicators(raw, "1d")
    close, high, low = raw["close"], raw["high"], raw["low"]

    assert np.allclose(df["sma_50"].dropna(), close.rolling(50).mean().dropna())
    deviation = close.rolling(20).std(ddof=0)
    assert np.allclose(df["bb_upper"].dropna(), (close.rolling(20).mean() + 2 * deviation).dropna())

    ema = [close.iloc[:21].mean()]  # seeded with the simple average of the first 21 closes
    for price in close.iloc[21:]:
        ema.append(ema[-1] + 2 / 22 * (price - ema[-1]))
    assert np.allclose(df["ema_21"].dropna(), ema)

    change = close.diff()
    gain, loss = change.clip(lower=0), -change.clip(upper=0)
    avg_gain, avg_loss = [gain.iloc[1:15].mean()], [loss.iloc[1:15].mean()]  # Wilder's smoothing
    for g, l in zip(gain.iloc[15:], loss.iloc[15:], strict=True):  # noqa: E741
        avg_gain.append((avg_gain[-1] * 13 + g) / 14)
        avg_loss.append((avg_loss[-1] * 13 + l) / 14)
    rsi = 100 - 100 / (1 + np.array(avg_gain) / np.array(avg_loss))
    assert np.allclose(df["rsi_14"].dropna(), rsi)

    true_range = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = [true_range.iloc[1:15].mean()]
    for value in true_range.iloc[15:]:
        atr.append((atr[-1] * 13 + value) / 14)
    assert np.allclose(df["atr_14"].dropna(), atr)

    obv = (np.sign(change).fillna(0) * raw["volume"]).cumsum() + raw["volume"].iloc[0]
    assert np.allclose(df["obv"], obv)


def test_relative_volume_compares_with_the_bars_before():
    volume = [1000.0] * 30 + [3000.0, 1000.0]
    df = analysed(np.linspace(100, 103, 32), volume=volume)
    assert df["rel_volume"].iloc[30] == pytest.approx(3.0)  # the spike does not dilute itself
    assert df["avg_volume_20"].iloc[30] == pytest.approx(1100.0)
    assert df["rel_volume"].iloc[31] == pytest.approx(1000 / 1100)
    assert analysed(np.linspace(100, 103, 32), volume=0)["rel_volume"].isna().all()  # not infinity


def test_historical_volatility_is_annualised_per_timeframe():
    closes = 100 * np.exp(np.cumsum(np.tile([0.01, -0.01], 20)))
    expected = 0.01 * np.sqrt(20 / 19)  # sample deviation of ten +1% and ten -1% log returns
    assert analysed(closes, "1d")["hist_vol_20"].iloc[-1] == pytest.approx(expected * np.sqrt(252))
    assert analysed(closes, "1w")["hist_vol_20"].iloc[-1] == pytest.approx(expected * np.sqrt(52))
    assert analysed(np.full(40, 100.0), "1d")["hist_vol_20"].iloc[-1] == 0


def test_session_vwap_restarts_each_trading_day():
    # Two bars late on 3 January (New York time), then two on 4 January.
    df = frame(
        [10, 20, 30, 40],
        wick=0,
        opens=[10, 20, 30, 40],
        volume=[1, 3, 2, 2],
        freq="2h",
        start="2022-01-03 23:00",
    )
    vwap = add_indicators(df, "1h")["vwap"]
    assert list(df.index.tz_convert("America/New_York").day) == [3, 3, 3, 4]
    assert vwap.tolist() == pytest.approx([10, (10 * 1 + 20 * 3) / 4, (10 + 60 + 60) / 6, 40])


def test_fibonacci_levels():
    up = fibonacci_levels(100, 200, "up")
    assert up == pytest.approx(
        {"0.236": 176.4, "0.382": 161.8, "0.500": 150, "0.618": 138.2, "0.786": 121.4}
    )
    assert fibonacci_levels(100, 200, "down")["0.382"] == pytest.approx(138.2)
    for bad in ((200, 100, "up"), (100, 100, "up"), (100, 200, "sideways")):
        with pytest.raises(ValueError):
            fibonacci_levels(*bad)


def test_volume_profile():
    bars = ohlc([(10, 20, 10, 20), (10, 12, 10, 12)], volume=[100, 300])
    profile = volume_profile(bars, bins=5)
    # The first bar spreads 100 over five 2-point bins; the second puts 300 in the lowest.
    assert [b["volume"] for b in profile["bins"]] == pytest.approx([320, 20, 20, 20, 20])
    assert profile["point_of_control"] == pytest.approx(11)
    assert (profile["value_area_low"], profile["value_area_high"]) == pytest.approx((10, 12))
    wide = volume_profile(bars, bins=5, value_area=0.9)  # 360 of 400 needs two more bins
    assert (wide["value_area_low"], wide["value_area_high"]) == pytest.approx((10, 16))
    assert volume_profile(ohlc([(10, 10, 10, 10)] * 3)) is None  # no price range
    assert volume_profile(ohlc([(10, 12, 9, 11)] * 3, volume=0)) is None  # no volume


def test_frame_requires_ordered_unique_bars():
    def bar(day):
        return Bar(
            "XYZ",
            "1d",
            datetime(2024, 1, day, 5, tzinfo=UTC),
            Decimal("10.5"),
            Decimal(11),
            Decimal(10),
            Decimal("10.75"),
            Decimal(1000),
            5,
            None,
        )

    df = to_frame([bar(2), bar(3)])
    assert df["close"].tolist() == [10.75, 10.75] and str(df.index.tz) == "UTC"
    for bad in ([bar(3), bar(2)], [bar(2), bar(2)]):
        with pytest.raises(ValueError, match="chronological"):
            to_frame(bad)
    with pytest.raises(ValueError, match="timeframe"):
        add_indicators(df, "2d")


# --- candlesticks ---


def lead(direction: int, n: int = 30, start: float = 100.0):
    """Ordinary candles drifting one way, and the price where the next candle would open."""
    rows, price = [], start
    for _ in range(n):
        close = price + direction * 0.6
        rows.append((price, max(price, close) + 0.2, min(price, close) - 0.2, close))
        price += direction * 0.5
    return rows, price


DOWN, P = lead(-1)
UP, Q = lead(+1)
CANDLES = {
    "engulfing bullish": (
        DOWN + [(P, P + 0.1, P - 0.5, P - 0.4), (P - 0.6, P + 1.1, P - 0.7, P + 1.0)],
        "engulfing",
        "bullish",
    ),
    "engulfing bearish": (
        UP + [(Q, Q + 0.5, Q - 0.1, Q + 0.4), (Q + 0.6, Q + 0.7, Q - 1.1, Q - 1.0)],
        "engulfing",
        "bearish",
    ),
    "hammer": (DOWN + [(P, P + 0.05, P - 2.0, P - 0.1)], "hammer", "bullish"),
    "shooting star": (UP + [(Q + 0.3, Q + 2.4, Q + 0.25, Q + 0.4)], "shooting_star", "bearish"),
    "doji": (DOWN + [(P, P + 0.6, P - 0.6, P + 0.01)], "doji", "neutral"),
    "morning star": (
        DOWN
        + [
            (P, P + 0.1, P - 2.6, P - 2.5),
            (P - 3.0, P - 2.8, P - 3.3, P - 3.1),
            (P - 2.9, P - 0.4, P - 3.0, P - 0.5),
        ],
        "morning_star",
        "bullish",
    ),
    "evening star": (
        UP
        + [
            (Q, Q + 2.6, Q - 0.1, Q + 2.5),
            (Q + 3.0, Q + 3.3, Q + 2.8, Q + 3.1),
            (Q + 2.9, Q + 3.0, Q + 0.4, Q + 0.5),
        ],
        "evening_star",
        "bearish",
    ),
    "three white soldiers": (
        DOWN
        + [
            (P, P + 1.55, P - 0.05, P + 1.5),
            (P + 0.8, P + 3.05, P + 0.75, P + 3.0),
            (P + 2.3, P + 4.55, P + 2.25, P + 4.5),
        ],
        "three_white_soldiers",
        "bullish",
    ),
    "three black crows": (
        UP
        + [
            (Q, Q + 0.05, Q - 1.55, Q - 1.5),
            (Q - 0.8, Q - 0.75, Q - 3.05, Q - 3.0),
            (Q - 2.3, Q - 2.25, Q - 4.55, Q - 4.5),
        ],
        "three_black_crows",
        "bearish",
    ),
    "inside bar": (DOWN + [(P, P + 0.4, P - 0.2, P + 0.3)], "inside_bar", "neutral"),
    "pin bar bullish": (UP + [(Q - 0.1, Q + 0.05, Q - 1.5, Q)], "pin_bar", "bullish"),
    "pin bar bearish": (UP + [(Q + 0.1, Q + 1.5, Q - 0.05, Q)], "pin_bar", "bearish"),
}


def last_candles(rows, volume=1000.0):
    df = add_indicators(ohlc(rows, volume=volume), "1d")
    return df, [d for d in detect_candlesticks(df) if d.detected_at == df.index[-1]]


@pytest.mark.parametrize("case", CANDLES)
def test_candlestick_is_recognised(case):
    rows, name, direction = CANDLES[case]
    _, found = last_candles(rows)
    assert [(d.name, d.direction, d.kind) for d in found] == [(name, direction, "candlestick")]
    (d,) = found
    if direction == "neutral":
        assert (d.entry_zone, d.stop_loss, d.targets) == (None, None, [])
    else:
        sign = 1 if direction == "bullish" else -1
        assert sign * (d.entry_zone[1] - d.stop_loss) > 0  # the stop is on the losing side
        assert all(sign * (target - d.entry_zone[1]) > 0 for target in d.targets)
        assert d.entry_zone[0] < d.entry_zone[1]
    assert 0 < d.confidence < 1 and d.historical_performance.startswith("unavailable")


def test_bullish_engulfing_levels_and_context():
    rows, _, _ = CANDLES["engulfing bullish"]
    df, (quiet,) = last_candles(rows)
    atr = df["atr_14"].iloc[-1]
    pattern_high, pattern_low = P + 1.1, P - 0.7
    stop = pattern_low - 0.25 * atr
    risk = pattern_high - stop
    assert quiet.stop_loss == pytest.approx(stop)
    assert quiet.entry_zone == pytest.approx((pattern_high - 0.25 * risk, pattern_high))
    assert quiet.targets == pytest.approx([pattern_high + risk, pattern_high + 2 * risk])
    assert quiet.confidence == 0.55 and "follows a decline" in quiet.explanation

    _, (loud,) = last_candles(rows, volume=[1000.0] * 31 + [2500.0])
    assert loud.confidence == 0.7 and "2.5x the 20-bar average" in loud.explanation
    # The same candles after a rise have nothing to reverse.
    _, (weak,) = last_candles(
        UP + [(Q, Q + 0.1, Q - 0.5, Q - 0.4), (Q - 0.6, Q + 1.1, Q - 0.7, Q + 1.0)]
    )
    assert (weak.name, weak.confidence) == ("engulfing", 0.4)


def test_ordinary_candles_are_not_patterns():
    for rows in (DOWN + [(P, P + 0.2, P - 0.8, P - 0.6)], UP + [(Q, Q + 0.8, Q - 0.2, Q + 0.6)]):
        assert last_candles(rows)[1] == []


# --- market structure ---

UPTREND_THEN_BREAK = path(
    100, (10, 110), (5, 105), (10, 118), (5, 112), (10, 126), (5, 120), (6, 108)
)


def events(detections, df):
    return [(d.name, d.direction, df.index.get_loc(d.detected_at)) for d in detections]


def test_swings_are_labelled_and_only_known_three_bars_later():
    df = analysed(UPTREND_THEN_BREAK)
    swings = st.find_swings(df)
    assert [(s.kind, s.i, s.label, s.confirmed) for s in swings] == [
        ("high", 10, "", 13),
        ("low", 15, "", 18),
        ("high", 25, "HH", 28),
        ("low", 30, "HL", 33),
        ("high", 40, "HH", 43),
    ]
    assert swings[0].price == pytest.approx(110.3) and swings[1].price == pytest.approx(104.7)
    assert st.trend_from_swings(swings) == "up"
    assert (
        st.trend_from_swings(
            st.find_swings(analysed(path(100, (10, 90), (5, 95), (10, 82), (5, 88), (10, 74))))
        )
        == "down"
    )
    assert (
        st.trend_from_swings(
            st.find_swings(analysed(path(100, (10, 110), (5, 104), (10, 112), (5, 102), (6, 106))))
        )
        == "range"
    )
    assert st.trend_from_swings([]) == "range"


def test_zigzag_keeps_the_most_extreme_of_repeated_swings():
    swings = [
        st.Swing(5, 110, "high", 8),
        st.Swing(9, 112, "high", 12),
        st.Swing(14, 100, "low", 17),
        st.Swing(18, 101, "low", 21),
        st.Swing(25, 111, "high", 28),
    ]
    assert [(s.kind, s.i) for s in st.zigzag(swings)] == [("high", 9), ("low", 14), ("high", 25)]


def test_break_of_structure_change_of_character_and_order_blocks():
    df = analysed(UPTREND_THEN_BREAK)
    found = st.detect_breaks(df, st.find_swings(df))
    assert events(found, df) == [
        ("liquidity_sweep", "bearish", 19),  # the wick pierced 110.3, the close did not
        ("break_of_structure", "bullish", 20),  # the next close did
        ("order_block", "bullish", 20),
        ("break_of_structure", "bullish", 35),
        ("order_block", "bullish", 35),
        ("change_of_character", "bearish", 50),  # first close under a swing low of the uptrend
        ("order_block", "bearish", 50),
    ]
    choch, block = found[-2], found[-1]
    assert choch.zone[1] == pytest.approx(111.7) and "against the prior trend" in choch.explanation
    # The order block is the last up candle before the fall: bar 40, which closed at 126.
    assert block.zone == pytest.approx((df["low"].iloc[40], df["high"].iloc[40]))
    assert all(d.kind == "structure" and d.entry_zone is None for d in found)


def test_liquidity_sweep_then_reversal():
    closes = path(100, (10, 110), (8, 104), (6, 109))
    rows = [
        (o, max(o, c) + 0.3, min(o, c) - 0.3, c)
        for o, c in zip(np.r_[100, closes[:-1]], closes, strict=True)
    ]
    rows += [(109, 111.5, 108.5, 109.2)] + [
        (109.2 - k, 109.5 - k, 108 - k, 108.2 - k) for k in range(5)
    ]
    df = add_indicators(ohlc(rows), "1d")
    (sweep,) = st.detect_breaks(df, st.find_swings(df))
    assert (sweep.name, sweep.direction, df.index.get_loc(sweep.detected_at)) == (
        "liquidity_sweep",
        "bearish",
        25,
    )
    assert sweep.zone == pytest.approx((110.3, 111.5))


FLAT = [(100, 100.5, 99.5, 100.1)] * 20


def test_fair_value_gap_demand_zone_and_volume_imbalance():
    rows = FLAT + [
        (100.1, 100.6, 99.9, 100.5),
        (100.6, 103.5, 100.5, 103.4),
        (103.5, 104.5, 101.2, 104.0),
    ]
    df = add_indicators(ohlc(rows), "1d")
    found = {(d.name, df.index.get_loc(d.detected_at)): d for d in st.detect_gaps_and_zones(df)}
    gap = found["fair_value_gap", 22]
    assert (gap.direction, gap.zone) == (
        "bullish",
        pytest.approx((100.6, 101.2)),
    )  # first high to third low
    zone = found["demand_zone", 21]  # the 2.8-point candle; the zone is the candle before it
    assert (zone.direction, zone.zone) == ("bullish", pytest.approx((99.9, 100.6)))
    assert found["volume_imbalance", 22].zone == pytest.approx((103.4, 103.5))

    assert st.open_fair_value_gaps(df) == [
        {
            "direction": "bullish",
            "low": pytest.approx(100.6),
            "high": pytest.approx(101.2),
            "since": df.index[22].isoformat(),
        }
    ]
    filled = add_indicators(ohlc(rows + [(104, 104.2, 100.2, 100.4)]), "1d")
    assert st.open_fair_value_gaps(filled) == []  # price traded back through it

    mirrored = add_indicators(
        ohlc(
            FLAT + [(100.1, 100.3, 99.6, 99.7), (99.6, 99.7, 96.7, 96.8), (96.7, 99.0, 96.0, 96.2)]
        ),
        "1d",
    )
    names = {(d.name, d.direction) for d in st.detect_gaps_and_zones(mirrored)}
    assert {("fair_value_gap", "bearish"), ("supply_zone", "bearish")} <= names
    assert st.detect_gaps_and_zones(add_indicators(ohlc(FLAT * 2), "1d")) == []


def test_consolidation_then_expansion():
    rng = np.random.default_rng(3)
    noisy = 100 + np.cumsum(rng.normal(0, 1.2, 150))
    tight = noisy[-1] + rng.normal(0, 0.05, 40)
    df = analysed(np.r_[noisy, tight, tight[-1] + 4.0, tight[-1] + 5.0])
    found = events(st.detect_squeeze_and_expansion(df), df)
    assert ("expansion", "bullish", 190) in found  # the first wide candle out of the tight range
    squeezes = [bar for name, _, bar in found if name == "consolidation"]
    assert squeezes and squeezes[-1] < 190  # the tight range may extend an earlier one
    assert next(e for e in found if e[2] > squeezes[-1]) == ("expansion", "bullish", 190)


def test_trend_exhaustion_is_a_higher_high_on_weaker_momentum():
    df = analysed(path(100, BASE, (12, 130), (6, 124), (14, 131.5), (8, 122)))
    swings = st.find_swings(df)
    first, second = (s for s in swings if s.kind == "high")
    assert second.label == "HH" and df["rsi_14"].iloc[second.i] < df["rsi_14"].iloc[first.i]
    (found,) = st.detect_exhaustion(df, swings)
    assert (found.name, found.direction) == ("trend_exhaustion", "bearish")
    assert found.detected_at == df.index[second.confirmed]  # reported when the high is confirmed
    # A higher high on stronger momentum is not exhaustion.
    # RSI reads 100 straight after a flat base, so the first rally here is choppy on purpose.
    legs = ((6, 104), (3, 102), (6, 108), (3, 106), (6, 115), (6, 111), (8, 135), (6, 128))
    strong = analysed(path(100, BASE, *legs))
    swings = st.find_swings(strong)
    final = [s for s in swings if s.kind == "high"][-1]
    assert final.label == "HH" and strong["rsi_14"].iloc[final.i] > 85
    found = st.detect_exhaustion(strong, swings)
    assert all(d.detected_at != strong.index[final.confirmed] for d in found)


def test_support_and_resistance_need_repeated_turns():
    df = analysed(path(100, (8, 110), (8, 100), (8, 110), (8, 100), (8, 110), (4, 105)))
    levels = st.support_resistance(df, st.find_swings(df))
    assert [(round(lv["price"], 1), lv["kind"], lv["touches"]) for lv in levels] == [
        (99.7, "support", 2),
        (110.3, "resistance", 3),
    ]
    trend = analysed(UPTREND_THEN_BREAK)
    assert st.support_resistance(trend, st.find_swings(trend)) == []  # no level was tested twice


# --- chart patterns ---

CUP = np.r_[path(100, BASE, (20, 120)), 100 + 20 * np.linspace(-1, 1, 61)[1:] ** 2]
RANGE = 100 + np.tile([0.5, -0.5], 30)
CHARTS = {
    "double_top": (path(100, BASE, (20, 120), (8, 110), (8, 120), (14, 100)), "bearish", 74),
    "double_bottom": (path(100, BASE, (20, 80), (8, 90), (8, 80), (14, 100)), "bullish", 74),
    "triple_top": (
        path(100, BASE, (20, 120), (8, 110), (8, 120), (8, 110), (8, 120), (14, 100)),
        "bearish",
        90,
    ),
    "triple_bottom": (
        path(100, BASE, (20, 80), (8, 90), (8, 80), (8, 90), (8, 80), (14, 100)),
        "bullish",
        90,
    ),
    "head_and_shoulders": (
        path(100, BASE, (15, 115), (7, 108), (12, 126), (12, 108), (7, 115), (12, 98)),
        "bearish",
        89,
    ),
    "inverse_head_and_shoulders": (
        path(100, BASE, (15, 85), (7, 92), (12, 74), (12, 92), (7, 85), (12, 102)),
        "bullish",
        89,
    ),
    "ascending_triangle": (
        path(100, BASE, (20, 120), (10, 104), (10, 120), (8, 110), (8, 120), (6, 114), (5, 119)),
        "bullish",
        95,
    ),
    "descending_triangle": (
        path(100, BASE, (20, 80), (10, 96), (10, 80), (8, 90), (8, 80), (6, 86), (5, 81)),
        "bearish",
        95,
    ),
    "symmetrical_triangle": (
        path(100, BASE, (10, 120), (12, 100), (10, 116), (9, 104), (7, 113), (6, 107), (4, 110)),
        "neutral",
        87,
    ),
    "rising_wedge": (
        path(100, BASE, (12, 114), (6, 106), (12, 118), (6, 112), (12, 121), (6, 117), (5, 121)),
        "bearish",
        87,
    ),
    "falling_wedge": (
        path(100, BASE, (12, 86), (6, 94), (12, 82), (6, 88), (12, 79), (6, 83), (5, 79)),
        "bullish",
        87,
    ),
    "bull_flag": (path(100, BASE, (5, 97), (8, 120), (6, 116), (4, 123)), "bullish", 52),
    "bear_flag": (path(100, BASE, (5, 103), (8, 80), (6, 84), (4, 77)), "bearish", 52),
    "rounded_bottom": (CUP, "bullish", 110),
}


def charts(closes, **kwargs):
    df = analysed(closes, **kwargs)
    return df, detect_chart_patterns(df, st.find_swings(df))


@pytest.mark.parametrize("name", CHARTS)
def test_chart_pattern_is_recognised_once_at_its_completing_bar(name):
    closes, direction, bar = CHARTS[name]
    df, found = charts(closes)
    assert [(d.name, d.direction, df.index.get_loc(d.detected_at)) for d in found] == [
        (name, direction, bar)
    ]
    (d,) = found
    assert d.kind == "chart" and 0 < d.confidence < 1
    if direction == "neutral":
        assert d.entry_zone is None and d.zone is not None  # no side to trade until it breaks
        return
    sign = 1 if direction == "bullish" else -1
    assert sign * (d.entry_zone[1 if sign > 0 else 0] - d.stop_loss) > 0
    assert all(sign * (t - d.entry_zone[1 if sign > 0 else 0]) > 0 for t in d.targets)
    # Nothing about the detection can come from bars after it.
    assert detect_chart_patterns(df.iloc[: bar + 1], st.find_swings(df.iloc[: bar + 1]))[-1] == d


def test_double_top_measured_move():
    df, (top,) = charts(CHARTS["double_top"][0])
    highs, neckline = 120.3, 109.7  # closes of 120 and 110 plus the 0.3 wick
    atr = df["atr_14"].iloc[74]
    assert top.entry_zone[0] == pytest.approx(neckline)
    assert top.stop_loss == pytest.approx(highs + 0.25 * atr)
    measured = neckline - (highs - neckline)  # the pattern's height, projected
    assert any(t == pytest.approx(measured) for t in top.targets)  # the other is 2x the risk
    assert (
        df["close"].iloc[74] < neckline <= df["close"].iloc[73]
    )  # the first close below the neckline
    assert "120.30" in top.explanation and "109.70" in top.explanation


def test_head_and_shoulders_measured_move():
    _, (pattern,) = charts(CHARTS["head_and_shoulders"][0])
    head, neckline = 126.3, 107.7
    assert pattern.targets[-1] == pytest.approx(neckline - (head - neckline))
    assert pattern.stop_loss > 115.3  # above the right shoulder
    assert "head at 126.30 between shoulders at 115.30 and 115.30" in pattern.explanation.lower()


def test_cup_and_handle_follows_a_rounded_bottom():
    closes = np.r_[CUP, path(120, (5, 116.5), (4, 122))[1:]]
    df, found = charts(closes)
    assert events(found, df) == [
        ("rounded_bottom", "bullish", 110),
        ("cup_and_handle", "bullish", 118),
    ]
    cup, handle = found
    assert cup.targets[-1] == pytest.approx(120.3 + (120.3 - 99.7))  # rim plus the cup's depth
    assert handle.targets[-1] == pytest.approx(120.3 + (120.3 - 99.7))
    assert handle.stop_loss == pytest.approx(df["low"].iloc[110:119].min())  # under the handle


def test_breakout_needs_volume():
    closes = np.r_[RANGE, [103.0], path(103, (10, 104))[1:]]
    volume = np.full(len(closes), 1000.0)
    volume[60] = 3200
    df, (breakout,) = charts(closes, volume=volume)
    assert (breakout.name, breakout.direction, df.index.get_loc(breakout.detected_at)) == (
        "breakout",
        "bullish",
        60,
    )
    assert breakout.entry_zone[1] == pytest.approx(100.8)  # the 20-bar high that was broken
    assert "3.2x average volume" in breakout.explanation
    assert charts(closes)[1] == []  # the same move on ordinary volume is not reported

    falling = np.r_[RANGE, [97.0], path(97, (10, 96))[1:]]
    _, (breakdown,) = charts(falling, volume=volume)
    assert (breakdown.name, breakdown.direction) == ("breakdown", "bearish")


@pytest.mark.parametrize(
    "closes",
    [
        path(100, (120, 160)),  # steady trend
        np.full(120, 100.0),  # nothing happens
        path(100, BASE, (20, 120), (30, 100), (30, 121)),  # a V is not a rounded bottom
        path(100, BASE, (5, 97), (8, 120), (6, 108), (6, 123)),  # a deep pullback is not a flag
        path(
            100, BASE, (20, 120), (8, 110), (8, 120), (14, 124)
        ),  # double top that never breaks down
        path(
            100, BASE, (20, 120), (8, 110), (8, 114), (14, 100)
        ),  # second high well short of the first
    ],
)
def test_lookalikes_are_not_reported(closes):
    assert charts(closes)[1] == []


# --- the whole engine: no look-ahead ---


@pytest.mark.parametrize("seed", range(4))
def test_later_bars_never_change_earlier_detections(seed):
    raw = random_walk(600, seed)
    full = detect_all(add_indicators(raw, "1d"))
    assert len({d.name for d in full}) > 15  # the walk exercises most detectors
    for cut in (250, 400, 555):
        prefix = detect_all(add_indicators(raw.iloc[:cut], "1d"))
        assert prefix == [d for d in full if d.detected_at <= raw.index[cut - 1]]


def to_bars(df: pd.DataFrame, timeframe: str) -> list[Bar]:
    return [
        Bar(
            "XYZ",
            timeframe,
            ts.to_pydatetime(),
            *(Decimal(str(round(row[k], 4))) for k in ("open", "high", "low", "close", "volume")),
            None,
            None,
        )
        for ts, row in df.iterrows()
    ]


def weekly(daily: pd.DataFrame) -> pd.DataFrame:
    grouped = daily.resample("W-MON", label="left", closed="left")
    return grouped.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


def test_analysis_output_and_higher_timeframe_agreement():
    # Long enough for every weekly vote (200-week average), with a dip that is small beside it.
    rise = np.r_[path(100, (1050, 1000)), path(1000, (20, 980), (8, 990), (8, 980), (10, 1000))[1:]]
    daily = frame(rise)
    result = analyze(
        "XYZ",
        {
            "1d": to_bars(daily, "1d"),
            "1w": to_bars(weekly(daily), "1w"),
            "1h": to_bars(daily.iloc[:10], "1h"),
        },
    )
    json.dumps(result)  # the whole result is plain JSON
    assert (
        result["symbol"] == "XYZ"
        and "not yet verified on real market data" in result["disclaimer"].lower()
    )
    assert result["timeframes"]["1h"] == {
        "status": "insufficient_data",
        "bars": 10,
        "detail": f"needs at least {MIN_BARS} bars",
    }

    day = result["timeframes"]["1d"]
    assert (day["status"], day["bars"], day["last_bar"]) == (
        "ok",
        len(daily),
        daily.index[-1].isoformat(),
    )
    assert (
        day["indicators"]["sma_200"] is not None and day["indicators"]["vwap"] is None
    )  # null, not zero
    assert set(day["levels"]) == {
        "support_resistance",
        "fibonacci",
        "volume_profile",
        "open_fair_value_gaps",
    }
    (bottom,) = (d for d in day["detections"] if d["name"] == "double_bottom")
    assert bottom["symbol"] == "XYZ" and bottom["timeframe"] == "1d"
    assert bottom["higher_timeframe"] == {"timeframe": "1w", "bias": "bullish", "agrees": True}
    assert (
        bottom["confidence"] == pytest.approx(0.8)
        and "The 1w trend agrees (bullish)." in bottom["explanation"]
    )
    assert bottom["historical_performance"].startswith("unavailable")
    assert all(
        d["higher_timeframe"] is None for d in result["timeframes"]["1w"]["detections"]
    )  # nothing above weekly

    # Against the weekly trend, the same kind of signal is marked down.
    fall = np.r_[path(1100, (1050, 100)), path(100, (20, 120), (8, 110), (8, 120), (10, 100))[1:]]
    down = frame(fall)
    result = analyze("XYZ", {"1d": to_bars(down, "1d"), "1w": to_bars(weekly(down), "1w")})
    (top,) = (d for d in result["timeframes"]["1d"]["detections"] if d["name"] == "double_top")
    assert top["higher_timeframe"]["agrees"] is True  # a top agrees with a falling weekly trend
    lows = np.r_[path(1100, (1050, 100)), path(100, (20, 80), (8, 90), (8, 80), (10, 100))[1:]]
    result = analyze(
        "XYZ", {"1d": to_bars(frame(lows), "1d"), "1w": to_bars(weekly(frame(lows)), "1w")}
    )
    (against,) = (
        d for d in result["timeframes"]["1d"]["detections"] if d["name"] == "double_bottom"
    )
    assert against["higher_timeframe"] == {"timeframe": "1w", "bias": "bearish", "agrees": False}
    assert against["confidence"] == pytest.approx(0.55) and "disagrees" in against["explanation"]


def test_higher_timeframe_uses_only_bars_that_had_closed():
    """A weekly bar still forming must not colour a daily detection made during that week."""
    daily = frame(
        np.r_[path(100, (400, 300)), path(300, (20, 280), (8, 290), (8, 280), (10, 300))[1:]]
    )
    week = weekly(daily)
    crashed = week.copy()
    crashed.iloc[-1, crashed.columns.get_loc("close")] = 1.0  # only the unfinished week differs
    crashed.iloc[-1, crashed.columns.get_loc("low")] = 0.5
    results = [
        analyze("XYZ", {"1d": to_bars(daily, "1d"), "1w": to_bars(w, "1w")}, recent_bars=3)[
            "timeframes"
        ]["1d"]["detections"]
        for w in (week, crashed)
    ]
    assert daily.index[-1] < week.index[-1] + timedelta(weeks=1)  # the last week has not closed
    assert results[0] == results[1] and results[0]


def test_bias_needs_history_and_votes():
    df = analysed(path(100, (300, 200)))
    bias = bias_series(df)
    assert bias.iloc[:20].isna().all()  # fewer than two votes can be computed
    assert bias.iloc[-1] == 1.0
    assert bias_series(analysed(path(200, (300, 100)))).iloc[-1] == -1.0
    assert (
        bias_series(analysed(np.r_[path(100, (250, 200))[:-1], path(200, (5, 185))])).iloc[-1]
        == 0.0
    )


# --- API ---

AUTH = {"Authorization": "Bearer test-token"}


class WalkProvider:
    name, feed = "fake", "test"

    def __init__(self):
        self.calls = []

    def get_bars(self, symbol, timeframe, start, end, adjustment):
        self.calls.append((timeframe, adjustment))
        days = random_walk(900, 11)
        days.index = pd.date_range(
            end=end.replace(hour=5, minute=0, second=0, microsecond=0),
            periods=900,
            freq="B",
            tz="UTC",
        )
        return [b for b in to_bars(days, timeframe) if start <= b.ts < end]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api.sqlite")
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(load_settings())) as client:
        yield client


def test_api_technical_analysis(api):
    provider = WalkProvider()
    api.app.state.market_data = MarketDataService(provider)
    response = api.get("/api/v1/technical/xyz", params={"timeframes": "1d"}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert (
        body["symbol"] == "XYZ" and body["source"] == "fake:test" and body["adjustment"] == "split"
    )
    day = body["timeframes"]["1d"]
    assert day["status"] == "ok" and day["bars"] > 300 and day["indicators"]["rsi_14"] is not None
    assert {"split"} == {
        adjustment for _, adjustment in provider.calls
    }  # splits must not look like gaps
    assert all(d["symbol"] == "XYZ" for d in day["detections"])
    # By default only the stronger matches are returned; everything is available on request.
    assert day["detections"] and all(d["confidence"] >= 0.5 for d in day["detections"])
    everything = api.get(
        "/api/v1/technical/xyz", params={"timeframes": "1d", "min_confidence": 0}, headers=AUTH
    ).json()["timeframes"]["1d"]["detections"]
    assert len(everything) > len(day["detections"])
    assert any(d["confidence"] < 0.5 for d in everything)
    bad = api.get("/api/v1/technical/xyz", params={"min_confidence": 2}, headers=AUTH)
    assert bad.status_code == 422


def test_api_technical_analysis_is_unavailable_without_prices(api):
    response = api.get("/api/v1/technical/AAPL", headers=AUTH)
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]
    assert api.get("/api/v1/technical/AAPL").status_code == 401


@pytest.mark.parametrize("timeframes", ["2d", "1d,", "", "1d,1d,1d,1d,1d,1d,1d,1d"])
def test_api_technical_analysis_validates_timeframes(api, timeframes):
    api.app.state.market_data = MarketDataService(WalkProvider())
    assert (
        api.get(
            "/api/v1/technical/XYZ", params={"timeframes": timeframes}, headers=AUTH
        ).status_code
        == 422
    )
