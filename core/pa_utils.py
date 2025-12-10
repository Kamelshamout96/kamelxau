"""
Lightweight price-action utilities for structure, liquidity, zones, channels, and wicks.
Extracted from prior logic to remove dependency on the old signal_engine module.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(val: Any, default=None):
    try:
        f = float(val)
        return f
    except Exception:
        return default


def _local_swings(df, lookback=20, window=2):
    swings = {"highs": [], "lows": []}
    if len(df) < window * 2 + 3:
        return swings
    tail = df.tail(lookback)
    highs = tail["high"].values
    lows = tail["low"].values
    idxs = list(tail.index)
    for i in range(window, len(tail) - window):
        if highs[i] >= highs[i - window : i + window + 1].max():
            swings["highs"].append({"idx": idxs[i], "price": float(highs[i])})
        if lows[i] <= lows[i - window : i + window + 1].min():
            swings["lows"].append({"idx": idxs[i], "price": float(lows[i])})
    return swings


def _detect_structure(df, lookback: int = 120, window: int = 3) -> Dict[str, Any]:
    swings = _local_swings(df, lookback=lookback, window=window)
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    label = None
    bias = "neutral"
    if len(highs) >= 2 and len(lows) >= 2:
        last_high, prev_high = highs[-1]["price"], highs[-2]["price"]
        last_low, prev_low = lows[-1]["price"], lows[-2]["price"]
        if last_high > prev_high and last_low > prev_low:
            label = "HH-HL"
            bias = "bullish"
        elif last_high < prev_high and last_low < prev_low:
            label = "LH-LL"
            bias = "bearish"
        else:
            label = "mixed"
    return {
        "label": label,
        "bias": bias,
        "last_high": highs[-1]["price"] if highs else None,
        "last_low": lows[-1]["price"] if lows else None,
        "swings": swings,
    }


def _liquidity_sweep(df, lookback: int = 14) -> Dict[str, Any]:
    if len(df) < 3:
        return {"type": None, "level": None}
    tail = df.tail(lookback)
    prev = tail.iloc[:-1]
    last = tail.iloc[-1]
    prev_high = float(prev["high"].max())
    prev_low = float(prev["low"].min())
    close = float(last["close"])
    sweep = {"type": None, "level": None}
    if float(last["high"]) > prev_high and close < prev_high:
        sweep = {"type": "above", "level": prev_high}
    elif float(last["low"]) < prev_low and close > prev_low:
        sweep = {"type": "below", "level": prev_low}
    return sweep


def _touch_strength(level, df, tolerance=0.0015):
    if level is None or len(df) == 0:
        return 0
    highs = df["high"].values
    lows = df["low"].values
    band_high = level * (1 + tolerance)
    band_low = level * (1 - tolerance)
    touches = ((lows <= band_high) & (highs >= band_low)).sum()
    return int(touches)


def _detect_zones(df) -> Dict[str, Any]:
    swings = _local_swings(df, lookback=120, window=3)
    demand_zone = None
    supply_zone = None
    touches_d = touches_s = 0

    if swings.get("lows"):
        base_low = swings["lows"][-1]["price"]
        demand_zone = {"low": base_low * 0.998, "high": base_low * 1.002}
        touches_d = _touch_strength((demand_zone["low"] + demand_zone["high"]) / 2, df)

    if swings.get("highs"):
        base_high = swings["highs"][-1]["price"]
        supply_zone = {"low": base_high * 0.998, "high": base_high * 1.002}
        touches_s = _touch_strength((supply_zone["low"] + supply_zone["high"]) / 2, df)

    conf_d = min(100, 40 + touches_d * 15) if demand_zone else 0
    conf_s = min(100, 40 + touches_s * 15) if supply_zone else 0

    return {
        "demand": {"zone": demand_zone, "touches": touches_d, "confidence": conf_d},
        "supply": {"zone": supply_zone, "touches": touches_s, "confidence": conf_s},
    }


def _detect_bos_choch(df, tf_label: str) -> Dict[str, Any]:
    swings = _local_swings(df, lookback=80, window=2)
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    direction = None
    level = None
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1]["price"] > highs[-2]["price"] and lows[-1]["price"] > lows[-2]["price"]:
            direction = "bullish"
            level = highs[-1]["price"]
        elif highs[-1]["price"] < highs[-2]["price"] and lows[-1]["price"] < lows[-2]["price"]:
            direction = "bearish"
            level = lows[-1]["price"]
    if direction:
        return {"timeframe": tf_label, "type": "BOS", "direction": direction, "level": level}
    return {"timeframe": tf_label, "type": None, "direction": None, "level": None}


def _detect_imbalance(df) -> Dict[str, Any]:
    if len(df) < 3:
        return {"bullish": False, "bearish": False}
    a, b, c = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    bullish = b["low"] > a["high"]
    bearish = b["high"] < a["low"]
    return {"bullish": bool(bullish), "bearish": bool(bearish)}


def _detect_channel_context(df, price: float) -> Dict[str, Any]:
    if len(df) == 0:
        return {"type": None, "bounds": None, "tap": None}
    tail = df.tail(60)
    upper = float(tail["high"].max())
    lower = float(tail["low"].min())
    mid = (upper + lower) / 2
    bounds = {"upper": upper, "lower": lower, "mid": mid}
    slope = float(tail["close"].diff().mean())
    channel_type = "up" if slope > 0 else ("down" if slope < 0 else "internal")
    tap_support = abs(price - lower) / price < 0.006
    tap_resistance = abs(price - upper) / price < 0.006
    tap = "support" if tap_support else ("resistance" if tap_resistance else None)
    return {"type": channel_type, "bounds": bounds, "tap": tap}


def _wick_rejection(candle):
    open_, high, low, close = map(float, (candle.get("open"), candle.get("high"), candle.get("low"), candle.get("close")))
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    if body == 0:
        body = 1e-8
    bullish_reject = lower_wick > body * 2 and close > open_
    bearish_reject = upper_wick > body * 2 and close < open_
    return bullish_reject, bearish_reject
