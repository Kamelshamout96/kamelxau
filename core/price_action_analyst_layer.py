"""
PriceActionAnalystLayer: discretionary-style intraday read to allow BUY/SELL when Stage 2 and fallback are flat.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

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


def _body_stats(candle) -> Tuple[float, float, float, float]:
    open_, high, low, close = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
    rng = max(high - low, 1e-8)
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body, rng, upper_wick, lower_wick


def _market_bias(swings: Dict[str, List[Dict[str, Any]]], momentum_bias: str) -> str:
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    bias = "mixed"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"] > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"] < lows[-2]["price"]
        if hh and hl:
            bias = "bullish"
        elif lh and ll:
            bias = "bearish"
    if "strong_bullish" in momentum_bias or "building_bullish" in momentum_bias:
        return "bullish" if bias != "bearish" else "mixed"
    if "strong_bearish" in momentum_bias or "building_bearish" in momentum_bias:
        return "bearish" if bias != "bullish" else "mixed"
    return bias


def _micro_zones(swings: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    micro_supply = {"zone": None, "strength": "weak"}
    micro_demand = {"zone": None, "strength": "weak"}
    if highs:
        h = highs[-1]["price"]
        micro_supply = {"zone": {"low": h * 0.998, "high": h * 1.002}, "strength": "normal"}
    if lows:
        l = lows[-1]["price"]
        micro_demand = {"zone": {"low": l * 0.998, "high": l * 1.002}, "strength": "normal"}
    return {"micro_supply": micro_supply, "micro_demand": micro_demand}


def _liquidity_event(df, swings: Dict[str, List[Dict[str, Any]]]) -> str:
    if len(df) < 3:
        return "none"
    last = df.iloc[-1]
    prev_high = swings.get("highs", [])[-1]["price"] if swings.get("highs") else None
    prev_low = swings.get("lows", [])[-1]["price"] if swings.get("lows") else None
    if prev_high is not None and float(last["high"]) > prev_high and float(last["close"]) < prev_high:
        return "high_sweep"
    if prev_low is not None and float(last["low"]) < prev_low and float(last["close"]) > prev_low:
        return "low_sweep"
    return "none"


def _momentum_shift(df) -> str:
    if len(df) < 4:
        return "neutral"
    closes = df["close"].iloc[-4:].tolist()
    if closes[-3] < closes[-2] < closes[-1]:
        return "momentum_up"
    if closes[-3] > closes[-2] > closes[-1]:
        return "momentum_down"
    return "neutral"


def _pattern_detected(df, micro_zones: Dict[str, Any], liquidity_event: str, momentum_shift: str) -> str:
    last = df.iloc[-1]
    body, rng, upper_wick, lower_wick = _body_stats(last)
    close = float(last["close"])
    open_ = float(last["open"])
    in_demand = False
    in_supply = False
    demand = micro_zones.get("micro_demand", {}).get("zone") or {}
    supply = micro_zones.get("micro_supply", {}).get("zone") or {}
    if demand:
        in_demand = demand["low"] <= close <= demand["high"]
    if supply:
        in_supply = supply["low"] <= close <= supply["high"]

    if liquidity_event in ("high_sweep", "low_sweep"):
        return "liquidity_grab_reversal"
    if in_demand and lower_wick > body * 1.5:
        return "bounce_from_demand"
    if in_supply and upper_wick > body * 1.5:
        return "rejection_from_supply"
    if body / rng < 0.25 and upper_wick > body * 2 and close > open_:
        return "exhaustion_top"
    if momentum_shift in ("momentum_up", "momentum_down"):
        return "micro_pullback_continuation"
    if body / rng < 0.25:
        return "range_compression"
    return "none"


class PriceActionAnalystLayer:
    def evaluate(self, df_5m, ctx: Dict[str, Any], discretionary_ctx: Dict[str, Any], bias: str, breakout_filter_active: bool = False) -> Dict[str, Any]:
        if df_5m is None or len(df_5m) < 30:
            return {"action": "NO_TRADE", "reason": "price_action", "entry": None, "sl": None, "tp": None, "tp1": None, "tp2": None, "tp3": None, "confidence": 0}

        last = df_5m.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        body, rng, upper_wick, lower_wick = _body_stats(last)
        body_ratio = body / rng if rng else 0

        swings = se._local_swings(df_5m, lookback=120, window=2)
        momentum_bias = discretionary_ctx.get("momentum_bias", "neutral")
        market_bias = _market_bias(swings, momentum_bias)
        liquidity_event = _liquidity_event(df_5m, swings)
        momentum_shift = _momentum_shift(df_5m)
        micro_zones = _micro_zones(swings)
        pattern = _pattern_detected(df_5m, micro_zones, liquidity_event, momentum_shift)

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

        def _no_trade(reason: str) -> Dict[str, Any]:
            return {
                "action": "NO_TRADE",
                "entry": None,
                "sl": None,
                "tp": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
                "confidence": 0,
                "reason": reason,
            }

        action = "NO_TRADE"
        entry = close
        sl = tp1 = tp2 = tp3 = None

        # BUY criteria
        buy_ok = (
            last_swing_high is not None
            and close > last_swing_high
            and body_ratio >= 0.6
            and momentum_bias in ("building_bullish", "strong_bullish")
            and upper_wick <= body
            and (high - close) <= rng * 0.3
            and bias != "SELL ONLY"
            and ctx.get("breakout_hh", False)
        )

        supply_zone = (ctx.get("zones", {}).get("supply") or {}).get("zone") or {}
        if supply_zone:
            supply_block = supply_zone.get("low") is not None and close >= supply_zone.get("low", 0) - atr * 0.2
        else:
            supply_block = False

        if buy_ok and not supply_block:
            action = "BUY"
            sl = entry - (atr * 2.0)
            tp1 = entry + (atr * 1.5)
            tp2 = entry + (atr * 2.5)
            tp3 = entry + (atr * 3.5)

        # SELL criteria
        demand_zone = (ctx.get("zones", {}).get("demand") or {}).get("zone") or {}
        sell_ok = (
            last_swing_low is not None
            and close < last_swing_low
            and body_ratio >= 0.6
            and momentum_bias in ("building_bearish", "strong_bearish")
            and lower_wick <= body
            and (close - low) <= rng * 0.3
            and bias != "BUY ONLY"
        )
        if demand_zone:
            demand_block = demand_zone.get("high") is not None and close <= demand_zone.get("high", 0) + atr * 0.2
        else:
            demand_block = False

        if action == "NO_TRADE" and sell_ok and not demand_block:
            action = "SELL"
            sl = entry + (atr * 2.0)
            tp1 = entry - (atr * 1.5)
            tp2 = entry - (atr * 2.5)
            tp3 = entry - (atr * 3.5)

        reasoning = [
            f"Market bias: {market_bias}",
            f"Momentum bias: {momentum_bias}",
            f"Pattern: {pattern}",
            f"Liquidity event: {liquidity_event}",
        ]

        if action == "NO_TRADE":
            return {
                "action": "NO_TRADE",
                "entry": None,
                "sl": None,
                "tp": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
                "confidence": 0,
                "reason": "price_action",
                "trend": {},
                "structure": {},
                "liquidity": {},
                "zones": {},
                "momentum": momentum_bias,
                "channels": ctx.get("channel", {}),
                "reasoning": reasoning,
                "score_breakdown": {},
                "discretionary_context": {
                    "market_bias": market_bias,
                    "pattern_detected": pattern,
                    "liquidity_event": liquidity_event,
                    "micro_zones": micro_zones,
                    "momentum_shift": momentum_shift,
                    "explanation": "No actionable price-action breakout found.",
                },
            }

        signal = {
            "action": action,
            "entry": round(entry, 2),
            "sl": round(sl, 2) if sl is not None else None,
            "tp": round(tp1, 2) if tp1 is not None else None,
            "tp1": round(tp1, 2) if tp1 is not None else None,
            "tp2": round(tp2, 2) if tp2 is not None else None,
            "tp3": round(tp3, 2) if tp3 is not None else None,
            "confidence": 55,
            "reason": "price_action",
            "trend": {
                "4h": ctx.get("bias_context", {}).get("htf_structure", {}).get("4h", {}).get("bias", "neutral"),
                "1h": ctx.get("bias_context", {}).get("htf_structure", {}).get("1h", {}).get("bias", "neutral"),
                "15m": ctx.get("structure_shifts", {}).get("15m", {}).get("direction"),
                "5m": ctx.get("structure_shifts", {}).get("5m", {}).get("direction"),
            },
            "structure": ctx.get("structure_shifts", {}),
            "liquidity": {
                "sweep": ctx.get("sweeps", {}).get("15m", {}).get("type") or ctx.get("sweeps", {}).get("5m", {}).get("type"),
                "levels": ctx.get("pools", {}),
            },
            "zones": ctx.get("zones", {}),
            "momentum": momentum_bias,
            "channels": ctx.get("channel", {}),
            "reasoning": reasoning,
            "score_breakdown": {
                "structure": 20 if ctx.get("structure_shifts", {}).get("5m", {}).get("direction") else 0,
                "liquidity": 15 if ctx.get("sweeps", {}).get("5m", {}).get("type") else 0,
                "zones": 15 if ctx.get("zones") else 0,
                "momentum": 25 if momentum_bias.startswith(("building", "strong")) else 10,
                "pattern": 15 if pattern != "none" else 0,
                "htf_context": 10 if bias != "NEUTRAL" else 0,
            },
            "discretionary_context": {
                "market_bias": market_bias,
                "pattern_detected": pattern,
                "liquidity_event": liquidity_event,
                "micro_zones": micro_zones,
                "momentum_shift": momentum_shift,
                "explanation": "Human-style PA read confirming breakout/momentum continuation.",
            },
        }

        return signal
