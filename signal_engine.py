def _trend(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


def calculate_sl_tp(entry, atr, direction, sl_atr_mult=0.8, tp_atr_mult=1.5, max_dist=10.0):
    """
    Calculate SL and TP with a maximum distance cap.
    max_dist=10.0 corresponds to 100 pips (assuming 1 pip = $0.10)
    """
    sl_dist = atr * sl_atr_mult
    tp_dist = atr * tp_atr_mult
    
    # Cap distances
    sl_dist = min(sl_dist, max_dist)
    tp_dist = min(tp_dist, max_dist)
    
    if direction == "BUY":
        sl = entry - sl_dist
        tp = entry + tp_dist
    else: # SELL
        sl = entry + sl_dist
        tp = entry - tp_dist
        
    return float(sl), float(tp)


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """Multi-timeframe logic with dual confidence levels:
    - HIGH CONFIDENCE: All strict conditions met (⭐⭐⭐ Most Accurate)
    - MEDIUM CONFIDENCE: Relaxed conditions (⭐⭐ Less Accurate)
    
    Timeframe logic:
    - 1H + 4H define main trend
    - 15m confirms
    - 5m gives precise entry
    """
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    last1h = df_1h.iloc[-1]
    last4h = df_4h.iloc[-1]

    trend_1h = _trend(last1h)
    trend_4h = _trend(last4h)
    mid_trend = _trend(last15)

    # Construct a market status summary
    status_msg = f"Trend: 4H={trend_4h}, 1H={trend_1h}, 15m={mid_trend}"

    if trend_1h != trend_4h or trend_1h == "neutral":
        return {
            "action": "NO_TRADE", 
            "reason": f"HTF Mismatch: 4H is {trend_4h}, 1H is {trend_1h}",
            "market_status": status_msg
        }

    main_trend = trend_1h

    # extra confirmation from 15m
    if mid_trend != main_trend:
        return {
            "action": "NO_TRADE", 
            "reason": f"15m Divergence: 15m is {mid_trend} while HTF is {main_trend}",
            "market_status": status_msg
        }

    # BUY setup - HIGH CONFIDENCE (⭐⭐⭐ Strict conditions)
    if main_trend == "bullish":
        if (
            last5["rsi"] > 55
            and last5["macd"] > last5["macd_signal"]
            and last5["stoch_k"] > last5["stoch_d"]
            and last5["adx"] > 20
            and last5["close"] > last5["don_high"]
        ):
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "HIGH",
                "confidence_emoji": "⭐⭐⭐",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg
            }
        
        # BUY setup - MEDIUM CONFIDENCE (⭐⭐ Relaxed conditions)
        # At least 3 out of 5 conditions must be true
        buy_conditions = [
            last5["rsi"] > 50,  # Relaxed from 55
            last5["macd"] > last5["macd_signal"],
            last5["stoch_k"] > last5["stoch_d"],
            last5["adx"] > 15,  # Relaxed from 20
            last5["close"] > last5["ema50"]  # Replaced Donchian with simpler EMA check
        ]
        
        if sum(buy_conditions) >= 3:
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "BUY")
            return {
                "action": "BUY",
                "confidence": "MEDIUM",
                "confidence_emoji": "⭐⭐",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg
            }

    # SELL setup - HIGH CONFIDENCE (⭐⭐⭐ Strict conditions)
    if main_trend == "bearish":
        if (
            last5["rsi"] < 45
            and last5["macd"] < last5["macd_signal"]
            and last5["stoch_k"] < last5["stoch_d"]
            and last5["adx"] > 20
            and last5["close"] < last5["don_low"]
        ):
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "HIGH",
                "confidence_emoji": "⭐⭐⭐",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg
            }
        
        # SELL setup - MEDIUM CONFIDENCE (⭐⭐ Relaxed conditions)
        sell_conditions = [
            last5["rsi"] < 50,  # Relaxed from 45
            last5["macd"] < last5["macd_signal"],
            last5["stoch_k"] < last5["stoch_d"],
            last5["adx"] > 15,  # Relaxed from 20
            last5["close"] < last5["ema50"]  # Replaced Donchian with simpler EMA check
        ]
        
        if sum(sell_conditions) >= 3:
            sl, tp = calculate_sl_tp(last5["close"], last5["atr"], "SELL")
            return {
                "action": "SELL",
                "confidence": "MEDIUM",
                "confidence_emoji": "⭐⭐",
                "entry": float(last5["close"]),
                "sl": sl,
                "tp": tp,
                "timeframe": "5m",
                "market_status": status_msg
            }

    return {
        "action": "NO_TRADE", 
        "reason": f"Waiting for entry. Trend is {main_trend} but not enough indicators aligned.",
        "market_status": status_msg
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
