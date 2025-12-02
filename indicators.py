import ta
import pandas as pd

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50/200, RSI, Stoch, MACD, ADX, ATR, Donchian, and kumo proxy.
    Expects index=datetime and columns: open, high, low, close, volume.
    """
    # Validate we have enough data
    if len(df) < 250:
        raise ValueError(f"Insufficient data for indicators: {len(df)} rows (need at least 250)")
    
    # Check required columns
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    df = df.copy()

    # EMAs (need 200+ periods)
    df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()

    # RSI (needs 14 periods)
    rsi = ta.momentum.RSIIndicator(close=df["close"], window=14)
    df["rsi"] = rsi.rsi()

    # Stochastic (needs 14 periods)
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

    # ADX (needs 14 periods)
    adx = ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=14
    )
    df["adx"] = adx.adx()

    # ATR (needs 14 periods)
    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    )
    df["atr"] = atr.average_true_range()

    # Donchian (needs 20 periods)
    df["don_high"] = df["high"].rolling(window=20, min_periods=20).max()
    df["don_low"] = df["low"].rolling(window=20, min_periods=20).min()

    # "Kumo" proxy using EMAs (structure only)
    df["kumo_top"] = df["ema50"]
    df["kumo_bottom"] = df["ema200"]

    return df.dropna()
