"""
MomentumBreakoutBuyEngine: emits BUY-only momentum breakout signals after Stage 2.
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


class MomentumBreakoutBuyEngine:
    def __init__(self, atr_period: int = 14) -> None:
        self.atr_period = atr_period

    def evaluate(self, df_5m, ctx: Dict[str, Any], discretionary: Dict[str, Any]) -> Dict[str, Any] | None:
        if df_5m is None or len(df_5m) < 15:
            return None

        bias = ctx.get("bias", "NEUTRAL")
        if bias == "SELL ONLY":
            return None

        last = df_5m.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        prev_high = float(df_5m["high"].iloc[-2]) if len(df_5m) >= 2 else None

        body = abs(close - open_)
        rng = max(high - low, 1e-8)
        if rng == 0 or (body / rng) < 0.2:
            return None

        structure_bull = (ctx.get("structure_shifts", {}).get("5m", {}) or {}).get("direction") == "bullish"
        disc_breakout = discretionary.get("breakout_status") == "bullish_breakout"
        price_breakout = prev_high is not None and close > prev_high + 0.30
        breakout_ok = structure_bull or disc_breakout or price_breakout
        if not breakout_ok:
            return None

        momentum_bias = discretionary.get("momentum_bias", "neutral")
        if momentum_bias not in ("building_bullish", "strong_bullish"):
            return None

        trend_direction = discretionary.get("trend_direction", "neutral")
        if trend_direction not in ("bullish", "expanding"):
            return None

        sweep_type = (ctx.get("sweeps", {}).get("5m", {}) or {}).get("type")
        if sweep_type == "above":
            return None

        swings = se._local_swings(df_5m, lookback=80, window=2)
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

        if last_swing_low is not None and (close - last_swing_low) > atr * 8:
            return None

        supply_zone = (ctx.get("zones", {}).get("supply") or {}).get("zone") or {}
        supply_low = supply_zone.get("low")
        if supply_low is not None and (supply_low - close) < atr * 0.5:
            return None

        entry = close
        sl = entry - (atr * 1.8)
        tp1 = entry + (atr * 1.2)
        tp2 = entry + (atr * 2.0)
        tp3 = entry + (atr * 3.0)

        return {
            "action": "BUY",
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp": round(tp1, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "confidence": 72,
            "reason": "momentum_breakout_buy",
        }
