import numpy as np
import pandas as pd


# ---------- Core helpers ----------

def _safe_tail(df: pd.DataFrame, n: int = 400) -> pd.DataFrame:
    return df if len(df) <= n else df.tail(n)


def _get_last(df: pd.DataFrame):
    return df.iloc[-1] if len(df) else None


# ---------- Trend / state ----------

def get_trend_direction(df: pd.DataFrame) -> str:
    """EMA50/200 bias."""
    if len(df) == 0 or "ema50" not in df or "ema200" not in df:
        return "unknown"
    last = _get_last(df)
    if last is None or pd.isna(last.get("ema50")) or pd.isna(last.get("ema200")):
        return "unknown"
    if last["close"] > last["ema200"] and last["ema50"] > last["ema200"]:
        return "bullish"
    if last["close"] < last["ema200"] and last["ema50"] < last["ema200"]:
        return "bearish"
    return "neutral"


def _adx_state(adx_val: float) -> str:
    if np.isnan(adx_val):
        return "unknown"
    if adx_val < 20:
        return "ranging (<20)"
    if 20 <= adx_val < 25:
        return "trending (20-25)"
    return "strong (>25)"


# ---------- Market structure ----------

def _detect_swings(df: pd.DataFrame):
    """3-candle swing highs/lows (non-repainting)."""
    swings = []
    if len(df) < 3:
        return swings
    highs = (df["high"].shift(1) > df["high"].shift(2)) & (df["high"].shift(1) > df["high"])
    lows = (df["low"].shift(1) < df["low"].shift(2)) & (df["low"].shift(1) < df["low"])
    for i in range(2, len(df)):
        if highs.iloc[i]:
            idx = df.index[i - 1]
            swings.append({"type": "high", "index": idx, "price": float(df["high"].iloc[i - 1])})
        if lows.iloc[i]:
            idx = df.index[i - 1]
            swings.append({"type": "low", "index": idx, "price": float(df["low"].iloc[i - 1])})
    return swings


def get_market_structure(df: pd.DataFrame):
    """Return structure labels HH/HL/LH/LL and last swings."""
    swings = _detect_swings(df)
    last_high = prev_high = None
    last_low = prev_low = None
    for s in swings:
        if s["type"] == "high":
            prev_high = last_high
            last_high = s
        else:
            prev_low = last_low
            last_low = s

    high_label = None
    low_label = None
    if last_high and prev_high:
        high_label = "HH" if last_high["price"] > prev_high["price"] else "LH"
    if last_low and prev_low:
        low_label = "HL" if last_low["price"] > prev_low["price"] else "LL"

    structure = "range"
    if high_label == "HH" and low_label in ("HL", "HH"):
        structure = "bullish"
    elif high_label == "LH" and low_label in ("LL", "LH"):
        structure = "bearish"

    return {
        "structure": structure,
        "high_label": high_label,
        "low_label": low_label,
        "last_high": last_high,
        "last_low": last_low,
        "swings": swings,
    }


# ---------- BOS / CHOCH ----------

def detect_bos_choch(df: pd.DataFrame, swings=None, max_events: int = 5):
    """Detect BOS/CHOCH from swing breaches without lookahead."""
    events = []
    if df is None or len(df) < 3:
        return events
    swings = swings or _detect_swings(df)
    closes = df["close"]
    last_dir = None
    for s in swings[-50:]:
        try:
            loc = df.index.get_loc(s["index"])
        except KeyError:
            continue
        future = closes.iloc[loc + 1 :]
        if s["type"] == "high":
            breach = future[future > s["price"]]
            direction = "bullish"
        else:
            breach = future[future < s["price"]]
            direction = "bearish"
        if breach.empty:
            continue
        ev_time = breach.index[0]
        ev_type = "CHOCH" if last_dir and last_dir != direction else "BOS"
        last_dir = direction
        events.append({"type": ev_type, "direction": direction, "price": float(s["price"]), "time": str(ev_time)})
        if len(events) >= max_events:
            break
    return events


# ---------- Liquidity ----------

def find_liquidity_zones(df: pd.DataFrame, swings=None, limit: int = 3):
    """Mark recent highs/lows as liquidity + equal highs/lows."""
    swings = swings or _detect_swings(df)
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    highs = sorted(highs, key=lambda x: x["index"], reverse=True)[:limit]
    lows = sorted(lows, key=lambda x: x["index"], reverse=True)[:limit]
    zones = []
    for h in highs:
        zones.append({"type": "above_highs", "price": h["price"], "time": str(h["index"])})
    for l in lows:
        zones.append({"type": "below_lows", "price": l["price"], "time": str(l["index"])})

    # Equal highs/lows detection (simple tolerance)
    def _equal_pairs(points):
        out = []
        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i + 1]
            if abs(p1["price"] - p2["price"]) <= max(0.01, 0.0005 * p1["price"]):
                out.append({"type": "equal_highs" if p1["type"] == "high" else "equal_lows", "prices": [p1["price"], p2["price"]], "times": [str(p1["index"]), str(p2["index"])]})
        return out

    zones.extend(_equal_pairs(highs))
    zones.extend(_equal_pairs(lows))
    return zones


# ---------- Order blocks ----------

