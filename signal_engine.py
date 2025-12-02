def _trend(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


def calculate_sl_tp(entry, atr, direction, sl_atr_mult=0.6, tp_atr_mult=1.0, max_dist=10.0):
    """
    Calculate SL and TP with a maximum distance cap for scalp trades.
    max_dist=10.0 corresponds to 100 pips (1 pip = $0.10).
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
    last5 = df_5m.iloc[-1]
    prev5 = df_5m.iloc[-2] if len(df_5m) > 1 else df_5m.iloc[-1]
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

    if mid_trend != trend_1h:
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
    adx_ok = last5["adx"] >= 22
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
            and over_extension < 0.0035  # avoid chasing extended moves
        )
        relaxed_buy = (
            price > ema50 > ema200
            and last5["rsi"] > 54
            and last5["macd"] > last5["macd_signal"]
            and last5["stoch_k"] > last5["stoch_d"]
            and last5["adx"] > 18
            and over_extension < 0.005
        )

        if strict_buy:
            sl, tp = calculate_sl_tp(price, last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "HIGH",
                "confidence_emoji": "***",
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
                "confidence_emoji": "**",
                "entry": float(price),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg,
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
            and last5["adx"] > 18
            and over_extension < 0.005
        )

        if strict_sell:
            sl, tp = calculate_sl_tp(price, last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "HIGH",
                "confidence_emoji": "***",
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
                "confidence_emoji": "**",
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
    SuperTrend-only signals (⭐ Simple & Fast)
    
    Logic:
    - Uses SuperTrend indicator on multiple timeframes
    - BUY when price is above SuperTrend (direction = 1)
    - SELL when price is below SuperTrend (direction = -1)
    - Requires alignment across 15m, 1H, and 4H
    """
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
