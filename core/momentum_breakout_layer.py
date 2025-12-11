"""
MomentumBreakoutLayer: captures strong momentum breakouts without POI/sweep requirements.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from . import pa_utils as se


def _atr_14(df):
    import numpy as np
    import pandas as pd

    tr = np.maximum.reduce(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ]
    )
    return float(pd.Series(tr, index=df.index).rolling(14).mean().iloc[-1])


def _get_atr(df, ctx: Dict[str, Any]) -> float:
    ctx_indicators = ctx.get("indicators", {}) if ctx else {}
    atr = ctx_indicators.get("atr_5m")
    if atr:
        try:
            return float(atr)
        except Exception:
            atr = None

    atr = None
    for col in ("atr", "atr_14", "ATR", "ATR_14"):
        if col in df.columns:
            try:
                atr = float(df[col].iloc[-1])
                break
            except Exception:
                atr = None
    if atr is None:
        atr = _atr_14(df)
    return float(atr)


def _body_ratio(candle) -> Tuple[float, float, float, float]:
    open_, high, low, close = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
    rng = max(high - low, 1e-8)
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body / rng, upper_wick, lower_wick, rng


def _increasing_closes(df, direction: str) -> bool:
    if len(df) < 3:
        return False
    closes = df["close"].iloc[-3:].tolist()
    if direction == "bull":
        return closes[0] < closes[1] < closes[2]
    return closes[0] > closes[1] > closes[2]


class MomentumBreakoutLayer:
    def evaluate(self, df_5m, ctx: Dict[str, Any], discretionary_ctx: Dict[str, Any], bias: str, breakout_filter_active: bool = False) -> Dict[str, Any]:
        if df_5m is None or len(df_5m) < 3:
            return {"action": "NO_TRADE", "reason": "insufficient_data"}

        last = df_5m.iloc[-1]
        momentum_bias = (discretionary_ctx or {}).get("momentum_bias", "neutral")
        channel_bounds = (ctx.get("channel") or {}).get("bounds") or {}
        pools = ctx.get("pools", {}) or {}
        structures = ctx.get("structure_shifts", {}) or {}
        sweeps = ctx.get("sweeps", {}) or {}

        body_ratio, upper_wick, lower_wick, rng = _body_ratio(last)
        if rng <= 0:
            return {"action": "NO_TRADE", "reason": "no_range"}
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])

        swings = se._local_swings(df_5m, lookback=80, window=2)
        last_swing_high = swings.get("highs", [])[-1]["price"] if swings.get("highs") else None
        last_swing_low = swings.get("lows", [])[-1]["price"] if swings.get("lows") else None

        liq_high = max(pools.get("highs", [])) if pools.get("highs") else None
        liq_low = min(pools.get("lows", [])) if pools.get("lows") else None
        ch_upper = channel_bounds.get("upper")
        ch_lower = channel_bounds.get("lower")

        breakout_buy_level = max(v for v in [last_swing_high, liq_high, ch_upper] if v is not None) if any(v is not None for v in [last_swing_high, liq_high, ch_upper]) else None
        breakout_sell_level = min(v for v in [last_swing_low, liq_low, ch_lower] if v is not None) if any(v is not None for v in [last_swing_low, liq_low, ch_lower]) else None

        strong_body = body_ratio >= 0.6
        bull_breakout = breakout_buy_level is not None and close > breakout_buy_level and strong_body
        bear_breakout = breakout_sell_level is not None and close < breakout_sell_level and strong_body

        inc_bull = _increasing_closes(df_5m, "bull")
        inc_bear = _increasing_closes(df_5m, "bear")

        no_bear_absorb = upper_wick <= abs(close - open_)  # limit bearish absorption on breakout candle
        no_bull_absorb = lower_wick <= abs(close - open_)  # limit bullish absorption on breakout candle

        # Micro pullback: ensure current candle did not retrace more than 30% of its range
        bull_pullback_ok = (high - close) <= rng * 0.3 if close >= open_ else False
        bear_pullback_ok = (close - low) <= rng * 0.3 if close <= open_ else False

        atr = _get_atr(df_5m, ctx)

        def _make_signal(action: str, entry_price: float) -> Dict[str, Any]:
            if action == "BUY":
                sl = entry_price - (atr * 2.0)
                tp1 = entry_price + (atr * 1.5)
                tp2 = entry_price + (atr * 2.5)
                tp3 = entry_price + (atr * 3.5)
            else:
                sl = entry_price + (atr * 2.0)
                tp1 = entry_price - (atr * 1.5)
                tp2 = entry_price - (atr * 2.5)
                tp3 = entry_price - (atr * 3.5)
            return {
                "action": action,
                "entry": round(entry_price, 2),
                "sl": round(sl, 2),
                "tp": round(tp1, 2),
                "tp1": round(tp1, 2),
                "tp2": round(tp2, 2),
                "tp3": round(tp3, 2),
                "confidence": 55,
                "reason": "momentum_breakout",
            }

        # Bias gating
        def _bias_allows(action: str) -> bool:
            if bias == "NEUTRAL":
                return True
            if action == "BUY" and bias == "SELL ONLY":
                return False
            if action == "SELL" and bias == "BUY ONLY":
                return False
            return True

        # Discretionary rejection gating
        def _has_strong_counter_rejection(action: str) -> bool:
            reaction = (discretionary_ctx or {}).get("reaction")
            zone_type = (discretionary_ctx or {}).get("zone_type")
            zone_strength = (discretionary_ctx or {}).get("zone_strength", "weak")
            if action == "BUY" and reaction == "rejection" and zone_type == "supply" and zone_strength == "strong":
                return True
            if action == "SELL" and reaction == "rejection" and zone_type == "demand" and zone_strength == "strong":
                return True
            return False

        def _has_counter_breakout(action: str) -> bool:
            breakout_status = (discretionary_ctx or {}).get("breakout_status")
            if action == "BUY" and breakout_status == "bearish_breakout":
                return True
            if action == "SELL" and breakout_status == "bullish_breakout":
                return True
            return False

        if breakout_filter_active and bear_breakout:
            bear_breakout = False

        if (
            bull_breakout
            and inc_bull
            and no_bear_absorb
            and bull_pullback_ok
            and momentum_bias in ("building_bullish", "strong_bullish")
        ):
            if _bias_allows("BUY") and not _has_strong_counter_rejection("BUY") and not _has_counter_breakout("BUY"):
                return _make_signal("BUY", close)

        if (
            bear_breakout
            and inc_bear
            and no_bull_absorb
            and bear_pullback_ok
            and momentum_bias in ("building_bearish", "strong_bearish")
        ):
            if _bias_allows("SELL") and not _has_strong_counter_rejection("SELL") and not _has_counter_breakout("SELL"):
                return _make_signal("SELL", close)

        return {"action": "NO_TRADE", "reason": "momentum_breakout_not_met"}
