def _trend(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


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
            return {
                "action": "BUY",
                "confidence": "HIGH",
                "confidence_emoji": "⭐⭐⭐",
                "entry": float(last5["close"]),
                "sl": float(last5["close"] - 1.5 * last5["atr"]),
                "tp": float(last5["close"] + 3 * last5["atr"]),
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
            return {
                "action": "BUY",
                "confidence": "MEDIUM",
                "confidence_emoji": "⭐⭐",
                "entry": float(last5["close"]),
                "sl": float(last5["close"] - 1.5 * last5["atr"]),
                "tp": float(last5["close"] + 3 * last5["atr"]),
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
            return {
                "action": "SELL",
                "confidence": "HIGH",
                "confidence_emoji": "⭐⭐⭐",
                "entry": float(last5["close"]),
                "sl": float(last5["close"] + 1.5 * last5["atr"]),
                "tp": float(last5["close"] - 3 * last5["atr"]),
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
            return {
                "action": "SELL",
                "confidence": "MEDIUM",
                "confidence_emoji": "⭐⭐",
                "entry": float(last5["close"]),
                "sl": float(last5["close"] + 1.5 * last5["atr"]),
                "tp": float(last5["close"] - 3 * last5["atr"]),
                "timeframe": "5m",
                "market_status": status_msg
            }

    return {
        "action": "NO_TRADE", 
        "reason": f"Waiting for entry. Trend is {main_trend} but not enough indicators aligned.",
        "market_status": status_msg
    }
