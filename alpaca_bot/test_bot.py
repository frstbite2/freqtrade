from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import bot
import numpy as np
import pandas as pd
import pytest


CFG = bot.load_config(Path(__file__).parent / "config.yaml")


def ohlc(close):
    close = np.asarray(close, dtype=float)
    idx = pd.date_range("2026-01-01", periods=len(close), freq="15min", tz="UTC")
    return pd.DataFrame(
        {"open": close, "high": close * 1.002, "low": close * 0.998, "close": close}, index=idx
    )


def test_trend_signals():
    up = bot.add_indicators(ohlc(np.linspace(100, 150, 120) + np.sin(np.arange(120))))
    down = bot.add_indicators(ohlc(np.linspace(150, 100, 120)))
    assert bot.signals(up, CFG).iloc[-1] == "buy"
    assert bot.signals(down, CFG).iloc[-1] == "sell"
    assert (bot.signals(up, CFG).iloc[:50] == "hold").all()  # not enough data for SMA_50 yet


def test_signal_has_no_lookahead():
    df = ohlc(np.linspace(100, 150, 120))
    full = bot.signals(bot.add_indicators(df.copy()), CFG)
    df.iloc[100:, :] *= 0.5  # crash the future
    cut = bot.signals(bot.add_indicators(df.copy()), CFG)
    assert (full.iloc[:100] == cut.iloc[:100]).all()


def test_confirmation_needs_two_bars():
    df = pd.DataFrame({"score": [0.5, 0.8, 0.5, 0.8, 0.9]})
    assert list(bot.signals(df, CFG)) == ["hold", "hold", "hold", "hold", "buy"]


def test_exit_levels_cap_atr_stop_at_2pct():
    assert bot.exit_levels(100, 0.5, CFG) == pytest.approx((99, 102))  # 2 x ATR = 1
    assert bot.exit_levels(100, 5, CFG) == pytest.approx((98, 104))  # capped at 2%, target 2R


def test_position_qty_caps():
    assert bot.position_qty(10_000, 0, 0, 230, 225.4, CFG, whole=True) == 2  # $500 cap -> 2 AAPL
    assert bot.position_qty(10_000, 0, 0, 600, 588, CFG, whole=True) == 0  # SPY > $500 cap
    assert bot.position_qty(10_000, 0, 5, 100, 98, CFG, whole=True) == 0  # max_open_positions
    assert (
        bot.position_qty(10_000, 2_800, 0, 100, 98, CFG, whole=False) == 2
    )  # only $200 exposure left
    assert bot.position_qty(10_000, 0, 0, 60_000, 58_800, CFG, whole=False) == pytest.approx(
        0.008333
    )


def test_backtest_runs_and_costs_money_on_chop():
    rng = np.random.default_rng(0)
    trend = bot.backtest(
        ohlc(np.linspace(100, 200, 2000) + rng.normal(0, 0.3, 2000)), CFG, whole=False
    )
    assert trend["trades"] > 0 and trend["return_pct"] > 0
    flat = bot.backtest(ohlc(np.full(500, 100.0)), CFG, whole=False)
    assert flat["trades"] == 0 and flat["return_pct"] == 0


class FakeTrading:
    def __init__(self, equity, last_equity, positions=()):
        self.acct = SimpleNamespace(equity=str(equity), last_equity=str(last_equity))
        self.positions = list(positions)
        self.submitted, self.closed_all = [], False

    def get_account(self):
        return self.acct

    def get_all_positions(self):
        return self.positions

    def get_orders(self, _):
        return []

    def get_clock(self):
        return SimpleNamespace(is_open=True)

    def submit_order(self, req):
        self.submitted.append(req)

    def close_all_positions(self, cancel_orders):
        self.closed_all = True


def make_bot(tmp_path, monkeypatch, trading):
    monkeypatch.setattr(bot, "STATE_FILE", tmp_path / "state.json")
    b = bot.Bot.__new__(bot.Bot)
    b.cfg, b.trading, b.minutes = CFG, trading, 15
    b.symbols = ["AAPL", "BTC/USD"]
    now = datetime.now(UTC)
    df = ohlc(np.linspace(100, 150, 120))
    df.index = pd.date_range(end=now - timedelta(minutes=16), periods=120, freq="15min")
    b.bars = lambda symbol, days: df * (500 if "/" in symbol else 1)
    return b


def test_step_buys_stock_bracket_and_crypto_limit(tmp_path, monkeypatch):
    t = FakeTrading(10_000, 10_000)
    make_bot(tmp_path, monkeypatch, t).step()
    stock, crypto = t.submitted
    assert stock.symbol == "AAPL" and stock.order_class == "bracket" and stock.qty == 3
    assert crypto.symbol == "BTC/USD" and crypto.limit_price == pytest.approx(75_075)
    assert "BTCUSD" in bot.load_state()["exits"]


def test_daily_loss_blocks_new_trades(tmp_path, monkeypatch):
    t = FakeTrading(9_700, 10_000)  # -3% today
    make_bot(tmp_path, monkeypatch, t).step()
    assert t.submitted == [] and not t.closed_all


def test_max_drawdown_halts_and_closes(tmp_path, monkeypatch):
    t = FakeTrading(9_000, 9_000)
    b = make_bot(tmp_path, monkeypatch, t)
    bot.save_state({"peak_equity": 10_000})
    b.step()
    assert t.closed_all and t.submitted == [] and bot.load_state()["halted"]


def test_live_keys_refused_in_paper_mode(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "AKLIVEKEY")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "x")
    with pytest.raises(SystemExit, match="do not match"):
        bot.Bot(CFG)