def find_order_blocks(df: pd.DataFrame, bos_events, lookback: int = 5):
    if df is None or len(df) == 0:
        return []
    obs = []
    for ev in bos_events:
        try:
            loc = df.index.get_loc(pd.to_datetime(ev["time"]))
        except Exception:
            continue
        window = df.iloc[max(0, loc - lookback) : loc]
        if window.empty:
            continue
        if ev["direction"] == "bullish":
            bearish = window[window["close"] < window["open"]]
            if len(bearish) == 0:
                continue
            candle = bearish.iloc[-1]
            obs.append({"type": "bullish", "open": float(candle["open"]), "close": float(candle["close"]), "high": float(candle["high"]), "low": float(candle["low"]), "time": str(candle.name)})
        else:
            bullish = window[window["close"] > window["open"]]
            if len(bullish) == 0:
                continue
            candle = bullish.iloc[-1]
            obs.append({"type": "bearish", "open": float(candle["open"]), "close": float(candle["close"]), "high": float(candle["high"]), "low": float(candle["low"]), "time": str(candle.name)})
    return obs


# ---------- Fair Value Gaps ----------

def find_fvg(df: pd.DataFrame, max_results: int = 5):
    if df is None or len(df) < 3:
        return []
    highs = df["high"]
    lows = df["low"]
    results = []
    for i in range(2, len(df)):
        if lows.iloc[i] > highs.iloc[i - 2]:
            results.append({"type": "bullish", "start": float(highs.iloc[i - 2]), "end": float(lows.iloc[i]), "time": str(df.index[i])})
        if highs.iloc[i] < lows.iloc[i - 2]:
            results.append({"type": "bearish", "start": float(highs.iloc[i]), "end": float(lows.iloc[i - 2]), "time": str(df.index[i])})
        if len(results) >= max_results:
            break
    return results


# ---------- Timeframe analysis ----------

def analyze_timeframe(df: pd.DataFrame, timeframe_name: str):
    """Compute structure, BOS/CHOCH, liquidity, OB, FVG, trend, ADX state."""
    if df is None or len(df) < 5:
        return {
            "timeframe": timeframe_name,
            "trend": "unknown",
            "market_structure": "insufficient",
            "bos_choch": [],
            "liquidity": [],
            "order_blocks": [],
            "fvg": [],
            "adx": "unknown",
            "atr": None,
        }

    tail_df = _safe_tail(df)
    structure = get_market_structure(tail_df)
    bos = detect_bos_choch(tail_df, structure["swings"])
    liquidity = find_liquidity_zones(tail_df, structure["swings"])
    order_blocks = find_order_blocks(tail_df, bos)
    fvg = find_fvg(tail_df)
    trend = get_trend_direction(tail_df)
    last = _get_last(tail_df)
    adx_val = float(last["adx"]) if last is not None and "adx" in last else float("nan")
    atr_val = float(last["atr"]) if last is not None and "atr" in last else None

    return {
        "timeframe": timeframe_name,
        "trend": trend,
        "market_structure": structure["structure"],
        "swings": {"last_high": structure["last_high"], "last_low": structure["last_low"], "high_label": structure["high_label"], "low_label": structure["low_label"]},
        "bos_choch": bos,
        "liquidity": liquidity,
        "order_blocks": order_blocks,
        "fvg": fvg,
        "adx": _adx_state(adx_val),
        "atr": atr_val,
    }


# ---------- MTF aggregation ----------

def _recommended_sl_tp(bias: str, tf_5m: dict, atr_mult: float = 1.5):
    sl = tp = "unavailable"
    last_high = tf_5m.get("swings", {}).get("last_high")
    last_low = tf_5m.get("swings", {}).get("last_low")
    atr_val = tf_5m.get("atr") or 0.0
    if bias == "bullish" and last_low:
        sl = last_low["price"] - atr_mult * atr_val if atr_val else last_low["price"]
    if bias == "bearish" and last_high:
        sl = last_high["price"] + atr_mult * atr_val if atr_val else last_high["price"]
    # TP: aim for next liquidity in direction of trade
    tp_candidates = tf_5m.get("liquidity", [])
    if bias == "bullish":
        tops = [z for z in tp_candidates if "high" in z.get("type", "")]
        if tops:
            tp = tops[0]["price"]
    elif bias == "bearish":
        lows = [z for z in tp_candidates if "low" in z.get("type", "")]
        if lows:
            tp = lows[0]["price"]
    return sl, tp


def analyze_mtf(dfs: dict):
    """
    Run full MTF analysis across 4H, 1H, 15m, 5m.
    dfs keys expected: \"4H\", \"1H\", \"15m\", \"5m\".
    """
    results = {}
    for name, df in dfs.items():
        results[name] = analyze_timeframe(df, name)

    tf4 = results.get("4H")
    tf1 = results.get("1H")
    tf15 = results.get("15m")
    tf5 = results.get("5m")

    bias = None
    confluence = []
    if tf4 and tf1 and tf4["trend"] in ("bullish", "bearish") and tf4["trend"] == tf1["trend"]:
        bias = tf4["trend"]
        confluence.append(f"4H trend {tf4['trend']}")
        confluence.append(f"1H trend {tf1['trend']}")

    entry_ok = False
    reason = "Waiting for confluence"
    if bias and tf15 and tf15["market_structure"] == bias:
        confluence.append(f"15m structure {tf15['market_structure']}")
        if tf15["order_blocks"] or tf15["fvg"]:
            confluence.append("15m zone (OB/FVG)")
        if tf5 and tf5["bos_choch"]:
            last_dir = tf5["bos_choch"][-1]["direction"]
            confluence.append(f"5m BOS/CHOCH {last_dir}")
            if last_dir == bias:
                entry_ok = True
                reason = "Bias aligned across HTF/ITF with 5m trigger"

    final_type = bias if entry_ok else "neutral"
    sl, tp = _recommended_sl_tp(bias, tf5 or {})

    final_signal = {
        "type": final_type if final_type else "neutral",
        "reason": reason,
        "confluence": confluence,
        "recommended_sl": sl,
        "recommended_tp": tp,
    }

    return {**results, "final_signal": final_signal}
