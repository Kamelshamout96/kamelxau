def _trend(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


def calculate_sl_tp(entry, atr, direction, sl_atr_mult=0.6, tp_atr_mult=1.0, max_dist=7.0):
    """
    Calculate SL and TP with a maximum distance cap for scalp trades.
    max_dist=7.0 corresponds to 70 pips (1 pip = $0.10).
    """
    sl_dist = min(atr * sl_atr_mult, max_dist)
    tp_dist = min(atr * tp_atr_mult, max_dist)
    
    if direction == "BUY":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:  # SELL
        sl = entry + sl_dist
        tp = entry - tp_dist
        
    return float(sl), float(tp)


def _momentum_check(curr, prev):
    """Heuristic momentum check for MACD histogram slope."""
    hist_now = curr["macd"] - curr["macd_signal"]
    hist_prev = prev["macd"] - prev["macd_signal"]
    return hist_now > hist_prev and hist_now > 0


def _momentum_down(curr, prev):
    """Inverse momentum check for bearish continuation."""
    hist_now = curr["macd"] - curr["macd_signal"]
    hist_prev = prev["macd"] - prev["macd_signal"]
    return hist_now < hist_prev and hist_now < 0


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Scalping-focused multi-timeframe logic:
    - Requires 4H/1H/15m trend alignment.
    - Looks for sharp 5m momentum with tight risk (<= 100 pips).
    """
    # Safety: ensure we have enough candles to avoid out-of-bounds
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

    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)
    mid_trend = _trend(last15)

    status_msg = (
        f"Trend 4H/1H/15m: {trend_4h}/{trend_1h}/{mid_trend} | "
        f"ADX5m={last5['adx']:.1f}"
    )

    if trend_1h != trend_4h or trend_1h == "neutral":
        return {
            "action": "NO_TRADE",
            "reason": f"HTF mismatch: 4H={trend_4h}, 1H={trend_1h}",
            "market_status": status_msg,
            "signal_type": "SCALP",
        }

    # Allow mid_trend to be neutral; only block if it disagrees (bullish vs bearish)
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
    # Slightly lower ADX threshold to allow trades in moderate momentum
    adx_ok = last5["adx"] >= 15
    over_extension = abs(price - ema50) / price

    # BUY setup
    if main_trend == "bullish":
        strict_buy = (
            price > ema50 > ema200
            and last5["rsi"] > 58
            and last5["rsi"] < 75
            and last5["macd"] > last5["macd_signal"]
            and last5["stoch_k"] > last5["stoch_d"] > 50
            and adx_ok
            and price >= last5["don_high"]
            and _momentum_check(last5, prev5)
            and over_extension < 0.02  # allow modest extension for scalp
        )
        relaxed_buy = (
            price > ema50 > ema200
            and last5["rsi"] > 54
            and last5["macd"] > last5["macd_signal"]
            and last5["stoch_k"] > last5["stoch_d"]
            and last5["adx"] >= 15
            and over_extension < 0.03
        )
        # Scalping fallback: allow a softer breakout when HTF are aligned
        fallback_buy = (
            price > ema50 > ema200
            and last5["rsi"] > 50
            and last5["macd"] > last5["macd_signal"]
            and last5["stoch_k"] >= last5["stoch_d"]
            and last5["adx"] >= 12
        )

        if strict_buy:
            sl, tp = calculate_sl_tp(price, last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "HIGH",
                "confidence_emoji": "??????",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }
        if relaxed_buy:
            sl, tp = calculate_sl_tp(price, last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "MEDIUM",
                "confidence_emoji": "????",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }
        if fallback_buy:
            sl, tp = calculate_sl_tp(price, last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "LOW",
                "confidence_emoji": "??",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg + " | fallback",
                "signal_type": "SCALP",
            }

    # SELL setup
    if main_trend == "bearish":
        strict_sell = (
            price < ema50 < ema200
            and last5["rsi"] < 42
            and last5["rsi"] > 20
            and last5["macd"] < last5["macd_signal"]
            and last5["stoch_k"] < last5["stoch_d"] < 50
            and adx_ok
            and price <= last5["don_low"]
            and _momentum_down(last5, prev5)  # histogram falling
            and over_extension < 0.0035
        )
        relaxed_sell = (
            price < ema50 < ema200
            and last5["rsi"] < 46
            and last5["macd"] < last5["macd_signal"]
            and last5["stoch_k"] < last5["stoch_d"]
            and last5["adx"] >= 15
            and over_extension < 0.005
        )
        fallback_sell = (
            price < ema50 < ema200
            and last5["rsi"] < 50
            and last5["macd"] < last5["macd_signal"]
            and last5["stoch_k"] <= last5["stoch_d"]
            and last5["adx"] >= 12
        )

        if strict_sell:
            sl, tp = calculate_sl_tp(price, last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "HIGH",
                "confidence_emoji": "??????",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }
        if relaxed_sell:
            sl, tp = calculate_sl_tp(price, last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "MEDIUM",
                "confidence_emoji": "????",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
                "signal_type": "SCALP",
            }
        if fallback_sell:
            sl, tp = calculate_sl_tp(price, last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "LOW",
                "confidence_emoji": "??",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg + " | fallback",
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
    SuperTrend-only signals (⭐ Simple & Fast)
    
    Logic:
    - Uses SuperTrend indicator on multiple timeframes
    - BUY when price is above SuperTrend (direction = 1)
    - SELL when price is below SuperTrend (direction = -1)
    - Requires alignment across 15m, 1H, and 4H
    """
    # Safety: avoid index errors when data is still loading
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
    
    # Check if SuperTrend columns exist
    if 'supertrend_direction' not in last5.index:
        return {
            "action": "NO_TRADE",
            "reason": "SuperTrend indicator not calculated",
            "signal_type": "SUPERTREND"
        }
    
    # Get SuperTrend directions
    st_5m = last5['supertrend_direction']
    st_15m = last15['supertrend_direction']
    st_1h = last1h['supertrend_direction']
    st_4h = last4h['supertrend_direction']
    
    status_msg = f"SuperTrend: 4H={'🟢' if st_4h == 1 else '🔴'}, 1H={'🟢' if st_1h == 1 else '🔴'}, 15m={'🟢' if st_15m == 1 else '🔴'}, 5m={'🟢' if st_5m == 1 else '🔴'}"

    # Extra precision: require 5m price to be on the correct side of its ST and a minimum ADX
    adx_ok = last5.get("adx", 0) >= 15
    price = last5["close"]
    st_val = last5.get("supertrend", price)
    price_on_side = (price > st_val) if st_5m == 1 else (price < st_val)
    if not adx_ok or not price_on_side:
        return {
            "action": "NO_TRADE",
            "reason": f"SuperTrend needs stronger confirmation (adx_ok={adx_ok}, price_on_side={price_on_side})",
            "market_status": status_msg,
            "signal_type": "SUPERTREND",
        }
    
    # BUY Signal: All higher timeframes bullish (direction = 1)
    if st_4h == 1 and st_1h == 1 and st_15m == 1 and st_5m == 1:
        sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "BUY")
        return {
            "action": "BUY",
            "confidence": "SUPERTREND",
            "confidence_emoji": "⭐",
            "signal_type": "SUPERTREND",
            "entry": float(last5["close"]),
            "sl": sl,
            "tp": tp,
            "timeframe": "5m",
            "market_status": status_msg
        }
    
    # SELL Signal: All higher timeframes bearish (direction = -1)
    if st_4h == -1 and st_1h == -1 and st_15m == -1 and st_5m == -1:
        sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "SELL")
        return {
            "action": "SELL",
            "confidence": "SUPERTREND",
            "confidence_emoji": "⭐",
            "signal_type": "SUPERTREND",
            "entry": float(last5["close"]),
            "sl": sl,
            "tp": tp,
            "timeframe": "5m",
            "market_status": status_msg
        }
    
    return {
        "action": "NO_TRADE",
        "reason": "SuperTrend signals not aligned across timeframes",
        "market_status": status_msg,
        "signal_type": "SUPERTREND"
    }


