import ta
import pandas as pd

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50/200, RSI, Stoch, MACD, ADX, ATR, Donchian, and kumo proxy.
    Expects index=datetime and columns: open, high, low, close, volume.
    """
    df = df.copy()

    # EMAs
    df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()

    # RSI
    rsi = ta.momentum.RSIIndicator(close=df["close"], window=14)
    df["rsi"] = rsi.rsi()

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14,
        smooth_window=3,
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # MACD
    macd = ta.trend.MACD(close=df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    # ADX
    adx = ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=14
    )
    df["adx"] = adx.adx()

    # ATR
    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    )
    df["atr"] = atr.average_true_range()

    # Donchian (20-period high/low)
    df["don_high"] = df["high"].rolling(window=20).max()
    df["don_low"] = df["low"].rolling(window=20).min()

    # "Kumo" proxy using EMAs (structure only)
    df["kumo_top"] = df["ema50"]
    df["kumo_bottom"] = df["ema200"]

    return df.dropna()
