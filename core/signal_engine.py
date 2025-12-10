import math
import time
from typing import Any, Dict, List, Optional, Tuple


_LAST_SIGNAL_STATE: Dict[str, Optional[float]] = {"entry": None, "action": None, "ts": None}
_DUPLICATE_BAND = 2.0  # USD band to block duplicate alerts
_DUPLICATE_WINDOW_SEC = 6 * 60  # 6 minutes window for duplicate suppression


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


def _is_low_volatility(atr5: Any, atr15: Any) -> Tuple[bool, Dict[str, Optional[float]]]:
    a5 = _safe_float(atr5, None)
    a15 = _safe_float(atr15, None)
    if a5 is None or a15 is None:
        return True, {"atr5": a5, "atr15": a15}
    return (a5 < 0.8 or a15 < 1.2), {"atr5": a5, "atr15": a15}


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


def _touch_strength(level, df, tolerance=0.0015, lookback: int = 40):
    """Count touches of a level within a tolerance band using recent window."""
    if level is None or len(df) == 0:
        return 0
    window = df.tail(max(5, min(len(df), lookback)))
    highs = window["high"].values
    lows = window["low"].values
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


def _detect_zones(df, touch_window: int = 40) -> Dict[str, Any]:
    """Detect demand/supply zones with touch count and confidence using recent data."""
    swings = _local_swings(df, lookback=120, window=3)
    demand_zone = None
    supply_zone = None
    touches_d = touches_s = 0

    if swings.get("lows"):
        base_low = swings["lows"][-1]["price"]
        demand_zone = {"low": base_low * 0.998, "high": base_low * 1.002}
        touches_d = _touch_strength((demand_zone["low"] + demand_zone["high"]) / 2, df.tail(touch_window))

    if swings.get("highs"):
        base_high = swings["highs"][-1]["price"]
        supply_zone = {"low": base_high * 0.998, "high": base_high * 1.002}
        touches_s = _touch_strength((supply_zone["low"] + supply_zone["high"]) / 2, df.tail(touch_window))

    conf_d = min(100, 35 + touches_d * 10) if demand_zone else 0
    conf_s = min(100, 35 + touches_s * 10) if supply_zone else 0

    return {
        "demand": {"zone": demand_zone, "touches": touches_d, "confidence": conf_d, "range_bound": touches_d > 20},
        "supply": {"zone": supply_zone, "touches": touches_s, "confidence": conf_s, "range_bound": touches_s > 20},
    }


def _inside_zone(price: float, zone: Optional[Dict[str, float]]) -> bool:
    if not zone:
        return False
    try:
        return float(zone["low"]) <= price <= float(zone["high"])
    except Exception:
        return False


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


def _fvg_band(df) -> Optional[Dict[str, float]]:
    """Return the most recent FVG band (low/high) if present."""
    if len(df) < 3:
        return None
    a, b, _ = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    if b["low"] > a["high"]:
        low, high = float(a["high"]), float(b["low"])
        return {"type": "bullish", "low": min(low, high), "high": max(low, high)}
    if b["high"] < a["low"]:
        low, high = float(b["high"]), float(a["low"])
        return {"type": "bearish", "low": min(low, high), "high": max(low, high)}
    return None


def _detect_order_block(df, direction: str, lookback: int = 30) -> Optional[Dict[str, float]]:
    """Lightweight order block approximation: last opposite candle before an impulse in lookback window."""
    if len(df) < 5:
        return None
    tail = df.tail(lookback)
    if direction == "BUY":
        prior_high = float(tail["high"].iloc[:-1].max())
        if float(tail["close"].iloc[-1]) <= prior_high:
            return None
        opp = tail[tail["close"] < tail["open"]]
        if len(opp) == 0:
            return None
        candle = opp.iloc[-1]
    else:
        prior_low = float(tail["low"].iloc[:-1].min())
        if float(tail["close"].iloc[-1]) >= prior_low:
            return None
        opp = tail[tail["close"] > tail["open"]]
        if len(opp) == 0:
            return None
        candle = opp.iloc[-1]
    open_, close_, high_, low_ = map(float, (candle["open"], candle["close"], candle["high"], candle["low"]))
    zone_low = min(open_, close_, low_)
    zone_high = max(open_, close_, high_)
    return {"low": zone_low, "high": zone_high, "time": candle.name}


def _pd_rate(price: float, high: Optional[float], low: Optional[float]) -> Optional[float]:
    """Premium/discount ratio within a range."""
    if high is None or low is None or high == low:
        return None
    return (price - low) / (high - low)


def _liquidity_targets(df_5m, df_15m, entry: float, action: str) -> List[float]:
    """Pick liquidity targets such as equal highs/lows or sweep levels on 5m/15m."""
    targets: List[float] = []
    for df in (df_5m, df_15m):
        swings = _local_swings(df, lookback=50, window=2)
        highs = [h["price"] for h in swings.get("highs", [])]
        lows = [l["price"] for l in swings.get("lows", [])]
        if action == "BUY":
            targets.extend([h for h in highs if h > entry])
        else:
            targets.extend([l for l in lows if l < entry])
        hs = df["high"].tail(12).values
        ls = df["low"].tail(12).values
        if action == "BUY":
            for i in range(len(hs) - 2):
                if abs(hs[i] - hs[i + 1]) / hs[i] < 0.0008 and hs[i] > entry:
                    targets.append(float(max(hs[i], hs[i + 1])))
        else:
            for i in range(len(ls) - 2):
                if abs(ls[i] - ls[i + 1]) / ls[i] < 0.0008 and ls[i] < entry:
                    targets.append(float(min(ls[i], ls[i + 1])))
    targets = list(sorted(set(targets)))
    if action == "BUY":
        targets = [t for t in targets if t > entry]
    else:
        targets = [t for t in targets if t < entry]
    return targets


def _ict_entry_from_mitigation(entry_source: Dict[str, float], fvg: Optional[Dict[str, float]]) -> Optional[float]:
    """Choose an entry price around mitigation zone midpoint."""
    prices = []
    if entry_source:
        prices.append((entry_source["low"] + entry_source["high"]) / 2)
    if fvg:
        prices.append((fvg["low"] + fvg["high"]) / 2)
    if not prices:
        return None
    return sum(prices) / len(prices)


def _risk_reward(entry: Optional[float], sl: Optional[float], tp1: Optional[float], action: str) -> Tuple[Optional[float], Optional[float]]:
    entry_val = _safe_float(entry, None)
    sl_val = _safe_float(sl, None)
    tp_val = _safe_float(tp1, None)
    action = _sanitize_action(action)
    if entry_val is None or sl_val is None or tp_val is None or action not in ("BUY", "SELL"):
        return None, None
    risk = abs(entry_val - sl_val)
    reward = tp_val - entry_val if action == "BUY" else entry_val - tp_val
    if risk <= 0:
        return None, None
    return risk, reward / risk


