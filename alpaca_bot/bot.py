"""Alpaca trend/momentum bot driven by config.yaml (stocks + crypto, long only).

Usage:
  export APCA_API_KEY_ID=... APCA_API_SECRET_KEY=...
  export GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD=...   # optional: email alerts to yourself
  python bot.py run                 # trading loop (paper or live, per app.trading_mode)
  python bot.py backtest            # backtest each symbol over historical_lookback_days
  python bot.py reset-kill-switch   # clear a max-drawdown halt (manual reset)
"""

import argparse
import json
import logging
import math
import os
import re
import smtplib
import time
import traceback
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


HERE = Path(__file__).parent
STATE_FILE = HERE / "state.json"
log = logging.getLogger("bot")
_last_alert = {}


def notify(subject, body="", cooldown=3600):
    """Email yourself via Gmail (needs an app password). No-op unless both env vars are set."""
    addr, password = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not addr or not password or time.time() - _last_alert.get(subject, 0) < cooldown:
        return
    _last_alert[subject] = time.time()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[trading bot] {subject}", addr, addr
    msg.set_content(body or subject)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(addr, password)
            smtp.send_message(msg)
    except Exception:
        log.exception("alert email failed")  # never let alerting stop trading


# ---------- config ----------


def load_config(path):
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg["app"]["trading_mode"] not in ("paper", "live"):
        raise SystemExit("app.trading_mode must be 'paper' or 'live'")
    if cfg["broker"]["provider"] != "alpaca":
        raise SystemExit("only broker.provider 'alpaca' is supported")
    if cfg["strategy"]["name"] != "trend_momentum":
        raise SystemExit("only strategy.name 'trend_momentum' is implemented")
    if cfg["strategy"]["allow_short_selling"]:
        raise SystemExit("short selling is not implemented; set allow_short_selling: false")
    if cfg["ai"]["enabled"]:
        raise SystemExit("the AI layer is not implemented; set ai.enabled: false")
    if cfg["risk"]["stop_loss"]["method"] not in ("atr", "percent"):
        raise SystemExit("risk.stop_loss.method must be 'atr' or 'percent'")
    if cfg["risk"]["take_profit"]["method"] not in ("risk_multiple", "percent"):
        raise SystemExit("risk.take_profit.method must be 'risk_multiple' or 'percent'")
    return cfg


def bar_minutes(timeframe):
    m = re.fullmatch(r"(\d+)(Min|Hour|Day)", timeframe)
    if not m:
        raise SystemExit(
            f"unsupported market.timeframe {timeframe!r} (use e.g. 15Min, 1Hour, 1Day)"
        )
    return int(m[1]) * {"Min": 1, "Hour": 60, "Day": 1440}[m[2]]


# ---------- strategy (pure, testable) ----------


