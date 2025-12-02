import ta
import pandas as pd

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50/200, RSI, Stoch, MACD, ADX, ATR, Donchian, and kumo proxy.
    Expects index=datetime and columns: open, high, low, close, volume.
    
    ADAPTIVE MODE: Works with limited data by adjusting indicator periods
    """
    # Check required columns
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    df = df.copy()
    data_len = len(df)
    
    # Adaptive periods based on available data
    if data_len < 50:
        # Very limited data - use minimum periods
        ema_short = min(10, data_len - 1)
        ema_long = min(20, data_len - 1)
        rsi_period = min(7, data_len - 1)
        stoch_period = min(7, data_len - 1)
        adx_period = min(7, data_len - 1)
        atr_period = min(7, data_len - 1)
        don_period = min(10, data_len - 1)
        print(f"  ⚠ Limited data mode: Using shorter periods (EMA{ema_short}/{ema_long})")
    elif data_len < 200:
        # Moderate data - use reduced periods
        ema_short = 20
        ema_long = min(50, data_len - 1)
        rsi_period = 14
        stoch_period = 14
        adx_period = 14
        atr_period = 14
        don_period = 20
        print(f"  ⚠ Reduced data mode: Using EMA{ema_short}/{ema_long}")
    else:
        # Full data - use standard periods
        ema_short = 50
        ema_long = 200
        rsi_period = 14
        stoch_period = 14
        adx_period = 14
        atr_period = 14
        don_period = 20

    # EMAs
    df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=ema_short).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=ema_long).ema_indicator()

    # RSI
    rsi = ta.momentum.RSIIndicator(close=df["close"], window=rsi_period)
    df["rsi"] = rsi.rsi()

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=stoch_period,
        smooth_window=min(3, stoch_period),
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # MACD
    macd = ta.trend.MACD(close=df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    # ADX
    adx = ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=adx_period
    )
    df["adx"] = adx.adx()

    # ATR
    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=atr_period
    )
    df["atr"] = atr.average_true_range()

    # Donchian
    df["don_high"] = df["high"].rolling(window=don_period, min_periods=1).max()
    df["don_low"] = df["low"].rolling(window=don_period, min_periods=1).min()

    # "Kumo" proxy using EMAs (structure only)
    df["kumo_top"] = df["ema50"]
    df["kumo_bottom"] = df["ema200"]
    
    # SuperTrend Indicator (adaptive period)
    st_period = min(10, data_len - 1)
    df = add_supertrend(df, period=st_period, multiplier=3)

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