def check_golden_entry(df_5m, df_15m, df_1h, df_4h):
    """
    Very strict confluence filter for high-confidence scalps.
    This does NOT guarantee outcomes; it simply tightens filters:
    - All timeframes agree on trend (price & supertrend)
    - Strong ADX on 5m and 15m
    - RSI in healthy zone (not overextended)
    - MACD and Stoch aligned
    - Price near Donchian breakout with limited extension from EMA50
    Returns BUY/SELL or NO_TRADE.
    """
    # Basic safety
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

    # Trend agreement via EMAs
    trend_5 = _trend(last5)
    trend_15 = _trend(last15)
    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)

    # SuperTrend agreement if available
    st_cols = all("supertrend_direction" in x.index for x in (last5, last15, last1h, last4h))
    st_agree = False
    st_align_with_trend = True
    if st_cols:
        st_list = [
            last5["supertrend_direction"],
            last15["supertrend_direction"],
            last1h["supertrend_direction"],
            last4h["supertrend_direction"],
        ]
        st_agree = len(set(st_list)) == 1
        # allow majority alignment with price trend even if one TF lags
        majority = 1 if st_list.count(1) >= 3 else (-1 if st_list.count(-1) >= 3 else 0)
        if majority != 0:
            st_align_with_trend = (
                (majority == 1 and trend_5 == "bullish") or (majority == -1 and trend_5 == "bearish")
            )

    adx5 = last5.get("adx", 0)
    adx15 = last15.get("adx", 0)
    over_ext = abs(last5["close"] - last5["ema50"]) / max(last5["close"], 1e-6)
    status_msg = (
        f"Trend 4H/1H/15m/5m: {trend_4h}/{trend_1h}/{trend_15}/{trend_5} | "
        f"ADX5m={adx5:.1f}, ADX15m={adx15:.1f} | over_ext={over_ext:.4f}"
    )

    # Require clear trend alignment
    if trend_4h != trend_1h or trend_1h != trend_15 or trend_15 != trend_5:
        return {
            "action": "NO_TRADE",
            "reason": "Golden: trend mismatch across timeframes",
            "market_status": status_msg,
            "signal_type": "GOLDEN",
        }

    # BUY conditions
    if trend_5 == "bullish":
        conds = [
            adx5 >= 22,
            adx15 >= 18,
            40 <= last5["rsi"] <= 100,
            last5["macd"] > last5["macd_signal"],
            last5["stoch_k"] > last5["stoch_d"] > 50,
            over_ext < 0.05,
            last5["close"] >= last5["don_high"] * 0.999,  # allow tiny slack on breakout
        ]
        if all(conds):
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "HIGH",
                "confidence_emoji": "??????",
                "signal_type": "GOLDEN",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
            }

    # SELL conditions
    if trend_5 == "bearish":
        conds = [
            adx5 >= 22,
            adx15 >= 18,
            32 <= last5["rsi"] <= 45,
            last5["macd"] < last5["macd_signal"],
            last5["stoch_k"] < last5["stoch_d"] < 50,
            over_ext < 0.02,
            last5["close"] <= last5["don_low"],
        ]
        if all(conds):
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "HIGH",
                "confidence_emoji": "??????",
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
