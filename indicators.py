import pandas as pd
import pandas_ta as ta

def add_all_indicators(df: pd.DataFrame):
    df["ema50"] = ta.ema(df["close"], length=50)
    df["ema200"] = ta.ema(df["close"], length=200)
    ich = ta.ichimoku(df["high"], df["low"], df["close"])
    df["kumo_top"] = ich[0]["ISA_9"]
    df["kumo_bottom"] = ich[0]["ISB_26"]
    st = ta.supertrend(df["high"], df["low"], df["close"])
    df["supertrend"] = st["SUPERT_7_3.0"]
    df["rsi"] = ta.rsi(df["close"], length=14)
    stoch = ta.stoch(df["high"], df["low"], df["close"])
    df["stoch_k"] = stoch["STOCHk_14_3_3"]
    df["stoch_d"] = stoch["STOCHd_14_3_3"]
    macd = ta.macd(df["close"])
    df["macd"] = macd["MACD_12_26_9"]
    df["macd_signal"] = macd["MACDs_12_26_9"]
    df["adx"] = ta.adx(df["high"], df["low"], df["close"])["ADX_14"]
    df["obv"] = ta.obv(df["close"], df["volume"])
    don = ta.donchian(df["high"], df["low"], lower_length=20, upper_length=20)
    df["don_low"] = don["DCL_20_20"]
    df["don_high"] = don["DCU_20_20"]
    df["atr"] = ta.atr(df["high"], df["low"], df["close"])
    return df.dropna()