def _level_quality_filter(
    action: str,
    entry: Optional[float],
    sl: Optional[float],
    zones: Dict[str, Any],
    fvg_bands: List[Optional[Dict[str, float]]],
    sweeps: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Apply structural quality guards around entry/SL placement."""
    action = _sanitize_action(action)
    entry_val = _safe_float(entry, None)
    sl_val = _safe_float(sl, None)
    if action not in ("BUY", "SELL") or entry_val is None or sl_val is None:
        return False, "missing levels"

    tol = entry_val * 0.001
    demand = zones.get("demand", {}).get("zone") if zones else None
    supply = zones.get("supply", {}).get("zone") if zones else None
    if action == "BUY" and supply and supply["low"] <= entry_val <= supply["high"]:
        return False, "entry inside supply"
    if action == "SELL" and demand and demand["low"] <= entry_val <= demand["high"]:
        return False, "entry inside demand"

    for fvg in fvg_bands or []:
        if fvg and fvg.get("low") is not None and fvg.get("high") is not None:
            if fvg["low"] <= entry_val <= fvg["high"]:
                return False, "entry inside fvg"

    sweeps = sweeps or {}
    for tf in ("5m", "15m"):
        sweep = sweeps.get(tf) or {}
        level = _safe_float(sweep.get("level"), None)
        if level is None:
            continue
        if action == "BUY" and sl_val >= level - tol:
            return False, "sl inside liquidity"
        if action == "SELL" and sl_val <= level + tol:
            return False, "sl inside liquidity"
    return True, None


def _ltf_structure_block(direction: str, human_layer: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Check if 5m/15m structure contradicts HTF direction without a confirming BOS."""
    direction = _sanitize_action(direction)
    if direction not in ("BUY", "SELL"):
        return True, "invalid direction"
    struct = human_layer.get("structure", {}) if human_layer else {}
    bos = human_layer.get("bos_choch", {}) if human_layer else {}
    struct5 = struct.get("5m", {})
    struct15 = struct.get("15m", {})
    bos5 = bos.get("5m", {})
    bos15 = bos.get("15m", {})

    bearish_struct = (struct5.get("label") == "LH-LL") or (struct15.get("label") == "LH-LL") or (
        struct5.get("bias") == "bearish" or struct15.get("bias") == "bearish"
    )
    bullish_struct = (struct5.get("label") == "HH-HL") or (struct15.get("label") == "HH-HL") or (
        struct5.get("bias") == "bullish" or struct15.get("bias") == "bullish"
    )
    bullish_bos = bos5.get("direction") == "bullish" or bos15.get("direction") == "bullish"
    bearish_bos = bos5.get("direction") == "bearish" or bos15.get("direction") == "bearish"

    if direction == "BUY" and bearish_struct and not bullish_bos:
        return True, "LTF bearish structure"
    if direction == "SELL" and bullish_struct and not bearish_bos:
        return True, "LTF bullish structure"
    return False, None


def _recalc_levels_from_risk(
    action: str,
    entry: Optional[float],
    sl: Optional[float],
    channel_bounds: Optional[Dict[str, float]] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Rebuild TP levels using only entry/SL and optional channel bounds when structural TPs failed."""
    action = _sanitize_action(action)
    entry_val = _safe_float(entry, None)
    sl_val = _safe_float(sl, None)
    if action not in ("BUY", "SELL") or entry_val is None or sl_val is None:
        return None, None, None
    risk = abs(entry_val - sl_val)
    if risk <= 0:
        return None, None, None

    base_gap = max(3.0, risk * 0.25)
    tp1_gap = max(2.5, risk + 0.5)
    if action == "BUY":
        tp1 = entry_val + tp1_gap
        tp2 = tp1 + base_gap
        upper = channel_bounds.get("upper") if channel_bounds else None
        tp3 = max(tp2 + base_gap, tp2 + 3.0)
        if upper and upper > tp2:
            tp3 = max(tp2 + 3.0, min(upper, tp2 + max(base_gap, 5.0)))
    else:
        tp1 = entry_val - tp1_gap
        tp2 = tp1 - base_gap
        lower = channel_bounds.get("lower") if channel_bounds else None
        tp3 = min(tp2 - base_gap, tp2 - 3.0)
        if lower and lower < tp2:
            tp3 = min(tp2 - 3.0, max(lower, tp2 - max(base_gap, 5.0)))
    return round(tp1, 2), round(tp2, 2), round(tp3, 2)


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
    swing_low: Optional[float] = None,
    swing_high: Optional[float] = None,
    channel_bounds: Optional[Dict[str, float]] = None,
) -> Tuple[Optional[float], List[float]]:
    """Ensure SL/TP respect BUY/SELL geometry and sanitize NaN/None."""
    action = _sanitize_action(action)
    entry = float(entry)
    fallback = max(entry * 0.001, 0.5)
    atr1h_val = _safe_float(atr1h, None)
    atr5_val = _safe_float(atr5, None)
    ref_sl_atr = atr1h_val if atr1h_val and atr1h_val > 0 else (atr5_val if atr5_val and atr5_val > 0 else fallback)

    min_sl_band = 6.0
    max_sl_band = 12.0
    min_tp1 = 2.5
    max_tp1 = 7.0
    tp_gap = 5.0

    soft_sl_min = max(min_sl_band, ref_sl_atr * 0.8 if ref_sl_atr else min_sl_band)
    channel_lower = channel_bounds.get("lower") if channel_bounds else None
    channel_upper = channel_bounds.get("upper") if channel_bounds else None

    safe_sl: Optional[float]
    if action == "BUY":
        candidate_sl = _safe_float(sl)
        if swing_low is not None:
            candidate_sl = swing_low if candidate_sl is None else min(candidate_sl, swing_low)
        elif channel_lower is not None:
            candidate_sl = channel_lower if candidate_sl is None else min(candidate_sl, channel_lower)
        if candidate_sl is not None:
            sl_dist = entry - candidate_sl
            sl_dist = min(max(sl_dist, soft_sl_min), max_sl_band)
            candidate_sl = entry - sl_dist
        else:
            candidate_sl = entry - min(max(soft_sl_min, min_sl_band), max_sl_band)
        safe_sl = candidate_sl if candidate_sl < entry else entry - soft_sl_min

        raw_tps: List[float] = []
        for tp in tps:
            tp_val = _safe_float(tp)
            if tp_val is not None and tp_val > entry:
                raw_tps.append(tp_val)
        while len(raw_tps) < 3:
            raw_tps.append(entry + min_tp1)

        structural_tp1 = raw_tps[0] if raw_tps else None
        tp1 = entry + min_tp1
        if structural_tp1 and structural_tp1 > entry:
            if (structural_tp1 - entry) > max_tp1:
                tp1 = structural_tp1
            else:
                tp1 = min(max(structural_tp1, entry + min_tp1), entry + max_tp1)
        else:
            tp1 = min(max(tp1, entry + min_tp1), entry + max_tp1)

        tp2 = tp1 + tp_gap
        tp3_structural = None
        if len(raw_tps) > 2 and raw_tps[2] > tp2:
            tp3_structural = raw_tps[2]
        tp3 = tp2 + tp_gap
        if tp3_structural and tp3_structural > tp2:
            tp3 = min(tp3, tp3_structural) if tp3_structural < tp3 else tp3_structural
        safe_tps = [tp1, tp2, tp3]
    else:
        candidate_sl = _safe_float(sl)
        if swing_high is not None:
            candidate_sl = swing_high if candidate_sl is None else max(candidate_sl, swing_high)
        elif channel_upper is not None:
            candidate_sl = channel_upper if candidate_sl is None else max(candidate_sl, channel_upper)
        if candidate_sl is not None:
            sl_dist = candidate_sl - entry
            sl_dist = min(max(sl_dist, soft_sl_min), max_sl_band)
            candidate_sl = entry + sl_dist
        else:
            candidate_sl = entry + min(max(soft_sl_min, min_sl_band), max_sl_band)
        safe_sl = candidate_sl if candidate_sl > entry else entry + soft_sl_min

        raw_tps = []
        for tp in tps:
            tp_val = _safe_float(tp)
            if tp_val is not None and tp_val < entry:
                raw_tps.append(tp_val)
        while len(raw_tps) < 3:
            raw_tps.append(entry - min_tp1)

        structural_tp1 = raw_tps[0] if raw_tps else None
        tp1 = entry - min_tp1
        if structural_tp1 and structural_tp1 < entry:
            if (entry - structural_tp1) > max_tp1:
                tp1 = structural_tp1
            else:
                tp1 = max(min(structural_tp1, entry - min_tp1), entry - max_tp1)
        else:
            tp1 = max(min(tp1, entry - min_tp1), entry - max_tp1)

        tp2 = tp1 - tp_gap
        tp3_structural = None
        if len(raw_tps) > 2 and raw_tps[2] < tp2:
            tp3_structural = raw_tps[2]
        tp3 = tp2 - tp_gap
        if tp3_structural and tp3_structural < tp2:
            tp3 = max(tp3, tp3_structural) if tp3_structural > tp3 else tp3_structural
        safe_tps = [tp1, tp2, tp3]

    if safe_sl is None:
        return None, []
    safe_tps = _order_tps(action, [round(float(tp), 2) for tp in safe_tps])
    return round(float(safe_sl), 2), safe_tps


def _order_tps(action: str, tps: List[float]) -> List[float]:
    """Sort TPs so they are ordered correctly for BUY/SELL directions."""
    if action == "BUY":
        return sorted(tps)
    return sorted(tps, reverse=True)


def _micro_body_stats(candle: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Return body, range, upper wick, lower wick for quick micro-candle checks."""
    open_, high, low, close = map(float, (candle.get("open"), candle.get("high"), candle.get("low"), candle.get("close")))
    body = abs(close - open_)
    rng = max(high - low, 1e-8)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    return body, rng, upper_wick, lower_wick


def _micro_structural_targets(df_15m, df_1h, entry: float, direction: str) -> Optional[float]:
    """Pick the nearest structural level (15m/1h swing) beyond entry for TP3."""
    candidates: List[float] = []
    for df in (df_15m, df_1h):
        swings = _local_swings(df, lookback=80, window=2)
        highs = [h["price"] for h in swings.get("highs", [])]
        lows = [l["price"] for l in swings.get("lows", [])]
        if direction == "BUY":
            candidates.extend([h for h in highs if h > entry])
        else:
            candidates.extend([l for l in lows if l < entry])
    if not candidates:
        return None
    if direction == "BUY":
        return min(candidates)
    return max(candidates)


def _micro_sl_tp(entry: float, direction: str, swing_low: Optional[float], swing_high: Optional[float], structural_tp: Optional[float]) -> Tuple[float, float, float]:
    """
    Micro scalp-specific SL/TP logic with strict clamps:
    - SL at last micro swing +/-3 USD
    - SL distance clamped to [8, 15] USD
    - TP1 forced to 3-7 USD away from entry
    - TP2 = TP1 +/- 5
    - TP3 = nearest structural level (fallback to TP2 +/- 5)
    """
    action = _sanitize_action(direction)
    if action not in ("BUY", "SELL"):
        raise ValueError("Micro SL/TP requires BUY or SELL direction")

    if action == "BUY":
        base_sl = (swing_low - 3) if swing_low is not None else entry - 10
        dist = entry - base_sl
        if dist < 8:
            sl = entry - 8
        elif dist > 15:
            sl = entry - 15
        else:
            sl = base_sl

        tp1 = entry + max(3.0, min(7.0, (entry - sl) * 0.65))
        tp2 = tp1 + 5.0
        if structural_tp and structural_tp > max(tp2, entry):
            tp3 = structural_tp
        else:
            tp3 = tp2 + 5.0
    else:
        base_sl = (swing_high + 3) if swing_high is not None else entry + 10
        dist = base_sl - entry
        if dist < 8:
            sl = entry + 8
        elif dist > 15:
            sl = entry + 15
        else:
            sl = base_sl

        tp1 = entry - max(3.0, min(7.0, (sl - entry) * 0.65))
        tp2 = tp1 - 5.0
        if structural_tp and structural_tp < min(tp2, entry):
            tp3 = structural_tp
        else:
            tp3 = tp2 - 5.0

    return round(sl, 2), round(tp1, 2), round(tp2, 2), round(tp3, 2)


def _should_block_duplicate(entry: float, action: str) -> bool:
    last_entry = _LAST_SIGNAL_STATE.get("entry")
    last_action = _LAST_SIGNAL_STATE.get("action")
    last_ts = _LAST_SIGNAL_STATE.get("ts")
    now = time.time()
    if last_entry is not None and last_action == action and last_ts:
        if abs(float(entry) - float(last_entry)) < _DUPLICATE_BAND and (now - float(last_ts)) <= _DUPLICATE_WINDOW_SEC:
            return True
    return False


def _record_signal(entry: float, action: str) -> None:
    _LAST_SIGNAL_STATE["entry"] = float(entry)
    _LAST_SIGNAL_STATE["action"] = action
    _LAST_SIGNAL_STATE["ts"] = time.time()


def _validate_final_signal(final: Dict[str, Any]) -> Optional[str]:
    action = _sanitize_action(final.get("action"))
    if action not in ("BUY", "SELL"):
        return "invalid action"
    htf_dir = _sanitize_action(final.get("htf_direction"))
    if htf_dir in ("BUY", "SELL") and htf_dir != action:
        return "direction mismatch"
    entry = _safe_float(final.get("entry"), None)
    sl = _safe_float(final.get("sl"), None)
    tp1 = _safe_float(final.get("tp1") if final.get("tp1") is not None else final.get("tp"), None)
    tp2 = _safe_float(final.get("tp2"), None)
    tp3 = _safe_float(final.get("tp3"), None)
    atr5 = _safe_float(final.get("atr5"), None)
    atr15 = _safe_float(final.get("atr15"), None)

    low_vol, _ = _is_low_volatility(atr5, atr15)
    if low_vol:
        return "low volatility"
    if entry is None or sl is None or tp1 is None or tp2 is None or tp3 is None:
        return "missing levels"

    fallback = max(entry * 0.001, 0.5)
    ref_tp = atr5 if atr5 and atr5 > 0 else fallback
    min_tp1_diff = max(2.5, ref_tp * 0.5)
    risk = abs(entry - sl)

    if risk <= 0 or risk > 18.0:
        return "sl distance invalid"

    if action == "BUY":
        if not (sl < entry < tp1 and tp2 > entry and tp3 > entry):
            return "invalid geometry"
        if (tp1 - entry) < min_tp1_diff:
            return "tp1 too close"
        if (tp2 - tp1) < 3.0:
            return "tp2 gap invalid"
        if (tp1 - entry) <= risk:
            return "rr below 1"
    else:
        if not (sl > entry > tp1 and tp2 < entry and tp3 < entry):
            return "invalid geometry"
        if (entry - tp1) < min_tp1_diff:
            return "tp1 too close"
        if (tp1 - tp2) < 3.0:
            return "tp2 gap invalid"
        if (entry - tp1) <= risk:
            return "rr below 1"
    return None


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
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    swings_5 = _local_swings(df_5m, lookback=40, window=2)
    swings_15 = _local_swings(df_15m, lookback=60, window=2)
    highs = [h["price"] for h in swings_5.get("highs", []) + swings_15.get("highs", [])]
    lows = [l["price"] for l in swings_5.get("lows", []) + swings_15.get("lows", [])]
    swing_high = max(highs) if highs else None
    swing_low = min(lows) if lows else None

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

    sl, tps = _sanitize_levels(
        direction,
        entry,
        sl_level,
        [tp1, tp2, tp3],
        atr1h,
        atr5,
        swing_low=swing_low,
        swing_high=swing_high,
        channel_bounds=channel_ctx.get("bounds"),
    )
    if sl is None or len(tps) < 3:
        return None, None, None, None
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


def _is_zone_exhausted(direction: str, zones: Dict[str, Any], structure: Dict[str, Any]) -> bool:
    """Determine if demand/supply is exhausted based on limited touches and structure bias."""
    direction = _sanitize_action(direction)
    struct_bias = structure.get("1H", {}).get("bias") or structure.get("15m", {}).get("bias")
    if direction == "BUY":
        demand = zones.get("demand", {})
        if demand.get("range_bound"):
            return False
        touches = demand.get("touches", 0)
        if touches > 6 and struct_bias != "bullish":
            return True
    elif direction == "SELL":
        supply = zones.get("supply", {})
        if supply.get("range_bound"):
            return False
        touches = supply.get("touches", 0)
        if touches > 6 and struct_bias != "bearish":
            return True
    return False


def _ict_direction(struct4h: Dict[str, Any], struct1h: Dict[str, Any]) -> str:
    """Derive ICT bias from HTF structure only (no indicators)."""
    if struct4h.get("bias") == "bullish" and struct1h.get("bias") == "bullish":
        return "BUY"
    if struct4h.get("bias") == "bearish" and struct1h.get("bias") == "bearish":
        return "SELL"
    return "NO_TRADE"


def run_ict_layer(df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
    """Pure ICT/SMC layer, isolated from other engines and indicators."""
    if len(df_5m) < 10 or len(df_15m) < 10 or len(df_1h) < 20 or len(df_4h) < 20:
        return {"action": "NO_TRADE", "reason": "insufficient data", "signal_type": "ICT"}

    last5 = df_5m.iloc[-1]
    price = float(last5["close"])

    struct_4h = _detect_structure(df_4h, lookback=140, window=3)
    struct_1h = _detect_structure(df_1h, lookback=140, window=3)
    struct_15m = _detect_structure(df_15m, lookback=120, window=2)
    struct_5m = _detect_structure(df_5m, lookback=80, window=2)

    direction = _ict_direction(struct_4h, struct_1h)
    relaxed = False
    if direction == "NO_TRADE":
        htf_bearish = struct_4h.get("bias") == "bearish" or struct_1h.get("bias") == "bearish"
        zones_1h = _detect_zones(df_1h)
        demand_conf = zones_1h.get("demand", {}).get("confidence", 0)
        choch_bull = _detect_bos_choch(df_15m, "15m").get("direction") == "bullish"
        swing_hl = struct_15m.get("label") == "HH-HL" or struct_15m.get("bias") == "bullish"
        if (not htf_bearish) and choch_bull and demand_conf >= 40 and swing_hl:
            direction = "BUY"
            relaxed = True
        else:
            return {"action": "NO_TRADE", "reason": "htf not aligned", "signal_type": "ICT"}
    if direction == "BUY" and (struct_4h.get("bias") == "bearish" and struct_1h.get("bias") == "bearish"):
        return {"action": "NO_TRADE", "reason": "htf contradicts", "signal_type": "ICT"}

    sweep15 = _liquidity_sweep(df_15m, lookback=30)
    bos15 = _detect_bos_choch(df_15m, "15m")
    sweep_cond = (sweep15.get("type") == "below" and direction == "BUY") or (sweep15.get("type") == "above" and direction == "SELL")
    bos_cond = bos15.get("direction") == ("bullish" if direction == "BUY" else "bearish")
    if not (sweep_cond and bos_cond):
        return {"action": "NO_TRADE", "reason": "no 15m sweep + displacement", "signal_type": "ICT"}

    fvg5 = _fvg_band(df_5m)
    ob5 = _detect_order_block(df_5m, direction)
    mitigation_ok = False
    if fvg5 and fvg5.get("low") is not None and fvg5.get("high") is not None:
        mitigation_ok |= fvg5["low"] <= price <= fvg5["high"]
    if ob5 and ob5.get("low") is not None and ob5.get("high") is not None:
        mitigation_ok |= ob5["low"] <= price <= ob5["high"]
    if not mitigation_ok:
        return {"action": "NO_TRADE", "reason": "no 5m mitigation", "signal_type": "ICT"}

    swing_high = struct_1h.get("last_high") or struct_4h.get("last_high")
    swing_low = struct_1h.get("last_low") or struct_4h.get("last_low")
    pd = _pd_rate(price, swing_high, swing_low)
    if pd is None:
        return {"action": "NO_TRADE", "reason": "missing range for PD", "signal_type": "ICT"}
    if direction == "BUY" and pd > 0.5:
        return {"action": "NO_TRADE", "reason": "not in discount", "signal_type": "ICT"}
    if direction == "SELL" and pd < 0.5:
        return {"action": "NO_TRADE", "reason": "not in premium", "signal_type": "ICT"}

    entry_price = _ict_entry_from_mitigation(ob5 or {}, fvg5)
    if entry_price is None:
        entry_price = price

    if direction == "BUY":
        zone_low = min([v for v in [ob5.get("low") if ob5 else None, fvg5.get("low") if fvg5 else None, entry_price - 1.0] if v is not None])
        sl = round(zone_low, 2)
        if sl >= entry_price:
            return {"action": "NO_TRADE", "reason": "invalid sl", "signal_type": "ICT"}
    else:
        zone_high = max([v for v in [ob5.get("high") if ob5 else None, fvg5.get("high") if fvg5 else None, entry_price + 1.0] if v is not None])
        sl = round(zone_high, 2)
        if sl <= entry_price:
            return {"action": "NO_TRADE", "reason": "invalid sl", "signal_type": "ICT"}

    targets = _liquidity_targets(df_5m, df_15m, entry_price, direction)
    risk = abs(entry_price - sl)
    if risk <= 0:
        return {"action": "NO_TRADE", "reason": "invalid risk", "signal_type": "ICT"}

    min_tp = entry_price + risk * 2 if direction == "BUY" else entry_price - risk * 2
    if targets:
        tp1 = targets[0] if (direction == "BUY" and targets[0] > min_tp) or (direction == "SELL" and targets[0] < min_tp) else min_tp
        tp2 = targets[1] if len(targets) > 1 else (tp1 + risk if direction == "BUY" else tp1 - risk)
        tp3 = targets[2] if len(targets) > 2 else (tp2 + risk if direction == "BUY" else tp2 - risk)
    else:
        tp1 = min_tp
        tp2 = tp1 + risk if direction == "BUY" else tp1 - risk
        tp3 = tp2 + risk if direction == "BUY" else tp2 - risk

    _, rr = _risk_reward(entry_price, sl, tp1, direction)
    if rr is None or rr < 2.0:
        return {"action": "NO_TRADE", "reason": "rr below 2", "signal_type": "ICT"}

    reasoning = [
        f"HTF bias {direction} via structure",
        f"15m sweep {sweep15.get('type')} with BOS {bos15.get('direction')}",
        "5m mitigation into FVG/OB",
        f"Premium/discount rate {pd:.2f}",
        f"RR {rr:.2f}",
    ]
    return {
        "action": direction,
        "entry": round(float(entry_price), 2),
        "sl": round(float(sl), 2),
        "tp": round(float(tp1), 2),
        "tp1": round(float(tp1), 2),
        "tp2": round(float(tp2), 2),
        "tp3": round(float(tp3), 2),
        "reasoning": reasoning,
        "signal_type": "ICT",
        "structure": {"4h": struct_4h, "1h": struct_1h, "15m": struct_15m, "5m": struct_5m},
        "debug_relaxed_rules": relaxed,
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
    atr5_val = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr15_val = _safe_float(last15.get("atr"), atr5_val) or atr5_val

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(
        _safe_float(last5.get("adx"), 0),
        _safe_float(last15.get("adx"), 0),
        _safe_float(last1h.get("adx"), 0),
        _safe_float(last4h.get("adx"), 0),
    )
    weak_momentum = (_safe_float(last5.get("adx"), 0) or 0) < 20 or (_safe_float(last15.get("adx"), 0) or 0) < 20
    relaxed = weak_momentum

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

    ltf_blocked, ltf_reason = _ltf_structure_block(direction, human_layer)
    if ltf_blocked:
        return {
            "action": "NO_TRADE",
            "reason": ltf_reason,
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    low_vol, vol_ctx = _is_low_volatility(atr5_val, atr15_val)
    if direction in ("BUY", "SELL") and low_vol:
        return {
            "action": "NO_TRADE",
            "reason": "low volatility",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
            "atr5": vol_ctx["atr5"],
            "atr15": vol_ctx["atr15"],
        }

    sweep5 = _liquidity_sweep(df_5m, lookback=20)
    bos5 = human_layer.get("bos_choch", {}).get("5m", {})
    bos15 = human_layer.get("bos_choch", {}).get("15m", {})
    channel_ctx = _detect_channel_context(df_5m, price)
    zones = human_layer.get("zones", _detect_zones(df_1h))
    atr1h = _safe_float(last1h.get("atr"), atr5_val) or atr5_val
    if _is_zone_exhausted(direction, zones, human_layer.get("structure", {})):
        return {
            "action": "NO_TRADE",
            "reason": "weak zone",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5_val, atr1h)
    if sl is None or tp1 is None or tp2 is None or tp3 is None:
        return {
            "action": "NO_TRADE",
            "reason": "invalid levels",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

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
        "momentum": not weak_momentum,
    }
    score, breakdown = _score_trade(score_ctx)

    risk, rr = _risk_reward(price, sl, tp1, direction)
    if rr is not None and rr <= 1.0:
        return {
            "action": "NO_TRADE",
            "reason": "rr below 1",
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    fvg5 = _fvg_band(df_5m)
    fvg15 = _fvg_band(df_15m)
    quality_ok, quality_reason = _level_quality_filter(
        direction, price, sl, zones, [fvg5, fvg15], human_layer.get("liquidity_sweeps")
    )
    if not quality_ok:
        return {
            "action": "NO_TRADE",
            "reason": quality_reason,
            "signal_type": "SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h, "15m": trend_15},
        }

    action = direction if score >= 50 or relaxed else direction if score >= 60 else "NO_TRADE"
    confidence_base = float(min(100, max(55 if relaxed else 60, score)))
    confidence = confidence_base - 10 if weak_momentum else confidence_base

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
        "atr5": atr5_val,
        "atr15": atr15_val,
        "reasoning": human_layer.get("explanation", []),
        "adx_conf": adx_conf,
        "debug_relaxed_rules": relaxed,
    }


def micro_scalp_layer(df_5m, df_15m, df_1h, df_4h, human_layer: Dict[str, Any]) -> Dict[str, Any]:
    """
    Micro scalp layer:
    - Uses last 2-4 candles on 5m to detect momentum + wick rejection + micro-structure
    - SL anchored to local swing with strict 8-15 USD clamp
    - TP1 forced 3-7 USD away, TP2=TP1±5, TP3=next structural HTF level
    """
    if len(df_5m) < 4:
        return {"action": "NO_TRADE", "reason": "insufficient data", "signal_type": "MICRO_SCALP"}

    last5 = df_5m.iloc[-1]
    tail4 = df_5m.tail(4)
    recent5 = df_5m.tail(5)
    price = float(last5["close"])

    trend_4h = _trend(df_4h.iloc[-1])
    trend_1h = _trend(df_1h.iloc[-1])
    htf_direction = _final_direction(trend_4h, trend_1h)
    if htf_direction == "NO_TRADE":
        return {"action": "NO_TRADE", "reason": "HTF conflict", "signal_type": "MICRO_SCALP"}

    atr5_val = _safe_float(last5.get("atr"), price * 0.0025) or price * 0.0025
    atr15_val = _safe_float(df_15m.iloc[-1].get("atr"), atr5_val) or atr5_val
    weak_momentum = ((_safe_float(last5.get("adx"), 0) or 0) < 20) or ((_safe_float(df_15m.iloc[-1].get("adx"), 0) or 0) < 20)

    body, rng, upper_wick, lower_wick = _micro_body_stats(last5)
    body_dominant = body > upper_wick and body > lower_wick and body >= 0.5 * rng
    wick_bull, wick_bear = _wick_rejection(last5)
    hist = tail4["macd"] - tail4["macd_signal"] if "macd" in tail4.columns and "macd_signal" in tail4.columns else None
    rsi_rising = False
    hist_rising = False
    if "rsi" in tail4.columns and len(tail4["rsi"].dropna()) >= 2:
        rsi_rising = tail4["rsi"].iloc[-1] > tail4["rsi"].iloc[-2]
    if hist is not None and len(hist.dropna()) >= 2:
        hist_rising = hist.iloc[-1] > hist.iloc[-2]

    closes_up = tail4["close"].diff().dropna().gt(0)
    closes_down = tail4["close"].diff().dropna().lt(0)
    range_mean = (tail4["high"] - tail4["low"]).mean()
    body_mean = (tail4["close"] - tail4["open"]).abs().mean()
    bullish_push = (
        last5["close"] > last5["open"]
        and closes_up.tail(2).all()
        and body >= max(range_mean * 0.6, body_mean)
        and body_dominant
    )
    bearish_push = (
        last5["close"] < last5["open"]
        and closes_down.tail(2).all()
        and body >= max(range_mean * 0.6, body_mean)
        and body_dominant
    )

    sweep = _liquidity_sweep(df_5m, lookback=12)
    bos15 = human_layer.get("bos_choch", {}).get("15m", {})
    zones = human_layer.get("zones", {})
    micro_swings = _local_swings(df_5m, lookback=10, window=1)
    swing_low = micro_swings.get("lows", [])[-1]["price"] if micro_swings.get("lows") else None
    swing_high = micro_swings.get("highs", [])[-1]["price"] if micro_swings.get("highs") else None
    micro_bias = _structure_bias(micro_swings)

    minor_support = float(recent5["low"].min())
    minor_resistance = float(recent5["high"].max())
    bounce_support = last5["low"] <= minor_support * 1.002 and last5["close"] > last5["open"]
    bounce_resistance = last5["high"] >= minor_resistance * 0.998 and last5["close"] < last5["open"]

    structural_tp = _micro_structural_targets(df_15m, df_1h, price, htf_direction)

    direction = htf_direction
    if direction == "BUY":
        sweep_ok = sweep.get("type") != "above"
        rules_ok = all(
            [
                body_dominant and last5["close"] > last5["open"],
                sweep_ok,
                bounce_support,
                micro_bias in ("bullish", "neutral"),
            ]
        )
        wick_ok = wick_bull or lower_wick > upper_wick
    else:
        sweep_ok = sweep.get("type") != "below"
        rules_ok = all(
            [
                body_dominant and last5["close"] < last5["open"],
                sweep_ok,
                bounce_resistance,
                micro_bias in ("bearish", "neutral"),
            ]
        )
        wick_ok = wick_bear or upper_wick > lower_wick

    sl, tp1, tp2, tp3 = _micro_sl_tp(price, direction, swing_low, swing_high, structural_tp)
    risk, rr = _risk_reward(price, sl, tp1, direction)
    if not rules_ok and (rr is None or rr < 1.0):
        return {
            "action": "NO_TRADE",
            "reason": "Micro rules not satisfied",
            "signal_type": "MICRO_SCALP",
            "trend": {"4h": trend_4h, "1h": trend_1h},
        }

    score_penalty = 0
    # BOS / zone filters cannot be bypassed by relaxed momentum
    if direction == "BUY" and bos15.get("direction") == "bearish":
        score_penalty += 25
        if not (wick_bull or sweep.get("type") == "below"):
            return {
                "action": "NO_TRADE",
                "reason": "15m bos bearish",
                "signal_type": "MICRO_SCALP",
                "trend": {"4h": trend_4h, "1h": trend_1h},
            }
    if direction == "BUY":
        supply = zones.get("supply", {})
        zone = supply.get("zone")
        if supply.get("confidence", 0) >= 80 and _inside_zone(price, zone):
            if not (micro_bias == "bullish" or (rsi_rising and hist_rising)):
                return {
                    "action": "NO_TRADE",
                    "reason": "inside strong supply",
                    "signal_type": "MICRO_SCALP",
                    "trend": {"4h": trend_4h, "1h": trend_1h},
                }

    score = 0
    score += 20  # HTF alignment baseline
    score += 20 if bullish_push or bearish_push else 10
    score += 15 if (rsi_rising or hist_rising) else 0
    score += 15 if (bounce_support or bounce_resistance) else 0
    score += 10 if wick_ok else 0
    score += 10 if sweep_ok else 0
    score += 10 if micro_bias == ("bullish" if direction == "BUY" else "bearish") else 5
    score = max(0, score - score_penalty)
    confidence = float(min(100, max(55 if weak_momentum else 60, score)))
    if weak_momentum:
        confidence = max(50.0, confidence - 5)

    return {
        "action": direction,
        "entry": round(price, 2),
        "sl": sl,
        "tp": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "signal_type": "MICRO_SCALP",
        "confidence": confidence,
        "score": score,
        "score_breakdown": {
            "htf_alignment": 20,
            "momentum": 20 if bullish_push or bearish_push else 10,
            "oscillator": 15 if (rsi_rising or hist_rising) else 0,
            "bounce": 15 if (bounce_support or bounce_resistance) else 0,
            "wick": 10 if wick_ok else 0,
            "liquidity": 10 if sweep_ok else 0,
            "structure": 10 if micro_bias == ("bullish" if direction == "BUY" else "bearish") else 5,
        },
        "trend": {"4h": trend_4h, "1h": trend_1h},
        "atr5": atr5_val,
        "atr15": atr15_val,
        "htf_direction": htf_direction,
        "reasoning": human_layer.get("explanation", []),
        "debug_relaxed_rules": weak_momentum or not rules_ok,
        "micro_context": {
            "body_dominant": body_dominant,
            "wick_reject": {"bullish": wick_bull, "bearish": wick_bear},
            "rsi_rising": rsi_rising,
            "hist_rising": hist_rising,
            "bounce_support": bounce_support,
            "bounce_resistance": bounce_resistance,
            "sweep": sweep,
            "micro_bias": micro_bias,
        },
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
    trend_15 = _trend(last15)
    atr5_val = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr15_val = _safe_float(last15.get("atr"), atr5_val) or atr5_val
    direction = _final_direction(trend_4h, trend_1h)
    if direction == "NO_TRADE":
        return {"action": "NO_TRADE", "reason": "HTF not aligned", "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}
    if trend_15 in ("bullish", "bearish") and (
        (trend_15 == "bullish" and direction == "SELL") or (trend_15 == "bearish" and direction == "BUY")
    ):
        struct_15 = human_layer.get("structure", {}).get("15m", {})
        if not (struct_15.get("label") == "HH-HL" and direction == "BUY"):
            return {"action": "NO_TRADE", "reason": "15m cannot contradict HTF", "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

    adx5_val = _safe_float(last5.get("adx"), 0)
    adx15_val = _safe_float(last15.get("adx"), 0)
    weak_momentum = (adx5_val or 0) < 20 or (adx15_val or 0) < 20
    relaxed = weak_momentum

    ltf_blocked, ltf_reason = _ltf_structure_block(direction, human_layer)
    if ltf_blocked and not (human_layer.get("structure", {}).get("15m", {}).get("label") == "HH-HL" and direction == "BUY"):
        return {"action": "NO_TRADE", "reason": ltf_reason, "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

    low_vol, vol_ctx = _is_low_volatility(atr5_val, atr15_val)
    if low_vol:
        return {
            "action": "NO_TRADE",
            "reason": "low volatility",
            "signal_type": "ULTRA",
            "atr5": vol_ctx["atr5"],
            "atr15": vol_ctx["atr15"],
        }

    sweep = _liquidity_sweep(df_5m, lookback=20)
    bos = _detect_bos_choch(df_5m, "5m")
    wick_bull, wick_bear = _wick_rejection(last5)
    wick_ok = (wick_bull and direction == "BUY") or (wick_bear and direction == "SELL")

    zones = human_layer.get("zones", _detect_zones(df_1h))
    channel_ctx = _detect_channel_context(df_5m, price)
    atr1h = _safe_float(last1h.get("atr"), atr5_val) or atr5_val
    if _is_zone_exhausted(direction, zones, human_layer.get("structure", {})):
        return {"action": "NO_TRADE", "reason": "weak zone", "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5_val, atr1h)
    if sl is None or tp1 is None or tp2 is None or tp3 is None:
        return {"action": "NO_TRADE", "reason": "invalid levels", "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

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
        "momentum": not weak_momentum,
    }
    score, breakdown = _score_trade(score_ctx)
    action = direction if score >= 50 or relaxed else direction if score >= 60 else "NO_TRADE"

    risk, rr = _risk_reward(price, sl, tp1, direction)
    if rr is not None and rr <= 1.0:
        return {"action": "NO_TRADE", "reason": "rr below 1", "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

    fvg5 = _fvg_band(df_5m)
    fvg15 = _fvg_band(df_15m)
    quality_ok, quality_reason = _level_quality_filter(
        direction, price, sl, zones, [fvg5, fvg15], human_layer.get("liquidity_sweeps")
    )
    if not quality_ok:
        return {"action": "NO_TRADE", "reason": quality_reason, "signal_type": "ULTRA", "atr5": atr5_val, "atr15": atr15_val}

    confidence_base = float(min(100, max(55 if relaxed else 60, score)))
    confidence = confidence_base - 10 if weak_momentum else confidence_base

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
        "atr5": atr5_val,
        "atr15": atr15_val,
        "reasoning": human_layer.get("explanation", []),
        "debug_relaxed_rules": relaxed,
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
    atr5_val = _safe_float(last5.get("atr"), price * 0.003) or price * 0.003
    atr15_val = _safe_float(last15.get("atr"), atr5_val) or atr5_val
    direction = _final_direction(trend_4h, trend_1h)
    if direction == "NO_TRADE":
        return {
            "action": "NO_TRADE",
            "reason": "HTF not aligned",
            "signal_type": "ULTRA_V3",
            "atr5": atr5_val,
            "atr15": atr15_val,
        }
    if trend_15 in ("bullish", "bearish") and (
        (trend_15 == "bullish" and direction == "SELL") or (trend_15 == "bearish" and direction == "BUY")
    ):
        return {"action": "NO_TRADE", "reason": "15m confirm failed", "signal_type": "ULTRA_V3"}

    adx5_val = _safe_float(last5.get("adx"), 0)
    adx15_val = _safe_float(last15.get("adx"), 0)
    weak_momentum = (adx5_val or 0) < 20 or (adx15_val or 0) < 20
    relaxed = weak_momentum

    ltf_blocked, ltf_reason = _ltf_structure_block(direction, human_layer)
    if ltf_blocked and not (human_layer.get("structure", {}).get("15m", {}).get("label") == "HH-HL" and direction == "BUY"):
        return {"action": "NO_TRADE", "reason": ltf_reason, "signal_type": "ULTRA_V3"}

    low_vol, vol_ctx = _is_low_volatility(atr5_val, atr15_val)
    if low_vol:
        return {
            "action": "NO_TRADE",
            "reason": "low volatility",
            "signal_type": "ULTRA_V3",
            "atr5": vol_ctx["atr5"],
            "atr15": vol_ctx["atr15"],
        }

    sweep = _liquidity_sweep(df_5m, lookback=18)
    bos = _detect_bos_choch(df_5m, "5m")
    bos15 = _detect_bos_choch(df_15m, "15m")
    wick_bull, wick_bear = _wick_rejection(last5)
    wick_ok = (wick_bull and direction == "BUY") or (wick_bear and direction == "SELL")

    zones = human_layer.get("zones", _detect_zones(df_1h))
    channel_ctx = _detect_channel_context(df_5m, price)
    atr1h = _safe_float(last1h.get("atr"), atr5_val) or atr5_val
    if _is_zone_exhausted(direction, zones, human_layer.get("structure", {})):
        return {"action": "NO_TRADE", "reason": "weak zone", "signal_type": "ULTRA_V3"}

    sl, tp1, tp2, tp3 = _build_levels(direction, price, df_5m, df_15m, df_1h, zones, channel_ctx, atr5_val, atr1h)
    if sl is None or tp1 is None or tp2 is None or tp3 is None:
        return {"action": "NO_TRADE", "reason": "invalid levels", "signal_type": "ULTRA_V3"}

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
        "momentum": not weak_momentum,
    }
    score, breakdown = _score_trade(score_ctx)
    action = direction if score >= 50 or relaxed else direction if score >= 60 else "NO_TRADE"

    risk, rr = _risk_reward(price, sl, tp1, direction)
    if rr is not None and rr <= 1.0:
        return {"action": "NO_TRADE", "reason": "rr below 1", "signal_type": "ULTRA_V3"}

    fvg5 = _fvg_band(df_5m)
    fvg15 = _fvg_band(df_15m)
    quality_ok, quality_reason = _level_quality_filter(
        direction, price, sl, zones, [fvg5, fvg15], human_layer.get("liquidity_sweeps")
    )
    if not quality_ok:
        return {"action": "NO_TRADE", "reason": quality_reason, "signal_type": "ULTRA_V3"}

    confidence_base = float(min(100, max(55 if relaxed else 60, score)))
    confidence = confidence_base - 10 if weak_momentum else confidence_base

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
        "atr5": atr5_val,
        "atr15": atr15_val,
        "reasoning": human_layer.get("explanation", []),
        "debug_relaxed_rules": relaxed,
    }


def consolidate_signals(
    human_layer: Dict[str, Any],
    ict_layer: Dict[str, Any],
    micro_layer: Dict[str, Any],
    scalp_layer: Dict[str, Any],
    ultra_layer: Dict[str, Any],
    v3_layer: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge layers and emit a single stable decision."""
    master_direction = human_layer.get("htf_direction", "NO_TRADE")
    ltf_conflict, ltf_reason = (
        _ltf_structure_block(master_direction, human_layer) if master_direction in ("BUY", "SELL") else (False, None)
    )
    ict_action = _sanitize_action(ict_layer.get("action"))
    if ict_action in ("BUY", "SELL"):
        entry = _safe_float(ict_layer.get("entry"), None)
        sl = _safe_float(ict_layer.get("sl"), None)
        tp1 = _safe_float(ict_layer.get("tp1") or ict_layer.get("tp"), None)
        if entry is not None and sl is not None and tp1 is not None:
            if (ict_action == "BUY" and sl < entry < tp1) or (ict_action == "SELL" and sl > entry > tp1):
                _, rr = _risk_reward(entry, sl, tp1, ict_action)
                if rr is not None and rr >= 2.0:
                    final = dict(ict_layer)
                    final["signal_type"] = "ICT"
                    final["htf_direction"] = master_direction
                    final["layers"] = {
                        "human": human_layer,
                        "ict": ict_layer,
                        "micro_scalp": micro_layer,
                        "scalp": scalp_layer,
                        "ultra": ultra_layer,
                        "ultra_v3": v3_layer,
                    }
                    return final
    if ltf_conflict and _sanitize_action(micro_layer.get("action")) not in ("BUY", "SELL"):
        return {
            "action": "NO_TRADE",
            "reason": ltf_reason or "LTF waiting for BOS",
            "signal_type": "UNIFIED",
            "htf_direction": master_direction,
            "layers": {
                "human": human_layer,
                "ict": ict_layer,
                "micro_scalp": micro_layer,
                "scalp": scalp_layer,
                "ultra": ultra_layer,
                "ultra_v3": v3_layer,
            },
        }

    candidates = []
    bos15_dir = human_layer.get("bos_choch", {}).get("15m", {}).get("direction")
    sweep15 = human_layer.get("liquidity_sweeps", {}).get("15m", {})
    wicks15 = human_layer.get("wicks", {})
    zones = human_layer.get("zones", {})
    supply_zone = zones.get("supply", {})
    demand_zone = zones.get("demand", {})
    for name, layer in (
        ("MICRO_SCALP", micro_layer),
        ("SCALP", scalp_layer),
        ("ULTRA_V3", v3_layer),
        ("ULTRA", ultra_layer),
    ):
        action = _sanitize_action(layer.get("action"))
        if action not in ("BUY", "SELL"):
            continue
        if master_direction != "NO_TRADE" and action != master_direction:
            continue
        entry_val = _safe_float(layer.get("entry"), None)
        sl_val = _safe_float(layer.get("sl"), None)
        tp_val = _safe_float(layer.get("tp1") or layer.get("tp"), None)
        if action == "BUY" and bos15_dir == "bearish":
            layer["score"] = max(0, layer.get("score", 0) - 25)
            if not (wicks15.get("bullish") or sweep15.get("type") == "below"):
                continue
        if action == "BUY" and supply_zone.get("confidence", 0) >= 80 and entry_val is not None and _inside_zone(entry_val, supply_zone.get("zone")):
            micro_ctx = layer.get("micro_context", {})
            micro_bias = micro_ctx.get("micro_bias")
            rsi_rising = micro_ctx.get("rsi_rising")
            hist_rising = micro_ctx.get("hist_rising")
            if not (micro_bias == "bullish" or (rsi_rising and hist_rising)):
                continue
        if action == "SELL" and demand_zone.get("confidence", 0) >= 80 and entry_val is not None and _inside_zone(entry_val, demand_zone.get("zone")):
            continue
        risk, rr = _risk_reward(layer.get("entry"), layer.get("sl"), layer.get("tp1") or layer.get("tp"), action)
        score = layer.get("score", 0)
        confidence = _safe_float(layer.get("confidence"), 0) or 0
        priority = 1 if (name == "MICRO_SCALP" and score >= 70) else 0
        if ltf_conflict and name != "MICRO_SCALP":
            continue
        candidates.append(
            {
                "name": name,
                "score": score,
                "confidence": confidence,
                "payload": layer,
                "action": action,
                "priority": priority,
                "rr": rr,
            }
        )

    if not candidates:
        fallback_layers = [("ICT", ict_layer), ("MICRO_SCALP", micro_layer), ("SCALP", scalp_layer), ("ULTRA_V3", v3_layer), ("ULTRA", ultra_layer)]
        for name, layer in fallback_layers:
            act = _sanitize_action(layer.get("action"))
            entry = _safe_float(layer.get("entry"), None)
            sl = _safe_float(layer.get("sl"), None)
            tp1 = _safe_float(layer.get("tp1") or layer.get("tp"), None)
            if act in ("BUY", "SELL") and entry is not None and sl is not None and tp1 is not None:
                final = dict(layer)
                final["signal_type"] = "UNIFIED"
                final["htf_direction"] = master_direction
                final["layers"] = {
                    "human": human_layer,
                    "ict": ict_layer,
                    "micro_scalp": micro_layer,
                    "scalp": scalp_layer,
                    "ultra": ultra_layer,
                    "ultra_v3": v3_layer,
                }
                final["debug_relaxed_rules"] = final.get("debug_relaxed_rules", False) or ict_layer.get("debug_relaxed_rules") or False
                return final
        return {
            "action": "NO_TRADE",
            "reason": "No aligned signals after consolidation",
            "signal_type": "UNIFIED",
            "htf_direction": master_direction,
            "layers": {
                "human": human_layer,
                "ict": ict_layer,
                "micro_scalp": micro_layer,
                "scalp": scalp_layer,
                "ultra": ultra_layer,
                "ultra_v3": v3_layer,
            },
        }

    best = sorted(candidates, key=lambda x: (x["priority"], x["score"], x["confidence"], x.get("rr", 0)), reverse=True)[0]
    final = dict(best["payload"])
    final["action"] = best["action"]
    final["signal_type"] = "UNIFIED"
    final["htf_direction"] = master_direction
    final["score"] = best["score"]
    final["confidence"] = best["confidence"] if final["action"] != "NO_TRADE" else best["confidence"]
    final["human_summary"] = human_layer.get("explanation", [])

    entry = _safe_float(final.get("entry"), None)
    final["layers"] = {
        "human": human_layer,
        "ict": ict_layer,
        "micro_scalp": micro_layer,
        "scalp": scalp_layer,
        "ultra": ultra_layer,
        "ultra_v3": v3_layer,
    }
    final["debug_relaxed_rules"] = final.get("debug_relaxed_rules", False) or ict_layer.get("debug_relaxed_rules") or micro_layer.get("debug_relaxed_rules") or scalp_layer.get("debug_relaxed_rules") or ultra_layer.get("debug_relaxed_rules") or v3_layer.get("debug_relaxed_rules") or False
    if final["action"] in ("BUY", "SELL") and entry is not None:
        bos15_dir = human_layer.get("bos_choch", {}).get("15m", {}).get("direction")
        wicks15 = human_layer.get("wicks", {})
        zones = human_layer.get("zones", {})
        supply_zone = zones.get("supply", {})
        demand_zone = zones.get("demand", {})
        if final["action"] == "BUY":
            if bos15_dir == "bearish" and not wicks15.get("bullish"):
                return {
                    "action": "NO_TRADE",
                    "reason": "15m bos bearish",
                    "signal_type": "UNIFIED",
                    "htf_direction": master_direction,
                    "layers": final["layers"],
                }
            if supply_zone.get("confidence", 0) >= 80 and _inside_zone(entry, supply_zone.get("zone")):
                return {
                    "action": "NO_TRADE",
                    "reason": "inside strong supply",
                    "signal_type": "UNIFIED",
                    "htf_direction": master_direction,
                    "layers": final["layers"],
                }
        if final["action"] == "SELL":
            if bos15_dir == "bullish" and not wicks15.get("bearish"):
                return {
                    "action": "NO_TRADE",
                    "reason": "15m bos bullish",
                    "signal_type": "UNIFIED",
                    "htf_direction": master_direction,
                    "layers": final["layers"],
                }
            if demand_zone.get("confidence", 0) >= 80 and _inside_zone(entry, demand_zone.get("zone")):
                return {
                    "action": "NO_TRADE",
                    "reason": "inside strong demand",
                    "signal_type": "UNIFIED",
                    "htf_direction": master_direction,
                    "layers": final["layers"],
                }
        validation_error = _validate_final_signal(final)
        if validation_error:
            tp1_new, tp2_new, tp3_new = _recalc_levels_from_risk(
                final["action"], final.get("entry"), final.get("sl"), human_layer.get("channels", {}).get("bounds")
            )
            if tp1_new is not None and tp2_new is not None and tp3_new is not None:
                final["tp1"] = final["tp"] = tp1_new
                final["tp2"] = tp2_new
                final["tp3"] = tp3_new
                validation_error = _validate_final_signal(final)
        if validation_error:
            return {
                "action": "NO_TRADE",
                "reason": validation_error,
                "signal_type": "UNIFIED",
                "htf_direction": master_direction,
                "layers": final["layers"],
            }
        if _should_block_duplicate(entry, final["action"]):
            return {
                "action": "NO_TRADE",
                "reason": "duplicate blocked",
                "signal_type": "UNIFIED",
                "htf_direction": master_direction,
                "layers": final["layers"],
            }
        _record_signal(entry, final["action"])
    return final


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """Unified entry point combining human layer + scalp + ultra stacks."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    ict_layer = run_ict_layer(df_5m, df_15m, df_1h, df_4h)
    micro_layer = micro_scalp_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    scalp_layer = run_scalp_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    ultra_layer = run_ultra_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    v3_layer = run_ultra_v3_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
    return consolidate_signals(human_layer, ict_layer, micro_layer, scalp_layer, ultra_layer, v3_layer)


def check_ultra_entry(df_5m, df_15m, df_1h, df_4h):
    """Compatibility wrapper for legacy callers."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    return run_ultra_layer(df_5m, df_15m, df_1h, df_4h, human_layer)


def check_ultra_v3(df_5m, df_15m, df_1h, df_4h):
    """Compatibility wrapper for legacy callers."""
    human_layer = build_human_layer(df_5m, df_15m, df_1h, df_4h)
    return run_ultra_v3_layer(df_5m, df_15m, df_1h, df_4h, human_layer)
