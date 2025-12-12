"""
LightPriceActionLayer: emits BUY/SELL with relaxed but guarded PA checks when other layers are flat.
"""

from __future__ import annotations

from typing import Any, Dict

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


class LightPriceActionLayer:
    def evaluate(self, df_5m, ctx: Dict[str, Any], discretionary_ctx: Dict[str, Any], bias: str, breakout_filter_active: bool = False) -> Dict[str, Any]:
        if df_5m is None or len(df_5m) < 20:
            return {"action": "NO_TRADE", "reason": "light_pa_insufficient_data"}

        last = df_5m.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])

        rng = max(high - low, 1e-8)
        body = abs(close - open_)
        upper_wick = high - max(open_, close)
        lower_wick = min(open_, close) - low
        body_ratio = body / rng if rng else 0

        sweeps = ctx.get("sweeps", {})
        sweep_5m = sweeps.get("5m", {}) or {}
        structure_5m = ctx.get("structure_shifts", {}).get("5m", {}) or {}
        structure_dir = structure_5m.get("direction")
        momentum_bias = discretionary_ctx.get("momentum_bias", "neutral")

        swings = se._local_swings(df_5m, lookback=100, window=2)
        last_swing_high = swings.get("highs", [])[-1]["price"] if swings.get("highs") else None
        last_swing_low = swings.get("lows", [])[-1]["price"] if swings.get("lows") else None

        atr = None
        for col in ("atr", "atr_14", "ATR", "ATR_14"):
            if col in df_5m.columns:
                try:
                    atr = float(df_5m[col].iloc[-1])
                    break
                except Exception:
                    atr = None
        if atr is None:
            atr = _atr_14(df_5m)

        action = "NO_TRADE"
        entry = close
        sl = tp1 = tp2 = tp3 = None

        # Light BUY: bullish structure or higher close than last swing high, healthy body, no bearish sweep, bias not opposite
        bearish_gate = (bias != "BUY ONLY" and ( structure_dir == "bearish" or (last_swing_low and close < last_swing_low) or  momentum_bias in ("building_bearish", "strong_bearish")))

        momentum_gate_bull = momentum_bias in ("building_bullish", "strong_bullish", "neutral")
        no_bear_absorb = upper_wick <= body * 1.6
        bull_pullback_ok = (high - close) <= rng * 0.45
        bear_sweep = sweep_5m.get("type") == "above"

        if (
            bullish_gate
            and body_ratio >= 0.35
            and momentum_gate_bull
            and no_bear_absorb
            and bull_pullback_ok
            (and not (bull_sweep and momentum_bias != "strong_bearish"))
        ):
            action = "BUY"
            sl = entry - (atr * 1.8)
            tp1 = entry + (atr * 1.2)
            tp2 = entry + (atr * 2.0)
            tp3 = entry + (atr * 3.0)

        # Light SELL: bearish structure or close below last swing low, healthy body, no bullish sweep, bias not opposite, respect breakout filter
        if action == "NO_TRADE":
            bearish_gate = bias != "BUY ONLY" and (structure_dir == "bearish" or (last_swing_low and close < last_swing_low) or momentum_bias in ("building_bearish", "strong_bearish"))
            momentum_gate_bear = momentum_bias in ("building_bearish", "strong_bearish", "neutral")
            no_bull_absorb = lower_wick <= body * 1.6
            bear_pullback_ok = (close - low) <= rng * 0.45
            bull_sweep = sweep_5m.get("type") == "below"

            if (
                bearish_gate
                and body_ratio >= 0.35
                and momentum_gate_bear
                and no_bull_absorb
                and bear_pullback_ok
                and not bull_sweep
                and (not breakout_filter_active or momentum_bias == "strong_bearish")
            ):
                action = "SELL"
                sl = entry + (atr * 1.8)
                tp1 = entry - (atr * 1.2)
                tp2 = entry - (atr * 2.0)
                tp3 = entry - (atr * 3.0)

        if action == "NO_TRADE":
            return {"action": "NO_TRADE", "reason": "light_pa_no_setup"}

        return {
            "action": action,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp": round(tp1, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "confidence": 52,
            "reason": "light_price_action",
        }
