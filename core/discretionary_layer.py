"""
DiscretionaryLayer: lightweight discretionary-style technical read.
Consumes recent price context only; does not emit trading instructions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import pa_utils as se


def _recent_swings(df, lookback: int = 120, window: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    swings = se._local_swings(df, lookback=lookback, window=window)
    return {"highs": swings.get("highs", []), "lows": swings.get("lows", [])}


def _trend_from_swings(swings: Dict[str, List[Dict[str, Any]]]) -> str:
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    if len(highs) < 2 or len(lows) < 2:
        return "consolidating"

    hh = highs[-1]["price"] > highs[-2]["price"]
    hl = lows[-1]["price"] > lows[-2]["price"]
    lh = highs[-1]["price"] < highs[-2]["price"]
    ll = lows[-1]["price"] < lows[-2]["price"]

    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "consolidating"


def _momentum_bias(df) -> str:
    if len(df) < 10:
        return "neutral"
    tail = df.tail(10)
    bodies = (tail["close"] - tail["open"]).abs()
    body_mean = float(bodies.mean())
    body_std = float(bodies.std() or 0)
    speed = float(tail["close"].iloc[-1] - tail["close"].iloc[0])
    direction = "bullish" if speed > 0 else ("bearish" if speed < 0 else "neutral")
    consistency = "steady" if body_mean and body_std / body_mean < 0.6 else "choppy"
    distance_pct = abs(speed) / float(tail["close"].iloc[0])

    if distance_pct > 0.006 and consistency == "steady":
        return f"strong_{direction}"
    if distance_pct > 0.003:
        return f"building_{direction}"
    return "neutral"


def _strong_body(candle) -> bool:
    body = abs(float(candle["close"]) - float(candle["open"]))
    rng = float(candle["high"]) - float(candle["low"])
    return rng > 0 and body / rng >= 0.6


def _breakout_and_retest(df, swings: Dict[str, List[Dict[str, Any]]]) -> Tuple[str, bool, str, float | None]:
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    last_c = df.iloc[-1]
    breakout = "none"
    level = None

    if len(highs) >= 2:
        level = highs[-1]["price"]
        if float(last_c["close"]) > level and _strong_body(last_c):
            breakout = "bullish_breakout"
    if breakout == "none" and len(lows) >= 2:
        level = lows[-1]["price"]
        if float(last_c["close"]) < level and _strong_body(last_c):
            breakout = "bearish_breakout"

    retest_found = False
    quality = "weak"
    if breakout != "none" and level is not None:
        window = df.tail(3)
        for _, c in window.iterrows():
            open_, high, low, close = map(float, (c["open"], c["high"], c["low"], c["close"]))
            body = abs(close - open_) or 1e-8
            lower_wick = open_ - low if open_ > close else close - low
            upper_wick = high - open_ if open_ > close else high - close

            if breakout == "bullish_breakout" and low <= level <= high and close > open_:
                if lower_wick > body * 1.5:
                    quality = "strong" if lower_wick > body * 2 else "normal"
                    retest_found = True
                    break
            if breakout == "bearish_breakout" and low <= level <= high and close < open_:
                if upper_wick > body * 1.5:
                    quality = "strong" if upper_wick > body * 2 else "normal"
                    retest_found = True
                    break

    return breakout, retest_found, quality, level


def _zone_reaction(df, zone: Dict[str, Any] | None) -> Tuple[str, str]:
    if not zone or not zone.get("zone"):
        return "none", "weak"
    bounds = zone["zone"]
    touches = zone.get("touches", 0)
    confidence = zone.get("confidence", 0)

    recent = df.tail(10)
    reaction = "none"
    strength = "weak"
    for _, c in recent.iterrows():
        open_, high, low, close = map(float, (c["open"], c["high"], c["low"], c["close"]))
        in_zone = low <= bounds.get("high", 0) and high >= bounds.get("low", 0)
        if not in_zone:
            continue
        body = abs(close - open_) or 1e-8
        upper_wick = high - max(open_, close)
        lower_wick = min(open_, close) - low
        big_body = body > 0 and body >= (abs(high - low) * 0.5)

        if lower_wick > body * 1.5 or upper_wick > body * 1.5:
            reaction = "rejection"
        if big_body and ((close > open_ and high >= bounds.get("high", 0)) or (close < open_ and low <= bounds.get("low", 0))):
            reaction = "absorption"
        break

    if reaction == "rejection":
        strength = "strong" if confidence >= 70 or touches >= 2 else "normal"
    elif reaction == "absorption":
        strength = "normal" if confidence >= 40 else "weak"
    else:
        strength = "weak" if confidence < 40 else "normal"

    return reaction, strength


def _liquidity_event(df, pools: Dict[str, Any]) -> str:
    highs = pools.get("highs") or []
    lows = pools.get("lows") or []
    current_high = float(df["high"].iloc[-1])
    current_low = float(df["low"].iloc[-1])

    event = "none"
    prev_high = highs[-1] if len(highs) else None
    prev_low = lows[-1] if len(lows) else None

    if prev_high is not None and current_high > float(prev_high):
        event = "high_sweep"
    if prev_low is not None and current_low < float(prev_low):
        event = "low_sweep"

    return event


class DiscretionaryLayer:
    def analyze(self, df_5m, ctx: Dict[str, Any]) -> Dict[str, Any]:
        if df_5m is None or len(df_5m) < 50:
            return {
                "trend_direction": "consolidating",
                "momentum_bias": "neutral",
                "breakout_status": "none",
                "retest_found": False,
                "retest_quality": "weak",
                "zone_type": "none",
                "zone_strength": "weak",
                "reaction": "none",
                "liquidity_event": "none",
                "liquidity_context": "unclear",
                "conclusion": "Insufficient data for discretionary read; fewer than 50 candles.",
            }

        swings = _recent_swings(df_5m)
        trend_direction = _trend_from_swings(swings)
        momentum_bias = _momentum_bias(df_5m)

        breakout_status, retest_found, retest_quality, breakout_level = _breakout_and_retest(df_5m, swings)

        zones_ctx = ctx.get("zones", {})
        demand_reaction, demand_strength = _zone_reaction(df_5m, zones_ctx.get("demand"))
        supply_reaction, supply_strength = _zone_reaction(df_5m, zones_ctx.get("supply"))

        reaction = "none"
        zone_type = "none"
        zone_strength = "weak"
        if demand_reaction != "none":
            reaction = demand_reaction
            zone_type = "demand"
            zone_strength = demand_strength
        elif supply_reaction != "none":
            reaction = supply_reaction
            zone_type = "supply"
            zone_strength = supply_strength

        liquidity_event = _liquidity_event(df_5m, ctx.get("pools", {}))
        liquidity_context = "unclear"
        if liquidity_event == "high_sweep":
            liquidity_context = "reversal" if trend_direction == "bearish" else "continuation"
        elif liquidity_event == "low_sweep":
            liquidity_context = "reversal" if trend_direction == "bullish" else "continuation"

        momentum_note = "expanding" if "strong" in momentum_bias else ("compressing" if "building" in momentum_bias else "balanced")
        breakout_note = "A breakout is underway." if breakout_status != "none" else "No decisive breakout seen."
        retest_note = (
            f"Retest at {round(breakout_level, 2)} with {retest_quality} quality."
            if retest_found and breakout_level
            else "Retest not yet confirmed."
        )
        zone_note = (
            f"Recent {zone_type} zone shows {reaction} with {zone_strength} strength."
            if zone_type != "none"
            else "No active demand/supply reaction detected."
        )
        liq_note = (
            f"Liquidity {liquidity_event} suggesting {liquidity_context} context."
            if liquidity_event != "none"
            else "No fresh liquidity sweep noted."
        )

        conclusion = (
            f"Structure leans {trend_direction}; momentum is {momentum_note}. "
            f"{breakout_note} {retest_note} {zone_note} {liq_note}"
        )

        return {
            "trend_direction": trend_direction,
            "momentum_bias": momentum_bias,
            "breakout_status": breakout_status,
            "retest_found": retest_found,
            "retest_quality": retest_quality,
            "zone_type": zone_type,
            "zone_strength": zone_strength,
            "reaction": reaction,
            "liquidity_event": liquidity_event,
            "liquidity_context": liquidity_context,
            "conclusion": conclusion,
        }
