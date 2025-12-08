def _trend(row):
    """
    Trend with optional structure support.
    If a structure label is present, use it; otherwise fall back to EMA50/200.
    """
    struct = row.get("market_structure") if hasattr(row, "get") else None
    if struct in ("bullish", "bearish"):
        return struct
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


def calculate_sl_tp(
    entry,
    atr,
    direction,
    sl_atr_mult=1.2,
    tp_atr_mult=1.0,
    max_dist=12.0,
    sl_atr=None,
    sl_max_dist=25.0,
    tp_atr=None,
    tp_max_dist=12.0,
):
    """
    SL = structure ref +/- ATR*1.2 (prefers 1H ATR), capped at $25.
    TP = entry +/- ATR*1.0 (prefers 5m ATR), capped at $12.
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


def _adx_tier(val):
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


def _confidence_emoji(conf):
    return "⭐️⭐️⭐️" if conf == "HIGH" else ("⭐️⭐️" if conf == "MEDIUM" else "⭐️")


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


def _liquidity_sweep(df):
    """Detect micro liquidity sweep on 5m using recent swings."""
    swings = _local_swings(df, lookback=12, window=2)
    highs, lows = swings.get("highs", []), swings.get("lows", [])
    if (not highs and not lows) or len(df) < 3:
        return {"type": None, "level": None}
    last = df.iloc[-1]
    close = float(last.get("close", 0))
    sweep = {"type": None, "level": None}
    if len(highs) >= 1:
        ref = highs[-1]["price"]
        if float(df["high"].iloc[-1]) > ref * 1.001 and close < ref:
            sweep = {"type": "above", "level": ref}
    if sweep["type"] is None and len(lows) >= 1:
        ref = lows[-1]["price"]
        if float(df["low"].iloc[-1]) < ref * 0.999 and close > ref:
            sweep = {"type": "below", "level": ref}
    return sweep


def _micro_bos(df):
    """Detect micro BOS/CHOCH (close beyond prior swing)."""
    swings = _local_swings(df, lookback=20, window=2)
    highs, lows = swings.get("highs", []), swings.get("lows", [])
    if len(df) < 4:
        return {"valid": False, "direction": None, "level": None}
    close = float(df["close"].iloc[-1])
    if len(highs) >= 1 and close > highs[-1]["price"]:
        return {"valid": True, "direction": "bullish", "level": highs[-1]["price"]}
    if len(lows) >= 1 and close < lows[-1]["price"]:
        return {"valid": True, "direction": "bearish", "level": lows[-1]["price"]}
    return {"valid": False, "direction": None, "level": None}


def _channel_bounds(df, lookback=30):
    """Approximate channel bounds using recent extrema."""
    if len(df) == 0:
        return None
    tail = df.tail(lookback)
    upper = float(tail["high"].max())
    lower = float(tail["low"].min())
    mid = (upper + lower) / 2
    return {"upper": upper, "lower": lower, "mid": mid}


def _human_struct_scalp(df_5m, df_15m, df_1h, adx5=None, adx15=None):
    """
    Human-like micro-structure scalp layer.
    Returns action if a structural scalp is available; otherwise NO_TRADE.
    """
    if len(df_5m) < 8 or len(df_15m) < 4:
        return {"action": "NO_TRADE"}

    last5 = df_5m.iloc[-1]
    price = float(last5.get("close", 0))
    atr5 = float(last5.get("atr", price * 0.01))
    atr5 = max(atr5, price * 0.003)

    swings_5 = _local_swings(df_5m, lookback=25, window=2)
    swings_15 = _local_swings(df_15m, lookback=25, window=2)
    bias_5 = _structure_bias(swings_5)
    bias_15 = _structure_bias(swings_15)
    bias = bias_5

    channel = _channel_bounds(df_5m)
    sweep = _liquidity_sweep(df_5m)
    micro_bos = _micro_bos(df_5m)
    bull_wick, bear_wick = _wick_rejection(last5)

    support_candidates = [s["price"] for s in swings_5.get("lows", [])]
    resistance_candidates = [h["price"] for h in swings_5.get("highs", [])]
    support_level = max(support_candidates) if support_candidates else None
    resistance_level = min(resistance_candidates) if resistance_candidates else None
    support_touches = _touch_strength(support_level, df_5m) if support_level else 0
    resistance_touches = _touch_strength(resistance_level, df_5m) if resistance_level else 0

    near_support = support_level and abs(price - support_level) / price < 0.0035 and support_touches >= 2
    near_resistance = resistance_level and abs(price - resistance_level) / price < 0.0035 and resistance_touches >= 2

    channel_support = channel and abs(price - channel["lower"]) / price < 0.007
    channel_resistance = channel and abs(price - channel["upper"]) / price < 0.007

    direction = None
    reasoning = []
    if sweep["type"] == "below":
        direction = "BUY"
        reasoning.append(f"Liquidity sweep below {sweep['level']:.2f}")
    elif sweep["type"] == "above":
        direction = "SELL"
        reasoning.append(f"Liquidity sweep above {sweep['level']:.2f}")

    if direction is None and bias in ("bullish", "bearish"):
        direction = "BUY" if bias == "bullish" else "SELL"
        reasoning.append(f"Micro structure {bias}")

    if direction is None and channel:
        if channel_support:
            direction = "BUY"
            reasoning.append("Channel support tap")
        elif channel_resistance:
            direction = "SELL"
            reasoning.append("Channel resistance tap")

    if direction is None:
        return {"action": "NO_TRADE"}

    if direction == "BUY" and bull_wick:
        reasoning.append("Bullish rejection wick")
    if direction == "SELL" and bear_wick:
        reasoning.append("Bearish rejection wick")
    if micro_bos["valid"]:
        reasoning.append(f"Micro BOS {micro_bos['direction']}")

    valid_entry = False
    anchor_level = None
    if direction == "BUY":
        if near_support:
            valid_entry = True
            anchor_level = support_level
            reasoning.append(f"Support touch ({support_touches} touches)")
        if channel_support:
            valid_entry = True
            anchor_level = anchor_level or channel["lower"]
            reasoning.append("Channel support confluence")
        if sweep["type"] == "below":
            valid_entry = True
            anchor_level = anchor_level or sweep["level"]
        if micro_bos["valid"] and micro_bos["direction"] == "bullish":
            valid_entry = True
    else:
        if near_resistance:
            valid_entry = True
            anchor_level = resistance_level
            reasoning.append(f"Resistance touch ({resistance_touches} touches)")
        if channel_resistance:
            valid_entry = True
            anchor_level = anchor_level or channel["upper"]
            reasoning.append("Channel resistance confluence")
        if sweep["type"] == "above":
            valid_entry = True
            anchor_level = anchor_level or sweep["level"]
        if micro_bos["valid"] and micro_bos["direction"] == "bearish":
            valid_entry = True

    if not valid_entry and not micro_bos["valid"]:
        return {"action": "NO_TRADE"}

    buffer = max(atr5 * 0.4, price * 0.0015)
    if direction == "BUY":
        sl = (anchor_level or price) - buffer
        tp1 = max([h["price"] for h in swings_5.get("highs", [])], default=price + atr5)
        tp2 = max(channel["mid"] if channel else tp1, tp1)
        tp3 = channel["upper"] if channel else tp2 + atr5
    else:
        sl = (anchor_level or price) + buffer
        tp1 = min([l["price"] for l in swings_5.get("lows", [])], default=price - atr5)
        tp2 = min(channel["mid"] if channel else tp1, tp1)
        tp3 = channel["lower"] if channel else tp2 - atr5

    confidence = 30
    if bias != "neutral":
        confidence += 15
    if sweep["type"]:
        confidence += 15
    if (channel_support and direction == "BUY") or (channel_resistance and direction == "SELL"):
        confidence += 15
    if (bull_wick and direction == "BUY") or (bear_wick and direction == "SELL"):
        confidence += 10
    if micro_bos["valid"]:
        confidence += 10
    if adx5 is not None and adx5 >= 25:
        confidence += 5
    if adx15 is not None and adx15 >= 25:
        confidence += 5
    confidence = float(min(100, max(0, confidence)))

    visual_story = "; ".join(reasoning) if reasoning else "Human structural scalp setup"
    return {
        "action": direction,
        "entry": round(price, 2),
        "sl": round(sl, 2),
        "tp": round(tp1, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2),
        "confidence": confidence,
        "reasoning": reasoning if reasoning else ["Human structural scalp trigger"],
        "visual_story": visual_story,
        "trigger": "HUMAN_STRUCT_SCALP",
        "signal_type": "SCALP",
    }

def check_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Scalping-focused multi-timeframe logic with strict ADX gating and cleaned momentum checks.
    """
    timeframe = "5m"

    def _trend_safe(row):
        try:
            t = _trend(row)
            if t not in ("bullish", "bearish", "neutral"):
                raise ValueError()
            return t
        except Exception:
            try:
                if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
                    return "bullish"
                if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
                    return "bearish"
            except Exception:
                return "neutral"
            return "neutral"

    def _with_meta(payload, trend_val):
        payload["timeframe"] = timeframe
        payload["trend"] = trend_val
        return payload

    def _is_major_demand(row):
        keys = ["major_demand", "major_demand_zone", "demand_zone_major", "in_major_demand", "major_demand_flag"]
        if any(row.get(k) for k in keys if hasattr(row, "get")):
            return True
        strength = 0
        for k in ["demand_zone_strength", "demand_strength", "demand_score"]:
            try:
                strength = max(strength, float(row.get(k, 0)))
            except Exception:
                continue
        in_zone = bool(row.get("in_demand_zone") if hasattr(row, "get") else False)
        return in_zone and strength >= 4

    def _is_major_supply(row):
        keys = ["major_supply", "major_supply_zone", "supply_zone_major", "in_major_supply", "major_supply_flag"]
        if any(row.get(k) for k in keys if hasattr(row, "get")):
            return True
        strength = 0
        for k in ["supply_zone_strength", "supply_strength", "supply_score"]:
            try:
                strength = max(strength, float(row.get(k, 0)))
            except Exception:
                continue
        in_zone = bool(row.get("in_supply_zone") if hasattr(row, "get") else False)
        return in_zone and strength >= 4

    min_required = 8
    if len(df_5m) < min_required:
        return _with_meta({
            "action": "NO_TRADE",
            "reason": f"Not enough candles (need >= {min_required}) in one of the timeframes",
            "market_status": "Data too short for safe scalping check",
            "signal_type": "SCALP",
        }, "neutral")
    for name, df in [("15m", df_15m), ("1h", df_1h), ("4h", df_4h)]:
        if len(df) < 1:
            return _with_meta({
                "action": "NO_TRADE",
                "reason": f"Not enough {name} candles (need >=1)",
                "market_status": "Data too short for safe scalping check",
                "signal_type": "SCALP",
            }, "neutral")

    last5 = df_5m.iloc[-1]
    prev5 = df_5m.iloc[-2]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]

    adx5 = float(last5.get("adx", 0))
    adx15 = float(last15.get("adx", 0))
    adx1h = float(last1h.get("adx", 0))
    adx4h = float(last4h.get("adx", 0))

    trend_1h = _trend_safe(last1h)
    trend_4h = _trend_safe(last4h)
    mid_trend = _trend_safe(last15)
    sl_atr = float(last1h.get("atr", last5.get("atr", 0)))
    tp_atr = float(last5.get("atr", sl_atr if sl_atr else 0))
    if sl_atr <= 0:
        sl_atr = tp_atr

    status_msg = (
        f"Trend 4H/1H/15m: {trend_4h}/{trend_1h}/{mid_trend} | "
        f"ADX5m={adx5:.1f} ADX15m={adx15:.1f}"
    )

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(adx5, adx15, adx1h, adx4h)

    # Human-like structural scalp layer (runs before strict SCALP rules)
    human_layer = _human_struct_scalp(df_5m, df_15m, df_1h, adx5=adx5, adx15=adx15)
    if human_layer.get("action") in ("BUY", "SELL"):
        return _with_meta(human_layer, trend_1h)

    if adx_conf == "blocked":
        return _with_meta({
            "action": "NO_TRADE",
            "reason": "ADX below 20 blocks entry",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }, trend_1h)

    if trend_1h != trend_4h or trend_1h == "neutral":
        return _with_meta({
            "action": "NO_TRADE",
            "reason": f"HTF mismatch: 4H={trend_4h}, 1H={trend_1h}",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }, trend_1h)

    if mid_trend not in (trend_1h, "neutral"):
        return _with_meta({
            "action": "NO_TRADE",
            "reason": f"15m divergence: 15m={mid_trend} vs HTF={trend_1h}",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }, trend_1h)

    main_trend = trend_1h
    price = last5["close"]
    ema50 = last5["ema50"]
    ema200 = last5["ema200"]
    over_extension = abs(price - ema50) / ema50

    def _calc_sl_tp(direction):
        return calculate_sl_tp(
            price,
            tp_atr,
            direction,
            sl_atr_mult=1.2,
            tp_atr_mult=1.0,
            sl_atr=sl_atr,
            sl_max_dist=25.0,
            tp_max_dist=12.0,
        )
    
    def _guard_levels(direction, sl, tp):
        tp_dist = abs(tp - price)
        min_tp_move = max(tp_dist, tp_atr * 0.5)
        min_sl_move = max(abs(sl - price), sl_atr * 0.5 if sl_atr else tp_atr * 0.5)
        if direction == "BUY":
            if tp <= price:
                tp = price + min_tp_move
            if sl >= price:
                sl = price - min_sl_move
        else:
            if tp >= price:
                tp = price - min_tp_move
            if sl <= price:
                sl = price + min_sl_move
        return round(sl, 2), round(tp, 2)

    rsi_cross = detect_rsi_cross(prev5.get("rsi"), last5.get("rsi"))
    macd_up = strong_macd_momentum(df_5m, "bullish")
    macd_down = strong_macd_momentum(df_5m, "bearish")
    emoji = _confidence_emoji(adx_conf)

    demand_block = _is_major_demand(last5) or _is_major_demand(last15) or _is_major_demand(last1h) or _is_major_demand(last4h)
    supply_block = _is_major_supply(last5) or _is_major_supply(last15) or _is_major_supply(last1h) or _is_major_supply(last4h)

    if main_trend == "bullish":
        buy_ok = (
            price > ema50 > ema200
            and rsi_cross == "bullish"
            and macd_up
            and last5["stoch_k"] >= last5["stoch_d"]
            and over_extension < 0.01
        )
        if buy_ok and not supply_block:
            sl, tp = _calc_sl_tp("BUY")
            sl, tp = _guard_levels("BUY", sl, tp)
            return _with_meta({
                "action": "BUY",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "market_status": status_msg,
                "signal_type": "SCALP",
            }, main_trend)

    if main_trend == "bearish":
        sell_ok = (
            price < ema50 < ema200
            and rsi_cross == "bearish"
            and macd_down
            and last5["stoch_k"] <= last5["stoch_d"]
            and over_extension < 0.01
        )
        if sell_ok and not demand_block:
            sl, tp = _calc_sl_tp("SELL")
            sl, tp = _guard_levels("SELL", sl, tp)
            return _with_meta({
                "action": "SELL",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "market_status": status_msg,
                "signal_type": "SCALP",
            }, main_trend)

    block_reason = None
    if main_trend == "bearish" and demand_block:
        block_reason = "Blocked by major demand zone"
    if main_trend == "bullish" and supply_block:
        block_reason = "Blocked by major supply zone"
    return _with_meta({
        "action": "NO_TRADE",
        "reason": block_reason or f"Waiting for aligned momentum. Trend={main_trend}.",
        "market_status": status_msg,
        "signal_type": "SCALP",
    }, main_trend)


