import ta
import pandas as pd

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50/200, RSI, Stoch, MACD, ADX, ATR, Donchian, and kumo proxy.
    Expects index=datetime and columns: open, high, low, close, volume.
    """
    # Validate we have enough data (need at least 200 for EMA200)
    if len(df) < 200:
        raise ValueError(f"Insufficient data for indicators: {len(df)} rows (need at least 200)")
    
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
    
    # SuperTrend Indicator (period=10, multiplier=3)
    # SuperTrend is a trend-following indicator based on ATR
    df = add_supertrend(df, period=10, multiplier=3)

    return df.dropna()


def add_supertrend(df, period=10, multiplier=3):
    """
    Calculate SuperTrend indicator
    Returns a dataframe with:
    - supertrend: The SuperTrend line value
    - supertrend_direction: 1 for uptrend (bullish), -1 for downtrend (bearish)
    """
    df = df.copy()
    
    # Calculate ATR if not already present
    if 'atr' not in df.columns:
        atr = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        df['atr'] = atr.average_true_range()
    
    # Calculate basic bands
    hl_avg = (df['high'] + df['low']) / 2
    
    # Upper and lower basic bands
    upper_band = hl_avg + (multiplier * df['atr'])
    lower_band = hl_avg - (multiplier * df['atr'])
    
    # Initialize SuperTrend columns
    supertrend = [0] * len(df)
    direction = [1] * len(df)  # 1 = bullish, -1 = bearish
    
    # Calculate SuperTrend
    for i in range(period, len(df)):
        # Current values
        curr_close = df['close'].iloc[i]
        prev_close = df['close'].iloc[i-1]
        
        # Adjust bands based on previous values
        if i == period:
            final_upper = upper_band.iloc[i]
            final_lower = lower_band.iloc[i]
        else:
            # Upper band
            if upper_band.iloc[i] < supertrend[i-1] or prev_close > supertrend[i-1]:
                final_upper = upper_band.iloc[i]
            else:
                final_upper = supertrend[i-1]
            
            # Lower band
            if lower_band.iloc[i] > supertrend[i-1] or prev_close < supertrend[i-1]:
                final_lower = lower_band.iloc[i]
            else:
                final_lower = supertrend[i-1]
        
        # Determine SuperTrend value and direction
        if curr_close <= final_upper:
            supertrend[i] = final_upper
            direction[i] = -1  # Bearish
        else:
            supertrend[i] = final_lower
            direction[i] = 1   # Bullish
    
    df['supertrend'] = supertrend
    df['supertrend_direction'] = direction
    
    return df
