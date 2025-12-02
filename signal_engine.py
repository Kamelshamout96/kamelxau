def _trend(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"


def check_entry(df_5m, df_15m, df_1h, df_4h):
    """Multi-timeframe logic:
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

    if trend_1h != trend_4h or trend_1h == "neutral":
        return {"action": "NO_TRADE", "reason": "HTF mismatch or neutral"}

    main_trend = trend_1h

    # extra confirmation from 15m
    mid_trend = _trend(last15)
    if mid_trend != main_trend:
        return {"action": "NO_TRADE", "reason": "15m disagrees with HTF"}

    # BUY setup
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
                "entry": float(last5["close"]),
                "sl": float(last5["close"] - 1.5 * last5["atr"]),
                "tp": float(last5["close"] + 3 * last5["atr"]),
                "timeframe": "5m",
            }

    # SELL setup
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
                "entry": float(last5["close"]),
                "sl": float(last5["close"] + 1.5 * last5["atr"]),
                "tp": float(last5["close"] - 3 * last5["atr"]),
                "timeframe": "5m",
            }

    return {"action": "NO_TRADE", "reason": "No confluence on 5m"}