def add_indicators(df):
    c = df["close"]
    df["SMA_20"] = c.rolling(20).mean()
    df["SMA_50"] = c.rolling(50).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["RSI_14"] = 100 - 100 / (1 + gain / loss)
    prev = c.shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    df["ATR_14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    # Score in 0..1: price above SMA20, SMA20 above SMA50, RSI momentum (30 -> 0, 70+ -> 1).
    rsi_part = ((df["RSI_14"] - 30) / 40).clip(0, 1)
    df["score"] = (
        (c > df["SMA_20"]).astype(float) + (df["SMA_20"] > df["SMA_50"]).astype(float) + rsi_part
    ) / 3
    df.loc[df["SMA_50"].isna() | df["RSI_14"].isna(), "score"] = np.nan
    return df


def signals(df, cfg):
    """'buy' / 'sell' / 'hold' per bar, using only that bar and earlier ones."""
    s = cfg["strategy"]
    n = s["confirmation_bars"] if s["require_signal_confirmation"] else 1
    buy = (df["score"] >= s["buy_threshold"]).astype(float).rolling(n).min() == 1
    sell = (df["score"] <= s["sell_threshold"]).astype(float).rolling(n).min() == 1
    return pd.Series(np.select([buy, sell], ["buy", "sell"], "hold"), index=df.index)


def exit_levels(entry, atr, cfg):
    sl, tp = cfg["risk"]["stop_loss"], cfg["risk"]["take_profit"]
    max_dist = entry * sl["max_pct"] / 100
    dist = min(atr * sl["atr_multiplier"], max_dist) if sl["method"] == "atr" else max_dist
    target_dist = (
        dist * tp["risk_multiple"] if tp["method"] == "risk_multiple" else entry * tp["pct"] / 100
    )
    return entry - dist, entry + target_dist


def position_qty(equity, exposure, n_open, entry, stop, cfg, whole):
    r = cfg["risk"]
    if n_open >= r["max_open_positions"] or entry <= stop:
        return 0
    by_risk = equity * r["risk_per_trade_pct"] / 100 / (entry - stop) * entry
    notional = min(
        by_risk,
        equity * r["max_position_pct"] / 100,
        cfg["execution"]["max_order_value_usd"],
        equity * r["max_total_exposure_pct"] / 100 - exposure,
    )
    if notional <= 0:
        return 0
    return math.floor(notional / entry) if whole else math.floor(notional / entry * 1e6) / 1e6


# ---------- backtest ----------


def backtest(df, cfg, whole):
    """Signal on bar i-1 close, fill at bar i open (no lookahead).

    If stop and target are hit in the same bar, the stop wins (conservative).
    """
    b = cfg["backtest"]
    com, slip = b["commission_pct"] / 100, b["slippage_pct"] / 100
    df = add_indicators(df.copy())
    sig = signals(df, cfg).to_numpy()
    o, h, lo, c, atr = (df[k].to_numpy() for k in ("open", "high", "low", "close", "ATR_14"))
    cash, qty, stop, target, entry_cost = float(b["initial_capital"]), 0, 0.0, 0.0, 0.0
    pnls, curve = [], []
    for i in range(1, len(df)):
        if not qty and sig[i - 1] == "buy":
            entry = o[i] * (1 + slip)
            stop, target = exit_levels(entry, atr[i - 1], cfg)
            qty = position_qty(cash, 0, 0, entry, stop, cfg, whole)
            entry_cost = qty * entry * (1 + com)
            cash -= entry_cost
        if qty:
            px = None
            if sig[i - 1] == "sell" or o[i] <= stop or o[i] >= target:
                px = o[i]
            elif lo[i] <= stop:
                px = stop
            elif h[i] >= target:
                px = target
            if px is not None:
                proceeds = qty * px * (1 - slip) * (1 - com)
                cash += proceeds
                pnls.append(proceeds - entry_cost)
                qty = 0
        curve.append(cash + qty * c[i])
    curve = np.array(curve) if curve else np.array([float(b["initial_capital"])])
    peak = np.maximum.accumulate(curve)
    return {
        "trades": len(pnls),
        "win_rate_pct": round(100 * sum(p > 0 for p in pnls) / len(pnls), 1) if pnls else 0.0,
        "return_pct": round(100 * (curve[-1] / b["initial_capital"] - 1), 2),
        "max_drawdown_pct": round(100 * ((peak - curve) / peak).max(), 2),
    }


# ---------- state ----------


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# ---------- live trading ----------


class Bot:
    def __init__(self, cfg):
        from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        self.cfg = cfg
        key, secret = os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise SystemExit("set APCA_API_KEY_ID and APCA_API_SECRET_KEY")
        paper = cfg["app"]["trading_mode"] == "paper"
        # Alpaca paper key IDs start with PK, live ones with AK.
        if cfg["broker"]["verify_keys_match_mode"] and key.startswith("PK") != paper:
            raise SystemExit(
                f"API keys do not match trading_mode {cfg['app']['trading_mode']!r}; refusing"
            )
        self.trading = TradingClient(key, secret, paper=paper)
        self.stock_data = StockHistoricalDataClient(key, secret)
        self.crypto_data = CryptoHistoricalDataClient(key, secret)
        self.minutes = bar_minutes(cfg["market"]["timeframe"])
        m = cfg["market"]
        self.symbols = (m["stock_symbols"] if "stocks" in m["asset_classes"] else []) + (
            m["crypto_symbols"] if "crypto" in m["asset_classes"] else []
        )

    def bars(self, symbol, days):
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        tf = (
            TimeFrame(self.minutes, TimeFrameUnit.Minute)
            if self.minutes < 60
            else (
                TimeFrame(self.minutes // 60, TimeFrameUnit.Hour)
                if self.minutes < 1440
                else TimeFrame.Day
            )
        )
        start = datetime.now(UTC) - timedelta(days=days)
        if "/" in symbol:
            df = self.crypto_data.get_crypto_bars(
                CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start)
            ).df
        else:
            # IEX feed works on free accounts; SIP needs a paid data plan.
            df = self.stock_data.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=symbol, timeframe=tf, start=start, feed=DataFeed.IEX
                )
            ).df
        if df.empty:
            return df
        df = df.droplevel("symbol")
        if "/" not in symbol and self.minutes < 1440:
            df = df.tz_convert("America/New_York").between_time("09:30", "15:59").tz_convert("UTC")
        return df

    def kill_switch(self, state, equity, last_equity, positions):
        """Returns True when new trades are blocked."""
        r = self.cfg["risk"]
        ks = r["kill_switch"]
        if not ks["enabled"]:
            return False
        dd = 100 * (state["peak_equity"] - equity) / state["peak_equity"]
        if dd >= r["max_drawdown_pct"] and not state.get("halted"):
            state["halted"] = True
            log.critical(
                "max drawdown %.2f%% hit: halted until `python bot.py reset-kill-switch`", dd
            )
            if ks["on_max_drawdown"]["close_positions"]:
                self.trading.close_all_positions(cancel_orders=True)
            notify("KILL SWITCH: max drawdown hit", f"Drawdown {dd:.2f}%. Trading halted.")
        if state.get("halted"):
            return ks["on_max_drawdown"]["block_new_trades"]
        # last_equity is the previous session's close, so this resets next trading day by itself.
        daily = 100 * (last_equity - equity) / last_equity
        if daily >= r["max_daily_loss_pct"]:
            log.warning("daily loss %.2f%% hit: no new trades today", daily)
            notify(
                f"daily loss limit hit {datetime.now(UTC).date()}",
                f"Down {daily:.2f}% today.",
                86400,
            )
            if ks["on_daily_loss_limit"]["close_positions"] and positions:
                self.trading.close_all_positions(cancel_orders=True)
            return ks["on_daily_loss_limit"]["block_new_trades"]
        return False

    def exit(self, symbol, open_orders):
        for o in open_orders:
            if o.symbol.replace("/", "") == symbol.replace("/", ""):
                self.trading.cancel_order_by_id(o.id)
        # Market exit for certainty; if bracket legs are still cancelling, this fails and retries.
        self.trading.close_position(symbol.replace("/", ""))
        log.info("exit %s", symbol)
        notify(f"exit {symbol}", cooldown=0)

    def enter(self, symbol, price, atr, equity, exposure, n_open, state):
        """Returns the notional ordered (0 if skipped)."""
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        crypto = "/" in symbol
        stop, target = exit_levels(price, atr, self.cfg)
        qty = position_qty(equity, exposure, n_open, price, stop, self.cfg, whole=not crypto)
        if qty <= 0:
            log.info("skip %s: size rounds to 0 under risk caps", symbol)
            return 0
        ex = self.cfg["execution"]["crypto" if crypto else "stocks"]
        extra = {}
        if not crypto:
            # Server-side bracket keeps the stop alive if the bot dies (none for crypto).
            extra = {
                "order_class": OrderClass.BRACKET,
                "take_profit": TakeProfitRequest(limit_price=round(target, 2)),
                "stop_loss": StopLossRequest(stop_price=round(stop, 2)),
            }
        common = dict(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce(ex["time_in_force"]),
            **extra,
        )
        if ex["order_type"] == "limit":
            limit = round(price * (1 + ex.get("limit_offset_pct", 0) / 100), 2)
            req = LimitOrderRequest(limit_price=limit, **common)
        else:
            req = MarketOrderRequest(**common)
        self.trading.submit_order(req)
        if crypto:
            state.setdefault("exits", {})[symbol.replace("/", "")] = {
                "stop": stop,
                "target": target,
            }
        log.info("buy %s qty=%s ~%.2f stop=%.2f target=%.2f", symbol, qty, price, stop, target)
        notify(f"buy {symbol}", f"qty={qty} ~{price:.2f} stop={stop:.2f} target={target:.2f}", 0)
        return qty * price

    def step(self):
        from alpaca.trading.enums import AssetClass, QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        cfg = self.cfg
        acct = self.trading.get_account()
        equity, last_equity = float(acct.equity), float(acct.last_equity)
        state = load_state()
        state["peak_equity"] = max(state.get("peak_equity") or equity, equity)
        positions = {p.symbol: p for p in self.trading.get_all_positions()}
        exposure = sum(abs(float(p.market_value)) for p in positions.values())
        n_open = len(positions)
        open_orders = self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))

        cutoff = datetime.now(UTC) - timedelta(
            minutes=cfg["execution"]["crypto"]["cancel_unfilled_after_minutes"]
        )
        for o in open_orders:
            if o.asset_class == AssetClass.CRYPTO and o.created_at < cutoff:
                self.trading.cancel_order_by_id(o.id)
                log.info("cancelled unfilled %s order %s", o.symbol, o.id)

        blocked = self.kill_switch(state, equity, last_equity, positions)
        market_open = self.trading.get_clock().is_open
        now = datetime.now(UTC)

        for symbol in self.symbols:
            try:
                crypto = "/" in symbol
                key = symbol.replace("/", "")
                if (
                    not crypto
                    and cfg["execution"]["stocks"]["enforce_market_hours"]
                    and not market_open
                ):
                    continue
                raw = self.bars(symbol, days=10)
                if raw.empty:
                    continue
                price = float(raw["close"].iloc[-1])  # latest, possibly still-forming bar
                closed = (
                    raw[raw.index + timedelta(minutes=self.minutes) <= now]
                    if cfg["market"]["act_on_closed_bars_only"]
                    else raw
                )
                df = add_indicators(closed.copy())
                sig = signals(df, cfg).iloc[-1] if len(df) else "hold"

                if key in positions:
                    lv = state.get("exits", {}).get(key)
                    if sig == "sell" or (crypto and lv and not lv["stop"] < price < lv["target"]):
                        self.exit(symbol, open_orders)
                        state.get("exits", {}).pop(key, None)
                    continue
                pending = any(o.symbol.replace("/", "") == key for o in open_orders)
                if blocked or (pending and not cfg["execution"]["allow_duplicate_orders"]):
                    continue
                if sig == "buy":
                    placed = self.enter(
                        symbol, price, float(df["ATR_14"].iloc[-1]), equity, exposure, n_open, state
                    )
                    if placed:  # count it toward the caps for the rest of this loop
                        exposure += placed
                        n_open += 1
            except Exception:
                log.exception("error on %s", symbol)
                notify(f"error on {symbol}", traceback.format_exc())
        save_state(state)

    def run(self):
        mode = self.cfg["app"]["trading_mode"].upper()
        log.info("starting in %s mode: %s", mode, self.symbols)
        notify(f"bot started in {mode} mode", cooldown=0)
        while True:
            try:
                self.step()
            except Exception:
                log.exception("step failed; retrying next loop")
                notify("step failed", traceback.format_exc())
            time.sleep(self.cfg["market"]["refresh_seconds"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["run", "backtest", "reset-kill-switch"])
    p.add_argument("--config", default=HERE / "config.yaml")
    args = p.parse_args()
    cfg = load_config(args.config)
    logging.basicConfig(
        level=cfg["app"]["log_level"], format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.command == "reset-kill-switch":
        state = load_state()
        state.update(halted=False, peak_equity=None)  # peak restarts from current equity
        save_state(state)
        print("kill switch reset")
        return
    bot = Bot(cfg)
    if args.command == "run":
        bot.run()
    else:
        days = cfg["market"]["historical_lookback_days"]
        bench = bot.bars(cfg["backtest"]["benchmark"], days)
        if not bench.empty:
            ret = 100 * (bench.close.iloc[-1] / bench.open.iloc[0] - 1)
            print(f"benchmark {cfg['backtest']['benchmark']} buy&hold: {ret:.2f}%")
        for symbol in bot.symbols:
            df = bot.bars(symbol, days)
            print(symbol, backtest(df, cfg, whole="/" not in symbol) if len(df) else "no data")


if __name__ == "__main__":
    main()
