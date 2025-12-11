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


def _get_atr(df, ctx: Dict[str, Any]):
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


def _no_trade_reason(
    trend_direction: str,
    zone_type: str,
    reaction: str,
    breakout_status: str,
    retest_found: bool,
    retest_quality: str,
    momentum_supports_bull: bool,
    momentum_supports_bear: bool,
    liquidity_event: str,
) -> str:
    if trend_direction not in ("bullish", "bearish"):
        return "no_trend_edge"
    if zone_type == "none":
        return "no_zone_reaction"

    if trend_direction == "bullish":
        if zone_type != "demand":
            return "demand_zone_missing"
        if liquidity_event == "high_sweep":
            return "bullish_liquidity_sweep_risk"
        if reaction != "rejection":
            return "demand_not_rejecting"
        if breakout_status == "bullish_breakout":
            if not retest_found:
                return "awaiting_bullish_retest"
            if retest_quality not in ("normal", "strong"):
                return "weak_bullish_retest"
        if not momentum_supports_bull:
            return "insufficient_bullish_momentum"
        return "bullish_filters_not_met"

    if trend_direction == "bearish":
        if zone_type != "supply":
            return "supply_zone_missing"
        if liquidity_event == "low_sweep":
            return "bearish_liquidity_sweep_risk"
        if reaction != "rejection":
            return "supply_not_rejecting"
        if breakout_status == "bearish_breakout":
            if not retest_found:
                return "awaiting_bearish_retest"
            if retest_quality not in ("normal", "strong"):
                return "weak_bearish_retest"
        if not momentum_supports_bear:
            return "insufficient_bearish_momentum"
        return "bearish_filters_not_met"

    return "analysis_only"


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
                "signal": {"action": "NO_TRADE", "reason": "insufficient_data"},
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

        # Discretionary signal (optional)
        action = "NO_TRADE"
        reason = "analysis_only"
        entry = float(df_5m["close"].iloc[-1])
        sl = tp = tp1 = tp2 = tp3 = None
        confidence = 0.0

        bullish_setup = (
            trend_direction == "bullish"
            and breakout_status == "bullish_breakout"
            and retest_found
            and retest_quality in ("normal", "strong")
            and zone_type == "demand"
            and reaction == "rejection"
            and liquidity_event != "high_sweep"
        )
        bearish_setup = (
            trend_direction == "bearish"
            and breakout_status == "bearish_breakout"
            and retest_found
            and retest_quality in ("normal", "strong")
            and zone_type == "supply"
            and reaction == "rejection"
            and liquidity_event != "low_sweep"
        )

        momentum_supports_bull = momentum_bias.startswith("strong_bull") or momentum_bias.startswith("building_bull")
        momentum_supports_bear = momentum_bias.startswith("strong_bear") or momentum_bias.startswith("building_bear")

        if bullish_setup or (trend_direction == "bullish" and zone_type == "demand" and reaction == "rejection" and momentum_supports_bull):
            action = "BUY"
            reason = "discretionary_bullish_breakout" if bullish_setup else "discretionary_bullish_rejection"
        elif bearish_setup or (trend_direction == "bearish" and zone_type == "supply" and reaction == "rejection" and momentum_supports_bear):
            action = "SELL"
            reason = "discretionary_bearish_breakout" if bearish_setup else "discretionary_bearish_rejection"

        if action == "NO_TRADE":
            reason = _no_trade_reason(
                trend_direction=trend_direction,
                zone_type=zone_type,
                reaction=reaction,
                breakout_status=breakout_status,
                retest_found=retest_found,
                retest_quality=retest_quality,
                momentum_supports_bull=momentum_supports_bull,
                momentum_supports_bear=momentum_supports_bear,
                liquidity_event=liquidity_event,
            )

        if action in ("BUY", "SELL"):
            atr = _get_atr(df_5m, ctx)
            if action == "BUY":
                sl_raw = entry - (atr * 2.5)
                sl_hard = entry - 10
                sl = min(sl_raw, sl_hard)
                tp1 = entry + (atr * 1.0)
                tp2 = entry + (atr * 1.6)
                tp3 = entry + (atr * 2.2)
                tp = tp1
            else:
                sl_raw = entry + (atr * 2.5)
                sl_hard = entry + 10
                sl = max(sl_raw, sl_hard)
                tp1 = entry - (atr * 1.0)
                tp2 = entry - (atr * 1.6)
                tp3 = entry - (atr * 2.2)
                tp = tp1

            confidence = 55.0
            if retest_quality == "strong":
                confidence += 7.5
            elif retest_quality == "normal":
                confidence += 3.0
            if "strong" in momentum_bias:
                confidence += 5.0
            if reaction == "rejection" and zone_strength == "strong":
                confidence += 5.0
            confidence = min(75.0, confidence)

        disc_signal = {
            "action": action,
            "entry": round(entry, 2),
            "sl": round(sl, 2) if sl else None,
            "tp": round(tp, 2) if tp else None,
            "tp1": round(tp1, 2) if tp1 else None,
            "tp2": round(tp2, 2) if tp2 else None,
            "tp3": round(tp3, 2) if tp3 else None,
            "confidence": confidence,
            "reason": reason,
        }

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
            "signal": disc_signal,
        }