def check_golden_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Very strict confluence filter for high-confidence scalps.
    """
    if min(len(df_5m), len(df_15m), len(df_1h), len(df_4h)) < 10:
        return {
            "action": "NO_TRADE",
            "reason": "Not enough candles for golden setup (need >=10 each timeframe)",
            "signal_type": "GOLDEN",
        }

    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]

    trend_5 = _trend(last5)
    trend_15 = _trend(last15)
    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(
        float(last5.get("adx", 0)),
        float(last15.get("adx", 0)),
        float(last1h.get("adx", 0)),
        float(last4h.get("adx", 0)),
    )
    if adx_conf == "blocked":
        return {
            "action": "NO_TRADE",
            "reason": "ADX below 20 blocks entry",
            "signal_type": "GOLDEN",
        }

    status_msg = (
        f"Trend 4H/1H/15m/5m: {trend_4h}/{trend_1h}/{trend_15}/{trend_5} | "
        f"ADX5m={float(last5.get('adx',0)):.1f}, ADX15m={float(last15.get('adx',0)):.1f}"
    )

    if trend_4h != trend_1h or trend_1h != trend_15 or trend_15 != trend_5:
        return {
            "action": "NO_TRADE",
            "reason": "Golden: trend mismatch across timeframes",
            "market_status": status_msg,
            "signal_type": "GOLDEN",
        }

    over_ext = abs(last5["close"] - last5["ema50"]) / last5["ema50"]
    rsi_cross = detect_rsi_cross(df_5m.iloc[-2].get("rsi"), last5.get("rsi"))
    macd_up = strong_macd_momentum(df_5m, "bullish")
    macd_down = strong_macd_momentum(df_5m, "bearish")
    emoji = _confidence_emoji(adx_conf)

    if trend_5 == "bullish":
        conds = [
            rsi_cross == "bullish",
            macd_up,
            last5["stoch_k"] > last5["stoch_d"],
            over_ext < 0.005,
            last5["close"] >= last5["don_high"] * 0.999,
        ]
        if all(conds):
            sl, tp = calculate_sl_tp(
                last5["close"],
                float(last5.get("atr", 0)),
                "BUY",
                sl_atr_mult=1.2,
                tp_atr_mult=1.0,
                sl_atr=float(last1h.get("atr", last5.get("atr", 0))),
                sl_max_dist=25.0,
                tp_max_dist=12.0,
            )
            return {
                "action": "BUY",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "signal_type": "GOLDEN",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
            }

    if trend_5 == "bearish":
        conds = [
            rsi_cross == "bearish",
            macd_down,
            last5["stoch_k"] < last5["stoch_d"],
            over_ext < 0.005,
            last5["close"] <= last5["don_low"],
        ]
        if all(conds):
            sl, tp = calculate_sl_tp(
                last5["close"],
                float(last5.get("atr", 0)),
                "SELL",
                sl_atr_mult=1.2,
                tp_atr_mult=1.0,
                sl_atr=float(last1h.get("atr", last5.get("atr", 0))),
                sl_max_dist=25.0,
                tp_max_dist=12.0,
            )
            return {
                "action": "SELL",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "signal_type": "GOLDEN",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
            }

    return {
        "action": "NO_TRADE",
        "reason": "Golden: conditions not met",
        "market_status": status_msg,
        "signal_type": "GOLDEN",
    }


# ---------------------------------------------------------------------------
# ULTRA SIGNALS (isolated SMC-based system)
# ---------------------------------------------------------------------------


def check_ultra_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Ultra SMC scalping engine (isolated). Does not modify other strategies.
    """
    # Basic safety
    if min(len(df_5m), len(df_15m), len(df_1h), len(df_4h)) < 8:
        return {
            "action": "NO_TRADE",
            "reason": "Not enough candles for ULTRA",
            "signal_type": "ULTRA",
            "market_status": "Insufficient data",
        }

    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    price = last5["close"]
    adx5 = float(last5.get("adx", 0))
    adx15 = float(last15.get("adx", 0))

    # Trends (HTF alignment)
    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)
    htf_bull = trend_1h == "bullish" and trend_4h == "bullish"
    htf_bear = trend_1h == "bearish" and trend_4h == "bearish"

    # Liquidity sweep detection (last 3-7 candles)
    tail = df_5m.tail(7)
    prev_range = tail.iloc[:-1] if len(tail) > 1 else tail
    recent_high = prev_range["high"].max()
    recent_low = prev_range["low"].min()

    sweep = {"valid": False, "direction": None, "level": None, "strength": None}
    wick_ratio = None
    if len(tail) >= 3:
        candle = tail.iloc[-1]
        body_mid = (candle["open"] + candle["close"]) / 2
        # BUY sweep: take out lows then close back above
        if candle["low"] < recent_low and candle["close"] > recent_low and htf_bull:
            sweep["valid"] = True
            sweep["direction"] = "BUY"
            sweep["level"] = float(recent_low)
            sweep["strength"] = float(recent_low - candle["low"])
            wick_ratio = (candle["low"] - min(candle["open"], candle["close"])) if body_mid else 0
        # SELL sweep: take out highs then close back below
        if candle["high"] > recent_high and candle["close"] < recent_high and htf_bear:
            sweep["valid"] = True
            sweep["direction"] = "SELL"
            sweep["level"] = float(recent_high)
            sweep["strength"] = float(candle["high"] - recent_high)
            wick_ratio = (max(candle["open"], candle["close"]) - candle["high"]) if body_mid else 0

    # Micro BOS (last 3-6 candles)
    micro_bos = {"valid": False, "direction": None, "level": None}
    if sweep["valid"]:
        window = df_5m.tail(6).iloc[:-1] if len(df_5m) >= 6 else df_5m.iloc[:-1]
        if sweep["direction"] == "BUY":
            minor_high = window["high"].max() if len(window) else recent_high
            if price > minor_high:
                micro_bos = {"valid": True, "direction": "BUY", "level": float(minor_high)}
        if sweep["direction"] == "SELL":
            minor_low = window["low"].min() if len(window) else recent_low
            if price < minor_low:
                micro_bos = {"valid": True, "direction": "SELL", "level": float(minor_low)}

    # Breaker block (last opposite candle before sweep)
    breaker = {"valid": False, "direction": None}
    if sweep["valid"]:
        sweep_idx = df_5m.index[-1]
        before_sweep = df_5m.iloc[:-1]
        if sweep["direction"] == "BUY":
            opp = before_sweep[before_sweep["close"] < before_sweep["open"]]
            if not opp.empty:
                last_bear = opp.iloc[-1]
                if price > last_bear["high"]:
                    breaker = {"valid": True, "direction": "BUY"}
        if sweep["direction"] == "SELL":
            opp = before_sweep[before_sweep["close"] > before_sweep["open"]]
            if not opp.empty:
                last_bull = opp.iloc[-1]
                if price < last_bull["low"]:
                    breaker = {"valid": True, "direction": "SELL"}

    # Confluence scoring
    score = 0
    if sweep["valid"]:
        score += 1
    if micro_bos["valid"]:
        score += 1
    if breaker["valid"]:
        score += 1
    if adx5 >= 20:
        score += 1

    if score < 2:
        return {
            "action": "NO_TRADE",
            "reason": "Insufficient ULTRA confluence",
            "signal_type": "ULTRA",
            "market_status": f"score={score}",
            "analysis": {
                "sweep": sweep,
                "micro_bos": micro_bos,
                "breaker": breaker,
                "confluence_score": score,
            },
        }

    confidence = "LOW"
    if score == 3:
        confidence = "MEDIUM"
    if score == 4:
        confidence = "HIGH"
    confidence_emoji = "⭐⭐⭐" if confidence == "HIGH" else ("⭐⭐" if confidence == "MEDIUM" else "⭐")

    # ADX and direction gating
    if sweep["direction"] == "BUY" and not htf_bull:
        return {"action": "NO_TRADE", "reason": "HTF trend not bullish", "signal_type": "ULTRA"}
    if sweep["direction"] == "SELL" and not htf_bear:
        return {"action": "NO_TRADE", "reason": "HTF trend not bearish", "signal_type": "ULTRA"}
    if adx5 < 20:
        return {"action": "NO_TRADE", "reason": "ADX5m < 20", "signal_type": "ULTRA"}

    # SL/TP
    fallback_sl = min(float(last1h.get("atr", 0)) * 1.2 if last1h.get("atr", 0) else 0, 25.0)
    sweep_level = sweep.get("level", price)
    if sweep["direction"] == "BUY":
        sl = sweep_level if sweep_level else price - fallback_sl
        sl = sl if sweep_level else price - fallback_sl
        tp1 = df_5m["high"].tail(20).max()
        tp2 = df_15m["high"].tail(20).max()
        tp3 = max(df_1h["high"].tail(30).max(), df_4h["high"].tail(30).max())
    else:
        sl = sweep_level if sweep_level else price + fallback_sl
        tp1 = df_5m["low"].tail(20).min()
        tp2 = df_15m["low"].tail(20).min()
        tp3 = min(df_1h["low"].tail(30).min(), df_4h["low"].tail(30).min())

    # Fallback SL if sweep not set
    if sweep_level is None:
        sl = price - fallback_sl if sweep["direction"] == "BUY" else price + fallback_sl

    return {
        "action": sweep["direction"] if sweep["valid"] and micro_bos["valid"] and breaker["valid"] else "NO_TRADE",
        "entry": float(price),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "confidence": confidence,
        "confidence_emoji": confidence_emoji,
        "signal_type": "ULTRA",
        "market_status": f"score={score}, adx5={adx5:.1f}, adx15={adx15:.1f}",
        "analysis": {
            "sweep": sweep,
            "micro_bos": micro_bos,
            "breaker": breaker,
            "confluence_score": score,
        },
    }


