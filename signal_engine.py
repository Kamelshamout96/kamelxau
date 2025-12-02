def get_trend_signal(row):
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return "bullish"
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return "bearish"
    return "neutral"

def check_entry(df_m15, df_h1, df_h4):
    last15=df_m15.iloc[-1]; last1=df_h1.iloc[-1]; last4=df_h4.iloc[-1]
    if get_trend_signal(last1)!=get_trend_signal(last4):
        return {"action":"NO_TRADE","reason":"HTF mismatch"}
    trend=get_trend_signal(last4)
    if trend=="bullish":
        if last15["rsi"]>55 and last15["macd"]>last15["macd_signal"] and last15["stoch_k"]>last15["stoch_d"] and last15["adx"]>20 and last15["close"]>last15["don_high"]:
            return {"action":"BUY","entry":last15["close"],"sl":last15["close"]-1.5*last15["atr"],"tp":last15["close"]+3*last15["atr"]}
    if trend=="bearish":
        if last15["rsi"]<45 and last15["macd"]<last15["macd_signal"] and last15["stoch_k"]<last15["stoch_d"] and last15["adx"]>20 and last15["close"]<last15["don_low"]:
            return {"action":"SELL","entry":last15["close"],"sl":last15["close"]+1.5*last15["atr"],"tp":last15["close"]-3*last15["atr"]}
    return {"action":"NO_TRADE","reason":"No confluence"}
