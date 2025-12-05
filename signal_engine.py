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


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Scalping-focused multi-timeframe logic with strict ADX gating and cleaned momentum checks.
    """
    min_required = 8
    if len(df_5m) < min_required:
        return {
            "action": "NO_TRADE",
            "reason": f"Not enough candles (need >= {min_required}) in one of the timeframes",
            "market_status": "Data too short for safe scalping check",
            "signal_type": "SCALP",
        }
    for name, df in [("15m", df_15m), ("1h", df_1h), ("4h", df_4h)]:
        if len(df) < 1:
            return {
                "action": "NO_TRADE",
                "reason": f"Not enough {name} candles (need >=1)",
                "market_status": "Data too short for safe scalping check",
                "signal_type": "SCALP",
            }

    last5 = df_5m.iloc[-1]
    prev5 = df_5m.iloc[-2]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]

    adx5 = float(last5.get("adx", 0))
    adx15 = float(last15.get("adx", 0))
    adx1h = float(last1h.get("adx", 0))
    adx4h = float(last4h.get("adx", 0))

    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)
    mid_trend = _trend(last15)
    sl_atr = float(last1h.get("atr", last5.get("atr", 0)))
    tp_atr = float(last5.get("atr", sl_atr if sl_atr else 0))
    if sl_atr <= 0:
        sl_atr = tp_atr

    status_msg = (
        f"Trend 4H/1H/15m: {trend_4h}/{trend_1h}/{mid_trend} | "
        f"ADX5m={adx5:.1f} ADX15m={adx15:.1f}"
    )

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(adx5, adx15, adx1h, adx4h)
    if adx_conf == "blocked":
        return {
            "action": "NO_TRADE",
            "reason": "ADX below 20 blocks entry",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }

    if trend_1h != trend_4h or trend_1h == "neutral":
        return {
            "action": "NO_TRADE",
            "reason": f"HTF mismatch: 4H={trend_4h}, 1H={trend_1h}",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }

    if mid_trend not in (trend_1h, "neutral"):
        return {
            "action": "NO_TRADE",
            "reason": f"15m divergence: 15m={mid_trend} vs HTF={trend_1h}",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }

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

    rsi_cross = detect_rsi_cross(prev5.get("rsi"), last5.get("rsi"))
    macd_up = strong_macd_momentum(df_5m, "bullish")
    macd_down = strong_macd_momentum(df_5m, "bearish")
    emoji = _confidence_emoji(adx_conf)

    if main_trend == "bullish":
        buy_ok = (
            price > ema50 > ema200
            and rsi_cross == "bullish"
            and macd_up
            and last5["stoch_k"] >= last5["stoch_d"]
            and over_extension < 0.01
        )
        if buy_ok:
            sl, tp = _calc_sl_tp("BUY")
            return {
                "action": "BUY",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }

    if main_trend == "bearish":
        sell_ok = (
            price < ema50 < ema200
            and rsi_cross == "bearish"
            and macd_down
            and last5["stoch_k"] <= last5["stoch_d"]
            and over_extension < 0.01
        )
        if sell_ok:
            sl, tp = _calc_sl_tp("SELL")
            return {
                "action": "SELL",
                "confidence": adx_conf,
                "confidence_emoji": emoji,
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }

    return {
        "action": "NO_TRADE",
        "reason": f"Waiting for aligned momentum. Trend={main_trend}.",
        "market_status": status_msg,
        "signal_type": "SCALP",
    }


def check_supertrend_entry(df_5m, df_15m, df_1h, df_4h):
    """
    SuperTrend-only signals (Simple & Fast) with strict ADX gating and PA confirmations.
    """
    if len(df_5m) == 0 or len(df_15m) == 0 or len(df_1h) == 0 or len(df_4h) == 0:
        return {
            "action": "NO_TRADE",
            "reason": "Not enough candles for SuperTrend check",
            "signal_type": "SUPERTREND",
            "market_status": "Waiting for multi-timeframe data",
        }

    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]
    adx5_val = float(last5.get("adx", 0))
    adx15_val = float(last15.get("adx", 0))
    adx1h_val = float(last1h.get("adx", 0))
    adx4h_val = float(last4h.get("adx", 0))
    atr5 = float(last5.get("atr", 0))
    atr15 = float(last15.get("atr", 0))
    atr1h = float(last1h.get("atr", atr5))

    adx_conf, tier5, tier15, tier1h, tier4h = _compute_adx_conf(
        adx5_val,
        adx15_val,
        adx1h_val,
        adx4h_val,
    )

    if 'supertrend_direction' not in last5.index:
        return {
            "action": "NO_TRADE",
            "reason": "SuperTrend indicator not calculated",
            "signal_type": "SUPERTREND"
        }

    st_5m = last5['supertrend_direction']
    st_15m = last15['supertrend_direction']
    st_1h = last1h['supertrend_direction']
    st_4h = last4h['supertrend_direction']
    strict_align = st_4h == st_1h == st_15m == st_5m
    majority_count = sum([st_4h == st_5m, st_1h == st_5m, st_15m == st_5m, True])  # counts 5m self-align
    majority_mode = (not strict_align) and majority_count >= 3 and (st_4h == st_5m or st_1h == st_5m)

    status_msg = (
        f"SuperTrend: 4H={'UP' if st_4h == 1 else 'DOWN'}, "
        f"1H={'UP' if st_1h == 1 else 'DOWN'}, "
        f"15m={'UP' if st_15m == 1 else 'DOWN'}, "
        f"5m={'UP' if st_5m == 1 else 'DOWN'}"
    )

    price = last5["close"]
    st_val = last5.get("supertrend", price)
    price_on_side = (price > st_val) if st_5m == 1 else (price < st_val)
    # Hard gates: ADX5m/15m, price on correct side, volatility, over-extension
    if adx_conf == "blocked" or adx5_val < 20 or adx15_val < 20 or not price_on_side:
        return {
            "action": "NO_TRADE",
            "reason": f"SuperTrend needs stronger confirmation (adx_conf={adx_conf}, price_on_side={price_on_side})",
            "market_status": status_msg,
            "signal_type": "SUPERTREND",
        }

    # Volatility filter
    if atr5 < atr15 * 0.6:
        return {
            "action": "NO_TRADE",
            "reason": "Volatility too low for fast scalping (ATR5m < 0.6 * ATR15m)",
            "market_status": status_msg,
            "signal_type": "SUPERTREND",
        }

    # Over-extension protection
    over_ext = abs(price - last5["ema50"]) / last5["ema50"]
    ext_limit = 0.01 if adx5_val >= 25 else 0.015
    if over_ext >= ext_limit:
        return {
            "action": "NO_TRADE",
            "reason": f"Over-extended from EMA50 (over_ext={over_ext:.4f})",
            "market_status": status_msg,
            "signal_type": "SUPERTREND",
        }

    # Micro structure (swing) and PA confirmations
    recent_high = df_5m["high"].tail(5).iloc[:-1].max() if len(df_5m) >= 4 else last5["high"]
    recent_low = df_5m["low"].tail(5).iloc[:-1].min() if len(df_5m) >= 4 else last5["low"]
    hist_now = last5["macd"] - last5["macd_signal"]
    hist_prev = df_5m.iloc[-2]["macd"] - df_5m.iloc[-2]["macd_signal"] if len(df_5m) >= 2 else hist_now
    rsi_prev = df_5m.iloc[-2].get("rsi", last5.get("rsi"))
    rsi_rising = last5.get("rsi") is not None and rsi_prev is not None and last5["rsi"] > rsi_prev
    rsi_falling = last5.get("rsi") is not None and rsi_prev is not None and last5["rsi"] < rsi_prev

    score = 0
    # Alignment score
    if strict_align or majority_mode:
        score += 1
    # ADX score
    if adx_conf in ("MEDIUM", "HIGH"):
        score += 1
    # MACD & RSI agreement score
    # (direction-specific below)
    # Micro-structure score will be added on trigger

    # Directional checks
    def make_response(action, conf, sl, tp):
        return {
            "action": action,
            "confidence": conf,
            "confidence_emoji": _confidence_emoji(conf),
            "signal_type": "SUPERTREND",
            "entry": float(last5["close"]),
            "sl": sl,
            "tp": tp,
            "timeframe": "5m",
            "market_status": status_msg
        }

    # BUY
    if st_5m == 1 and (strict_align or majority_mode):
        pa_ok = (
            price > recent_high
            and (last5["stoch_k"] > last5["stoch_d"] or rsi_rising)
            and (hist_now > 0 or hist_now > hist_prev)
        )
        if pa_ok:
            score_dir = score + 1  # MACD/RSI agree
            score_dir += 1  # micro-structure break
            # Confidence from score
            if score_dir >= 4:
                score_conf = "HIGH"
            elif score_dir == 3:
                score_conf = "MEDIUM"
            elif score_dir == 2:
                score_conf = "LOW"
            else:
                score_conf = "LOW"
            # Majority downgrade
            if majority_mode and score_conf == "HIGH":
                score_conf = "MEDIUM"
            elif majority_mode and score_conf == "MEDIUM":
                score_conf = "LOW"
            # ADX boost/downgrade
            if adx5_val >= 25:
                score_conf = "HIGH"
            if adx1h_val < 20 or adx4h_val < 20:
                score_conf = "LOW"
            # SL/TP tuned for scalping
            sl_dist = min(atr1h * 1.0, 20.0)
            tp_mult = 1.0 if adx5_val >= 25 or adx15_val >= 25 else 0.8
            tp_cap = 12.0 if adx5_val >= 25 or adx15_val >= 25 else 8.0
            tp_dist = min(atr5 * tp_mult, tp_cap)
            sl = price - sl_dist
            tp = price + tp_dist
            if score_dir >= 2:
                return make_response("BUY", score_conf, sl, tp)

    # SELL
    if st_5m == -1 and (strict_align or majority_mode):
        pa_ok = (
            price < recent_low
            and (last5["stoch_k"] < last5["stoch_d"] or rsi_falling)
            and (hist_now < 0 or hist_now < hist_prev)
        )
        if pa_ok:
            score_dir = score + 1  # MACD/RSI agree
            score_dir += 1  # micro-structure break
            if score_dir >= 4:
                score_conf = "HIGH"
            elif score_dir == 3:
                score_conf = "MEDIUM"
            elif score_dir == 2:
                score_conf = "LOW"
            else:
                score_conf = "LOW"
            if majority_mode and score_conf == "HIGH":
                score_conf = "MEDIUM"
            elif majority_mode and score_conf == "MEDIUM":
                score_conf = "LOW"
            if adx5_val >= 25:
                score_conf = "HIGH"
            if adx1h_val < 20 or adx4h_val < 20:
                score_conf = "LOW"
            sl_dist = min(atr1h * 1.0, 20.0)
            tp_mult = 1.0 if adx5_val >= 25 or adx15_val >= 25 else 0.8
            tp_cap = 12.0 if adx5_val >= 25 or adx15_val >= 25 else 8.0
            tp_dist = min(atr5 * tp_mult, tp_cap)
            sl = price + sl_dist
            tp = price - tp_dist
            if score_dir >= 2:
                return make_response("SELL", score_conf, sl, tp)

    return {
        "action": "NO_TRADE",
        "reason": "SuperTrend signals not aligned across timeframes",
        "market_status": status_msg,
        "signal_type": "SUPERTREND"
    }


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
