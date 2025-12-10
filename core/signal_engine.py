import math
from typing import Any, Dict, List, Optional, Tuple


_LAST_SIGNAL_STATE: Dict[str, Optional[float]] = {"entry": None, "action": None}
_DUPLICATE_BAND = 2.0  # USD band to block duplicate alerts


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Convert to float safely."""
    try:
        if val is None:
            return default
        f = float(val)
        if math.isnan(f):
            return default
        return f
    except Exception:
        return default


def _sanitize_action(action: Any) -> str:
    if isinstance(action, str):
        act = action.upper()
        return act if act in ("BUY", "SELL", "NO_TRADE") else "NO_TRADE"
    return "NO_TRADE"


def _trend(row: Dict[str, Any]) -> str:
    """
    Trend with optional structure support.
    If a structure label is present, use it; otherwise fall back to EMA50/200.
    """
    struct = row.get("market_structure") if hasattr(row, "get") else None
    if struct in ("bullish", "bearish"):
        return struct
    try:
        if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
            return "bullish"
        if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
            return "bearish"
    except Exception:
        return "neutral"
    return "neutral"


def _final_direction(trend_4h: str, trend_1h: str) -> str:
    if trend_4h == "bullish" and trend_1h == "bullish":
        return "BUY"
    if trend_4h == "bearish" and trend_1h == "bearish":
        return "SELL"
    return "NO_TRADE"


def calculate_sl_tp(
    entry: float,
    atr: float,
    direction: str,
    sl_atr_mult: float = 1.2,
    tp_atr_mult: float = 1.0,
    max_dist: float = 12.0,
    sl_atr: Optional[float] = None,
    sl_max_dist: float = 25.0,
    tp_atr: Optional[float] = None,
    tp_max_dist: float = 12.0,
) -> Tuple[float, float]:
    """
    ATR-based SL/TP helper (used as fallback only).
    """
    sl_src_atr = sl_atr if sl_atr is not None else atr
    tp_src_atr = tp_atr if tp_atr is not None else atr
    sl_cap = sl_max_dist if sl_max_dist is not None else 25.0
    tp_cap = tp_max_dist if tp_max_dist is not None else 12.0

    sl_dist = min(sl_src_atr * sl_atr_mult, sl_cap)
    tp_dist = min(tp_src_atr * tp_atr_mult, tp_cap)

    if direction == "BUY":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:  # SELL
        sl = entry + sl_dist
        tp = entry - tp_dist

    return float(sl), float(tp)


def detect_rsi_cross(prev_rsi, curr_rsi):
    """Detect RSI crosses through the 45-55 zone."""
    try:
        p = float(prev_rsi)
        c = float(curr_rsi)
    except Exception:
        return None
    bullish = (p < 45 <= c) or (p < 55 <= c)
    bearish = (p > 55 >= c) or (p > 45 >= c)
    if bullish and not bearish:
        return "bullish"
    if bearish and not bullish:
        return "bearish"
    return None


def strong_macd_momentum(df, direction, lookback=3):
    """
    Strong MACD momentum requires MACD > signal and rising histogram for bullish,
    MACD < signal and falling histogram for bearish over the last 2-3 candles.
    """
    if len(df) < lookback:
        return False
    tail = df.tail(lookback)
    hist = tail["macd"] - tail["macd_signal"]
    if direction == "bullish":
        return (
            tail["macd"].iloc[-1] > tail["macd_signal"].iloc[-1]
            and hist.is_monotonic_increasing
            and hist.iloc[-1] > 0
        )
    if direction == "bearish":
        return (
            tail["macd"].iloc[-1] < tail["macd_signal"].iloc[-1]
            and hist.is_monotonic_decreasing
            and hist.iloc[-1] < 0
        )
    return False


def _adx_tier(val: Any) -> str:
    """Return ADX tier: blocked (<20), medium (20-25), high (>=25)."""
    try:
        v = float(val)
    except Exception:
        return "blocked"
    if v < 20:
        return "blocked"
    if v < 25:
        return "medium"
    return "high"


def _compute_adx_conf(adx5, adx15, adx1h=None, adx4h=None):
    """
    Apply MTF ADX rules and return (conf, tier5, tier15, tier1h, tier4h).
    - If 5m or 15m < 20 => blocked.
    - High requires 5m & 15m >= 25; medium for 20-25.
    - 1H/4H only adjust confidence (never block): downgrade if <20, upgrade if both >=25.
    """
    tier5 = _adx_tier(adx5)
    tier15 = _adx_tier(adx15)
    tier1h = _adx_tier(adx1h) if adx1h is not None else None
    tier4h = _adx_tier(adx4h) if adx4h is not None else None

    if tier5 == "blocked" or tier15 == "blocked":
        return "blocked", tier5, tier15, tier1h, tier4h

    conf = "HIGH" if (tier5 == "high" and tier15 == "high") else "MEDIUM"

    htf_weak = (tier1h == "blocked") or (tier4h == "blocked")
    htf_strong = (tier1h == "high" and tier4h == "high")
    if htf_weak:
        conf = "LOW"
    elif conf == "MEDIUM" and htf_strong:
        conf = "HIGH"

    return conf, tier5, tier15, tier1h, tier4h


def _local_swings(df, lookback=20, window=2):
    """Lightweight swing detection for micro structure."""
    swings = {"highs": [], "lows": []}
    if len(df) < window * 2 + 3:
        return swings
    tail = df.tail(lookback)
    highs = tail["high"].values
    lows = tail["low"].values
    closes = tail["close"].values
    idxs = list(tail.index)
    for i in range(window, len(tail) - window):
        if highs[i] >= highs[i - window : i + window + 1].max():
            swings["highs"].append({"idx": idxs[i], "price": float(highs[i])})
        if lows[i] <= lows[i - window : i + window + 1].min():
            swings["lows"].append({"idx": idxs[i], "price": float(lows[i])})
    swings["closes"] = float(closes[-1]) if len(closes) else None
    return swings


def _structure_bias(swings):
    """Infer bullish/bearish micro bias from last two swings."""
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    bias = "neutral"
    if len(highs) >= 2 and len(lows) >= 2:
        last_high, prev_high = highs[-1]["price"], highs[-2]["price"]
        last_low, prev_low = lows[-1]["price"], lows[-2]["price"]
        if last_high > prev_high and last_low > prev_low:
            bias = "bullish"
        elif last_high < prev_high and last_low < prev_low:
            bias = "bearish"
    return bias


def _touch_strength(level, df, tolerance=0.0015):
    """Count touches of a level within a tolerance band."""
    if level is None or len(df) == 0:
        return 0
    highs = df["high"].values
    lows = df["low"].values
    band_high = level * (1 + tolerance)
    band_low = level * (1 - tolerance)
    touches = ((lows <= band_high) & (highs >= band_low)).sum()
    return int(touches)


def _wick_rejection(candle):
    """Detect pin-bar style rejection wick on the last candle."""
    open_, high, low, close = map(float, (candle.get("open"), candle.get("high"), candle.get("low"), candle.get("close")))
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    if body == 0:
        body = 1e-8
    bullish_reject = lower_wick > body * 2 and close > open_
    bearish_reject = upper_wick > body * 2 and close < open_
    return bullish_reject, bearish_reject


def _liquidity_sweep(df, lookback: int = 14) -> Dict[str, Any]:
    """Detect liquidity sweep (high/low violation with close back inside)."""
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


def _detect_zones(df) -> Dict[str, Any]:
    """Detect demand/supply zones with touch count and confidence."""
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


def _channel_bounds(df, lookback=30):
    """Approximate channel bounds using recent extrema."""
    if len(df) == 0:
        return None
    tail = df.tail(lookback)
    upper = float(tail["high"].max())
    lower = float(tail["low"].min())
    mid = (upper + lower) / 2
    return {"upper": upper, "lower": lower, "mid": mid}


def _detect_channel_context(df, price: float) -> Dict[str, Any]:
    bounds = _channel_bounds(df, lookback=60)
    if not bounds:
        return {"type": None, "bounds": None, "tap": None}
    slope = float(df["close"].tail(8).diff().mean())
    channel_type = "up" if slope > 0 else ("down" if slope < 0 else "internal")
    tap_support = abs(price - bounds["lower"]) / price < 0.006
    tap_resistance = abs(price - bounds["upper"]) / price < 0.006
    tap = "support" if tap_support else ("resistance" if tap_resistance else None)
    return {
        "type": channel_type,
        "bounds": bounds,
        "tap": tap,
    }


def _detect_bos_choch(df, label: str) -> Dict[str, Any]:
    swings = _local_swings(df, lookback=50, window=2)
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    close = float(df["close"].iloc[-1])
    event_type = None
    direction = None
    level = None

    if highs and close > highs[-1]["price"]:
        event_type, direction, level = "BOS", "bullish", highs[-1]["price"]
    elif lows and close < lows[-1]["price"]:
        event_type, direction, level = "BOS", "bearish", lows[-1]["price"]
    else:
        prev_bias = _structure_bias({"highs": highs[:-1], "lows": lows[:-1]}) if len(highs) > 1 and len(lows) > 1 else "neutral"
        cur_bias = _structure_bias(swings)
        if prev_bias != "neutral" and cur_bias != "neutral" and prev_bias != cur_bias:
            event_type, direction = "CHOCH", cur_bias

    return {"timeframe": label, "type": event_type, "direction": direction, "level": level}


def _detect_imbalance(df) -> Dict[str, Any]:
    """Detect a simple Fair Value Gap (FVG) on the last 3 candles."""
    if len(df) < 3:
        return {"bullish": False, "bearish": False}
    a, b, c = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    bullish = b["low"] > a["high"]
    bearish = b["high"] < a["low"]
    return {"bullish": bool(bullish), "bearish": bool(bearish)}


def _build_human_explanation(
    structure: Dict[str, Any],
    sweeps: Dict[str, Any],
    zones: Dict[str, Any],
    channels: Dict[str, Any],
    bos15: Dict[str, Any],
    bos5: Dict[str, Any],
    imbalances: Dict[str, Any],
    wicks: Dict[str, Any],
    master_direction: str,
) -> List[str]:
    notes: List[str] = []
    for tf, info in structure.items():
        if info.get("label"):
            notes.append(f"{tf} structure {info['label']} ({info['bias']})")
    if sweeps.get("15m", {}).get("type"):
        notes.append(f"15m liquidity sweep {sweeps['15m']['type']}")
    if sweeps.get("5m", {}).get("type"):
        notes.append(f"5m liquidity sweep {sweeps['5m']['type']}")
    if zones.get("demand", {}).get("zone") and master_direction == "BUY":
        notes.append(
            f"Demand zone touched {zones['demand']['touches']} times (conf {zones['demand']['confidence']:.0f}%)"
        )
    if zones.get("supply", {}).get("zone") and master_direction == "SELL":
        notes.append(
            f"Supply zone touched {zones['supply']['touches']} times (conf {zones['supply']['confidence']:.0f}%)"
        )
    if channels.get("tap"):
        notes.append(f"Channel tap at {channels['tap']} ({channels['type']})")
    if bos15.get("type"):
        notes.append(f"15m {bos15['type']} {bos15.get('direction')}")
    if bos5.get("type"):
        notes.append(f"5m {bos5['type']} {bos5.get('direction')}")
    if imbalances.get("bullish"):
        notes.append("Bullish FVG present")
    if imbalances.get("bearish"):
        notes.append("Bearish FVG present")
    if wicks.get("bullish"):
        notes.append("Wick rejection to the downside")
    if wicks.get("bearish"):
        notes.append("Wick rejection to the upside")
    if not notes:
        notes.append("No strong discretionary cues detected")
    return notes


def _sanitize_levels(
    action: str,
    entry: float,
    sl: Optional[float],
    tps: List[Optional[float]],
    atr1h: float,
    atr5: float,
) -> Tuple[float, List[float]]:
    """Ensure SL/TP respect BUY/SELL geometry and sanitize NaN/None."""
    action = _sanitize_action(action)
    entry = float(entry)
    fallback = max(entry * 0.001, 0.5)
    atr1h_val = _safe_float(atr1h, None)
    atr5_val = _safe_float(atr5, None)
    ref_sl_atr = atr1h_val if atr1h_val and atr1h_val > 0 else (atr5_val if atr5_val and atr5_val > 0 else fallback)
    ref_tp_atr = atr5_val if atr5_val and atr5_val > 0 else fallback

    min_sl_dist = max(ref_sl_atr * 0.8, 2.5)
    max_sl_dist = max(min_sl_dist, min(ref_sl_atr * 2.0, 15.0))
    min_tp_dist = min(ref_tp_atr * 0.8, 2.5)

    if action == "BUY":
        candidate_sl = _safe_float(sl)
        if candidate_sl is None or candidate_sl >= entry:
            candidate_sl = entry - min_sl_dist
        sl_dist = entry - candidate_sl
        sl_dist = min(max(sl_dist, min_sl_dist), max_sl_dist)
        safe_sl = entry - sl_dist

        raw_tps = []
        for tp in tps:
            tp_val = _safe_float(tp)
            if tp_val is None or tp_val <= entry:
                tp_val = entry + min_tp_dist
            raw_tps.append(tp_val)
        while len(raw_tps) < 3:
            raw_tps.append(entry + min_tp_dist)
        tp1 = max(raw_tps[0], entry + min_tp_dist)
        tp2 = max(raw_tps[1], tp1 + 2)
        tp3 = max(raw_tps[2], tp2 + 2)
        safe_tps = [tp1, tp2, tp3]
    else:
        candidate_sl = _safe_float(sl)
        if candidate_sl is None or candidate_sl <= entry:
            candidate_sl = entry + min_sl_dist
        sl_dist = candidate_sl - entry
        sl_dist = min(max(sl_dist, min_sl_dist), max_sl_dist)
        safe_sl = entry + sl_dist

        raw_tps = []
        for tp in tps:
            tp_val = _safe_float(tp)
            if tp_val is None or tp_val >= entry:
                tp_val = entry - min_tp_dist
            raw_tps.append(tp_val)
        while len(raw_tps) < 3:
            raw_tps.append(entry - min_tp_dist)
        tp1 = min(raw_tps[0], entry - min_tp_dist)
        tp2 = min(raw_tps[1], tp1 - 2)
        tp3 = min(raw_tps[2], tp2 - 2)
        safe_tps = [tp1, tp2, tp3]
    safe_tps = _order_tps(action, [round(float(tp), 2) for tp in safe_tps])
    return round(float(safe_sl), 2), safe_tps


def _order_tps(action: str, tps: List[float]) -> List[float]:
    """Sort TPs so they are ordered correctly for BUY/SELL directions."""
    if action == "BUY":
        return sorted(tps)
    return sorted(tps, reverse=True)


def _should_block_duplicate(entry: float, action: str) -> bool:
    last_entry = _LAST_SIGNAL_STATE.get("entry")
    last_action = _LAST_SIGNAL_STATE.get("action")
    if last_entry is not None and last_action == action:
        if abs(float(entry) - float(last_entry)) <= _DUPLICATE_BAND:
            return True
    return False


def _record_signal(entry: float, action: str) -> None:
    _LAST_SIGNAL_STATE["entry"] = float(entry)
    _LAST_SIGNAL_STATE["action"] = action


def _score_trade(context: Dict[str, Any]) -> Tuple[int, Dict[str, int]]:
    """Apply the fixed human-like scoring matrix."""
    breakdown = {
        "htf_alignment": 40 if context.get("htf_alignment") else 0,
        "zones": 25 if context.get("zones") else 0,
        "liquidity": 20 if context.get("liquidity") else 0,
        "channels": 15 if context.get("channels") else 0,
        "bos": 15 if context.get("bos") else 0,
        "wick": 10 if context.get("wick") else 0,
        "momentum": 10 if context.get("momentum") else 0,
    }
    total = sum(breakdown.values())
    return total, breakdown


def _build_levels(
    direction: str,
    entry: float,
    df_5m,
    df_15m,
    df_1h,
    zones: Dict[str, Any],
    channel_ctx: Dict[str, Any],
    atr5: float,
    atr1h: float,
) -> Tuple[float, float, float, float]:
    swings_5 = _local_swings(df_5m, lookback=40, window=2)
    swings_15 = _local_swings(df_15m, lookback=60, window=2)
    highs = [h["price"] for h in swings_5.get("highs", []) + swings_15.get("highs", [])]
    lows = [l["price"] for l in swings_5.get("lows", []) + swings_15.get("lows", [])]

    sl_level = None
    tp_candidates: List[float] = []

    if direction == "BUY":
        if zones.get("demand", {}).get("zone"):
            sl_level = zones["demand"]["zone"]["low"]
        if lows:
            sl_level = min(sl_level, min(lows)) if sl_level is not None else min(lows)
        if channel_ctx.get("bounds"):
            sl_level = min(sl_level, channel_ctx["bounds"]["lower"]) if sl_level is not None else channel_ctx["bounds"]["lower"]

        if zones.get("supply", {}).get("zone"):
            tp_candidates.append(zones["supply"]["zone"]["high"])
        tp_candidates += [h for h in highs if h > entry]
        if channel_ctx.get("bounds"):
            tp_candidates.append(channel_ctx["bounds"]["upper"])
    else:
        if zones.get("supply", {}).get("zone"):
            sl_level = zones["supply"]["zone"]["high"]
        if highs:
            sl_level = max(sl_level, max(highs)) if sl_level is not None else max(highs)
        if channel_ctx.get("bounds"):
            sl_level = max(sl_level, channel_ctx["bounds"]["upper"]) if sl_level is not None else channel_ctx["bounds"]["upper"]

        if zones.get("demand", {}).get("zone"):
            tp_candidates.append(zones["demand"]["zone"]["low"])
        tp_candidates += [l for l in lows if l < entry]
        if channel_ctx.get("bounds"):
            tp_candidates.append(channel_ctx["bounds"]["lower"])

    # Prefer structural targets, fallback to ATR
    if direction == "BUY":
        tp_candidates = [c for c in tp_candidates if c > entry]
        tp1 = min(tp_candidates) if tp_candidates else entry + atr5
        tp2 = max(tp_candidates) if tp_candidates else entry + atr5 * 1.5
        tp3 = channel_ctx.get("bounds", {}).get("upper", tp2 + atr5)
    else:
        tp_candidates = [c for c in tp_candidates if c < entry]
        tp1 = max(tp_candidates) if tp_candidates else entry - atr5
        tp2 = min(tp_candidates) if tp_candidates else entry - atr5 * 1.5
        tp3 = channel_ctx.get("bounds", {}).get("lower", tp2 - atr5)

    sl, tps = _sanitize_levels(direction, entry, sl_level, [tp1, tp2, tp3], atr1h, atr5)
    return sl, tps[0], tps[1], tps[2]


def build_human_layer(df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
    """Human-like analysis layer that never issues a trade decision."""
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]

    structure = {
        "4H": _detect_structure(df_4h, lookback=140, window=3),
        "1H": _detect_structure(df_1h, lookback=140, window=3),
        "15m": _detect_structure(df_15m, lookback=120, window=2),
        "5m": _detect_structure(df_5m, lookback=80, window=2),
    }
    sweeps = {
        "15m": _liquidity_sweep(df_15m, lookback=30),
        "5m": _liquidity_sweep(df_5m, lookback=20),
    }
    zones = _detect_zones(df_1h)
    channels = _detect_channel_context(df_1h, float(last1h["close"]))
    bos15 = _detect_bos_choch(df_15m, "15m")
    bos5 = _detect_bos_choch(df_5m, "5m")
    imbalances = _detect_imbalance(df_15m)
    wick_bull, wick_bear = _wick_rejection(last15)

    master_direction = _final_direction(_trend(last4h), _trend(last1h))
    explanation = _build_human_explanation(
        structure,
        sweeps,
        zones,
        channels,
        bos15,
        bos5,
        imbalances,
        {"bullish": wick_bull, "bearish": wick_bear},
        master_direction,
    )

    return {
        "action": "NO_TRADE",
        "htf_direction": master_direction,
        "structure": structure,
        "liquidity_sweeps": sweeps,
        "zones": zones,
        "channels": channels,
        "bos_choch": {"15m": bos15, "5m": bos5},
        "imbalances": imbalances,
        "wicks": {"bullish": wick_bull, "bearish": wick_bear},
        "explanation": explanation,
    }


def run_scalp_layer(df_5m, df_15m, df_1h, df_4h, human_layer: Dict[str, Any]) -> Dict[str, Any]:
    """Refined SCALP engine aligned to professional rules."""
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    price = float(last5["close"])

    trend_4h = _trend(last4h)
    trend_1h = _trend(last1h)
    trend_15 = _trend(last15)
    direction = _final_direction(trend_4h, trend_1h)

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(
        _safe_float(last5.get("adx"), 0),
        _safe_float(last15.get("adx"), 0),
        _safe_float(last1h.get("adx"), 0),
        _safe_float(last4h.get("adx"), 0),
    )

    if direction == "NO_TRADE":
        return {
            "action": "NO_TRADE",
            "reason": "HTF alignment missing",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    if trend_15 in ("bullish", "bearish") and (
        (trend_15 == "bullish" and direction == "SELL") or (trend_15 == "bearish" and direction == "BUY")
    ):
        return {
            "action": "NO_TRADE",
            "reason": "15m cannot contradict HTF",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    sweep5 = _liquidity_sweep(df_5m, lookback=20)
    bos5 = human_layer.get("bos_choch", {}).get("5m", {})
    bos15 = human_layer.get("bos_choch", {}).get("15m", {})
    channel_ctx = _detect_channel_context(df_5m, price)
    zones = human_layer.get("zones", _detect_zones(df_1h))
    atr5 = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr1h = _safe_float(last1h.get("atr"), atr5) or atr5

    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5, atr1h)

    wick_bull, wick_bear = _wick_rejection(last5)
    wick_ok = (wick_bull and direction == "BUY") or (wick_bear and direction == "SELL")
    sweep_ok = (sweep5.get("type") == "below" and direction == "BUY") or (sweep5.get("type") == "above" and direction == "SELL")
    bos_ok = (bos5.get("direction") == ("bullish" if direction == "BUY" else "bearish")) or (
        bos15.get("direction") == ("bullish" if direction == "BUY" else "bearish")
    )
    channel_ok = (channel_ctx.get("tap") == "support" and direction == "BUY") or (
        channel_ctx.get("tap") == "resistance" and direction == "SELL"
    )
    zone_conf = zones.get("demand", {}).get("confidence", 0) if direction == "BUY" else zones.get("supply", {}).get("confidence", 0)

    score_ctx = {
        "htf_alignment": True,
        "zones": zone_conf >= 50,
        "liquidity": sweep_ok,
        "channels": channel_ok,
        "bos": bos_ok,
        "wick": wick_ok,
        "momentum": adx_conf != "blocked",
    }
    score, breakdown = _score_trade(score_ctx)

    action = direction if score >= 60 else "NO_TRADE"
    confidence = float(min(100, max(60, score))) if action != "NO_TRADE" else float(min(score, 60))

    return {
        "action": action,
        "entry": round(price, 2),
        "sl": sl,
        "tp": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "score": score,
        "score_breakdown": breakdown,
        "signal_type": "SCALP",
        "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        "reasoning": human_layer.get("explanation", []),
        "adx_conf": adx_conf,
    }


def run_ultra_layer(df_5m, df_15m, df_1h, df_4h, human_layer: Dict[str, Any]) -> Dict[str, Any]:
    """ULTRA layer wrapped to respect new stability + direction rules."""
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    price = float(last5["close"])

    trend_4h = _trend(last4h)
    trend_1h = _trend(last1h)
    direction = _final_direction(trend_4h, trend_1h)
    if direction == "NO_TRADE":
        return {"action": "NO_TRADE", "reason": "HTF not aligned", "signal_type": "ULTRA"}

    sweep = _liquidity_sweep(df_5m, lookback=20)
    bos = _detect_bos_choch(df_5m, "5m")
    wick_bull, wick_bear = _wick_rejection(last5)
    wick_ok = (wick_bull and direction == "BUY") or (wick_bear and direction == "SELL")

    zones = human_layer.get("zones", _detect_zones(df_1h))
    channel_ctx = _detect_channel_context(df_5m, price)
    atr5 = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr1h = _safe_float(last1h.get("atr"), atr5) or atr5
    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5, atr1h)

    bos_ok = bos.get("direction") == ("bullish" if direction == "BUY" else "bearish")
    sweep_ok = (sweep.get("type") == "below" and direction == "BUY") or (sweep.get("type") == "above" and direction == "SELL")
    channel_ok = (channel_ctx.get("tap") == "support" and direction == "BUY") or (channel_ctx.get("tap") == "resistance" and direction == "SELL")
    zone_conf = zones.get("demand", {}).get("confidence", 0) if direction == "BUY" else zones.get("supply", {}).get("confidence", 0)

    score_ctx = {
        "htf_alignment": True,
        "zones": zone_conf >= 50,
        "liquidity": sweep_ok,
        "channels": channel_ok,
        "bos": bos_ok,
        "wick": wick_ok,
        "momentum": _safe_float(last5.get("adx"), 0) >= 20 and _safe_float(last15.get("adx"), 0) >= 20,
    }
    score, breakdown = _score_trade(score_ctx)
    action = direction if score >= 60 else "NO_TRADE"
    confidence = float(min(100, max(60, score))) if action != "NO_TRADE" else float(min(score, 60))

    return {
        "action": action,
        "entry": round(price, 2),
        "sl": sl,
        "tp": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "score": score,
        "score_breakdown": breakdown,
        "signal_type": "ULTRA",
        "trend": {"4h": trend_4h, "1h": trend_1h},
        "reasoning": human_layer.get("explanation", []),
    }


def run_ultra_v3_layer(df_5m, df_15m, df_1h, df_4h, human_layer: Dict[str, Any]) -> Dict[str, Any]:
    """ULTRA V3 layer – stricter version, but still aligned to HTF rules."""
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    price = float(last5["close"])

    trend_4h = _trend(last4h)
    trend_1h = _trend(last1h)
    trend_15 = _trend(last15)
    direction = _final_direction(trend_4h, trend_1h)
    if direction == "NO_TRADE":
        return {"action": "NO_TRADE", "reason": "HTF not aligned", "signal_type": "ULTRA_V3"}
    if trend_15 in ("bullish", "bearish") and (
        (trend_15 == "bullish" and direction == "SELL") or (trend_15 == "bearish" and direction == "BUY")
    ):
        return {"action": "NO_TRADE", "reason": "15m confirm failed", "signal_type": "ULTRA_V3"}

    sweep = _liquidity_sweep(df_5m, lookback=18)
    bos = _detect_bos_choch(df_5m, "5m")
    bos15 = _detect_bos_choch(df_15m, "15m")
    wick_bull, wick_bear = _wick_rejection(last5)
    wick_ok = (wick_bull and direction == "BUY") or (wick_bear and direction == "SELL")

    zones = human_layer.get("zones", _detect_zones(df_1h))
    channel_ctx = _detect_channel_context(df_5m, price)
    atr5 = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr1h = _safe_float(last1h.get("atr"), atr5) or atr5
    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5, atr1h)

    bos_ok = (bos.get("direction") == ("bullish" if direction == "BUY" else "bearish")) or (
        bos15.get("direction") == ("bullish" if direction == "BUY" else "bearish")
    )
    sweep_ok = (sweep.get("type") == "below" and direction == "BUY") or (sweep.get("type") == "above" and direction == "SELL")
    channel_ok = (channel_ctx.get("tap") == "support" and direction == "BUY") or (channel_ctx.get("tap") == "resistance" and direction == "SELL")
    zone_conf = zones.get("demand", {}).get("confidence", 0) if direction == "BUY" else zones.get("supply", {}).get("confidence", 0)

    score_ctx = {
        "htf_alignment": True,
        "zones": zone_conf >= 50,
        "liquidity": sweep_ok,
        "channels": channel_ok,
        "bos": bos_ok,
        "wick": wick_ok,
        "momentum": _safe_float(last5.get("adx"), 0) >= 20 and _safe_float(last15.get("adx"), 0) >= 20,
    }
    score, breakdown = _score_trade(score_ctx)
    action = direction if score >= 60 else "NO_TRADE"
    confidence = float(min(100, max(60, score))) if action != "NO_TRADE" else float(min(score, 60))

    return {
        "action": action,
        "entry": round(price, 2),
        "sl": sl,
        "tp": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "confidence": confidence,
        "score": score,
        "score_breakdown": breakdown,
        "signal_type": "ULTRA_V3",
        "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        "reasoning": human_layer.get("explanation", []),
    }


def consolidate_signals(
    human_layer: Dict[str, Any],
    scalp_layer: Dict[str, Any],
    ultra_layer: Dict[str, Any],
    v3_layer: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge layers and emit a single stable decision."""
    master_direction = human_layer.get("htf_direction", "NO_TRADE")
    candidates = []
    for name, layer in (("SCALP", scalp_layer), ("ULTRA_V3", v3_layer), ("ULTRA", ultra_layer)):
        action = _sanitize_action(layer.get("action"))
        if action not in ("BUY", "SELL"):
            continue
        if master_direction != "NO_TRADE" and action != master_direction:
            continue
        score = layer.get("score", 0)
        confidence = _safe_float(layer.get("confidence"), 0) or 0
        candidates.append(
            {"name": name, "score": score, "confidence": confidence, "payload": layer, "action": action}
        )

    if not candidates:
        return {
            "action": "NO_TRADE",
            "reason": "No aligned signals after consolidation",
            "signal_type": "UNIFIED",
            "htf_direction": master_direction,
            "layers": {"human": human_layer, "scalp": scalp_layer, "ultra": ultra_layer, "ultra_v3": v3_layer},
        }

    best = sorted(candidates, key=lambda x: (x["score"], x["confidence"]), reverse=True)[0]
    final = dict(best["payload"])
    final["action"] = best["action"]
    final["signal_type"] = "UNIFIED"
    final["htf_direction"] = master_direction
    final["score"] = best["score"]
    final["confidence"] = best["confidence"] if final["action"] != "NO_TRADE" else best["confidence"]
    final["human_summary"] = human_layer.get("explanation", [])

    entry = _safe_float(final.get("entry"), None)
    if final["action"] in ("BUY", "SELL") and entry is not None:
        if _should_block_duplicate(entry, final["action"]):
            return {
                "action": "NO_TRADE",
                "reason": "Stability layer blocked duplicate entry",
                "signal_type": "UNIFIED",
                "htf_direction": master_direction,
                "layers": {"human": human_layer, "scalp": scalp_layer, "ultra": ultra_layer, "ultra_v3": v3_layer},
            }
        _record_signal(entry, final["action"])
    final["layers"] = {"human": human_layer, "scalp": scalp_layer, "ultra": ultra_layer, "ultra_v3": v3_layer}
    return final


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """Unified entry point combining human layer + scalp + ultra stacks."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    scalp_layer = run_scalp_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    ultra_layer = run_ultra_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    v3_layer = run_ultra_v3_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    return consolidate_signals(human_layer, scalp_layer, ultra_layer, v3_layer)


def check_ultra_entry(df_5m, df_15m, df_1h, df_4h):
    """Compatibility wrapper for legacy callers."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    return run_ultra_layer(df_5m, df_15m, df_1h, df_4h, human_layer)


def check_ultra_v3(df_5m, df_15m, df_1h, df_4h):
    """Compatibility wrapper for legacy callers."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    return run_ultra_v3_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