# ---------------------------------------------------------------------------
# ULTRA V3 (independent advanced scalping engine)
# ---------------------------------------------------------------------------


def check_ultra_v3(df_5m, df_15m, df_1h, df_4h):
    """
    Advanced SMC-based scalping engine (independent from other strategies).
    """
    if min(len(df_5m), len(df_15m), len(df_1h), len(df_4h)) < 10:
        return {
            "action": "NO_TRADE",
            "reason": "Not enough candles for ULTRA_V3",
            "signal_type": "ULTRA_V3",
            "market_status": "Insufficient data",
        }

    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    price = float(last5["close"])

    # Helper: swing detection (simple 3-candle pattern)
    def swings(df):
        highs = (df["high"].shift(1) > df["high"].shift(2)) & (df["high"].shift(1) > df["high"])
        lows = (df["low"].shift(1) < df["low"].shift(2)) & (df["low"].shift(1) < df["low"])
        sh = [{"type": "high", "idx": df.index[i - 1], "price": float(df["high"].iloc[i - 1])} for i in range(2, len(df)) if highs.iloc[i]]
        sl = [{"type": "low", "idx": df.index[i - 1], "price": float(df["low"].iloc[i - 1])} for i in range(2, len(df)) if lows.iloc[i]]
        return sh, sl

    def liquidity_map(df):
        sh, sl = swings(df)
        eq_tolerance = 0.0005
        def equal_clusters(points):
            pts = sorted(points, key=lambda x: x["price"])
            clusters = []
            for p in pts:
                if not clusters or abs(clusters[-1][-1]["price"] - p["price"]) > eq_tolerance * max(1.0, p["price"]):
                    clusters.append([p])
                else:
                    clusters[-1].append(p)
            return [c for c in clusters if len(c) >= 2]
        return {
            "swing_highs": sh,
            "swing_lows": sl,
            "equal_highs": equal_clusters(sh),
            "equal_lows": equal_clusters(sl),
            "liq_above": [p["price"] for p in sh],
            "liq_below": [p["price"] for p in sl],
        }

    liq_5 = liquidity_map(df_5m.tail(300))
    liq_15 = liquidity_map(df_15m.tail(300))
    liq_1h = liquidity_map(df_1h.tail(300))
    liq_4h = liquidity_map(df_4h.tail(400))

    # HTF trend alignment
    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)
    trend_15 = _trend(last15)
    if not ((trend_1h == trend_4h == "bullish" and trend_15 != "bearish") or (trend_1h == trend_4h == "bearish" and trend_15 != "bullish")):
        return {
            "action": "NO_TRADE",
            "reason": "HTF trends not aligned for ULTRA_V3",
            "signal_type": "ULTRA_V3",
            "market_status": f"4H={trend_4h},1H={trend_1h},15m={trend_15}",
        }

    direction = "BUY" if trend_1h == "bullish" else "SELL"

    # Sweep detection (last 3-7 candles)
    tail = df_5m.tail(7)
    sweep = {"valid": False, "level": None, "strength": None, "direction": None}
    if len(tail) >= 3:
        ref_high = tail.iloc[:-1]["high"].max()
        ref_low = tail.iloc[:-1]["low"].min()
        last_candle = tail.iloc[-1]
        if direction == "BUY" and last_candle["low"] < ref_low and last_candle["close"] > ref_low:
            sweep = {"valid": True, "level": float(ref_low), "strength": float(ref_low - last_candle["low"]), "direction": "BUY"}
        if direction == "SELL" and last_candle["high"] > ref_high and last_candle["close"] < ref_high:
            sweep = {"valid": True, "level": float(ref_high), "strength": float(last_candle["high"] - ref_high), "direction": "SELL"}
    if not sweep["valid"]:
        return {
            "action": "NO_TRADE",
            "reason": "No liquidity sweep",
            "signal_type": "ULTRA_V3",
            "market_status": "Sweep missing",
        }

    # Micro CHOCH + BOS
    micro_bos = {"valid": False, "direction": None, "level": None}
    window = df_5m.tail(6).iloc[:-1]
    if direction == "BUY":
        minor_high = window["high"].max() if len(window) else tail["high"].max()
        if price > minor_high:
            micro_bos = {"valid": True, "direction": "BUY", "level": float(minor_high)}
    else:
        minor_low = window["low"].min() if len(window) else tail["low"].min()
        if price < minor_low:
            micro_bos = {"valid": True, "direction": "SELL", "level": float(minor_low)}
    if not micro_bos["valid"]:
        return {
            "action": "NO_TRADE",
            "reason": "CHOCH/BOS missing",
            "signal_type": "ULTRA_V3",
            "market_status": "Micro BOS missing",
        }

    # Refined order block (last opposite candle before sweep)
    ob = {"valid": False, "direction": None, "low": None, "high": None}
    pre_sweep = df_5m.iloc[:-1]
    if direction == "BUY":
        opp = pre_sweep[pre_sweep["close"] < pre_sweep["open"]]
        if not opp.empty:
            last_opp = opp.iloc[-1]
            if price > last_opp["high"]:
                span = last_opp["high"] - last_opp["low"]
                ob_low = last_opp["low"] + span * (1 / 3)
                ob_high = last_opp["high"] - span * (1 / 3)
                ob = {"valid": True, "direction": "BUY", "low": float(ob_low), "high": float(ob_high)}
    else:
        opp = pre_sweep[pre_sweep["close"] > pre_sweep["open"]]
        if not opp.empty:
            last_opp = opp.iloc[-1]
            if price < last_opp["low"]:
                span = last_opp["high"] - last_opp["low"]
                ob_low = last_opp["low"] + span * (1 / 3)
                ob_high = last_opp["high"] - span * (1 / 3)
                ob = {"valid": True, "direction": "SELL", "low": float(ob_low), "high": float(ob_high)}
    if not ob["valid"]:
        return {
            "action": "NO_TRADE",
            "reason": "Refined OB invalid",
            "signal_type": "ULTRA_V3",
            "market_status": "OB invalid",
        }

    # FVG alignment (optional)
    fvg = {"overlap_ob": False}
    if len(df_5m) >= 3:
        highs = df_5m["high"]
        lows = df_5m["low"]
        for i in range(len(df_5m) - 2, len(df_5m)):
            if i < 2:
                continue
            if direction == "BUY" and lows.iloc[i] > highs.iloc[i - 2]:
                if ob["low"] <= lows.iloc[i] <= ob["high"]:
                    fvg["overlap_ob"] = True
            if direction == "SELL" and highs.iloc[i] < lows.iloc[i - 2]:
                if ob["low"] <= highs.iloc[i] <= ob["high"]:
                    fvg["overlap_ob"] = True

    # ADX confidence (not blocker)
    adx_info = {
        "adx5": float(last5.get("adx", 0)),
        "adx15": float(last15.get("adx", 0)),
        "adx1h": float(last1h.get("adx", 0)),
    }
    adx_score = 0
    if adx_info["adx5"] >= 20:
        adx_score += 1
    if adx_info["adx15"] >= 22:
        adx_score += 1
    if adx_info["adx1h"] >= 25:
        adx_score += 1

    # Confluence score 0-6
    score = 0
    if sweep["valid"]:
        score += 1
    if micro_bos["valid"]:
        score += 1
    if ob["valid"]:
        score += 1
    if fvg["overlap_ob"]:
        score += 1
    score += adx_score

    if score < 2:
        return {"action": "NO_TRADE", "reason": "Low score", "signal_type": "ULTRA_V3", "market_status": f"score={score}"}

    if score >= 6:
        confidence = "HIGH"
    elif score >= 4:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    conf_emoji = "⭐⭐⭐" if confidence == "HIGH" else ("⭐⭐" if confidence == "MEDIUM" else "⭐")

    # Entry triggers: allow if price within OB or retesting micro levels
    entry_ok = False
    if direction == "BUY":
        if ob["low"] <= price <= ob["high"]:
            entry_ok = True
        if price >= micro_bos["level"]:
            entry_ok = True
    else:
        if ob["low"] <= price <= ob["high"]:
            entry_ok = True
        if price <= micro_bos["level"]:
            entry_ok = True
    if not entry_ok:
        return {"action": "NO_TRADE", "reason": "No entry trigger", "signal_type": "ULTRA_V3", "market_status": f"score={score}"}

    # SL based on protected liquidity
    buffer = 0.05
    if direction == "BUY":
        sl_raw = min(sweep["level"], ob["low"]) - buffer
    else:
        sl_raw = max(sweep["level"], ob["high"]) + buffer
    fallback_sl = min(float(last1h.get("atr", 0)) * 1.2 if last1h.get("atr", 0) else 0, 25.0)
    sl = sl_raw if sl_raw is not None else (price - fallback_sl if direction == "BUY" else price + fallback_sl)

    # TP levels via nearest liquidity
    if direction == "BUY":
        tp1 = max(liq_5["liq_above"]) if liq_5["liq_above"] else price
        tp2 = max(liq_15["liq_above"]) if liq_15["liq_above"] else tp1
        tp3 = max(liq_1h["liq_above"]) if liq_1h["liq_above"] else tp2
        tp4 = max(liq_4h["liq_above"]) if liq_4h["liq_above"] else tp3
    else:
        tp1 = min(liq_5["liq_below"]) if liq_5["liq_below"] else price
        tp2 = min(liq_15["liq_below"]) if liq_15["liq_below"] else tp1
        tp3 = min(liq_1h["liq_below"]) if liq_1h["liq_below"] else tp2
        tp4 = min(liq_4h["liq_below"]) if liq_4h["liq_below"] else tp3

    result = {
        "action": direction,
        "signal_type": "ULTRA_V3",
        "entry": round(price, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2),
        "tp4": round(tp4, 2),
        "confidence": confidence,
        "confidence_emoji": conf_emoji,
        "market_status": f"HTF {direction} | sweep {sweep['valid']} | BOS {micro_bos['valid']} | score {score}",
        "analysis": {
            "sweep": sweep,
            "micro_bos": micro_bos,
            "order_block": ob,
            "fvg": fvg,
            "adx": adx_info,
            "liquidity": {
                "m5": liq_5,
                "m15": liq_15,
                "h1": liq_1h,
                "h4": liq_4h,
            },
            "score": score,
        },
    }
    return result


