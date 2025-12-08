import ta
import pandas as pd
from core.utils import DataError

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50/200, RSI, Stoch, MACD, ADX, ATR, Donchian, and kumo proxy.
    Expects index=datetime and columns: open, high, low, close, volume.
    
    ADAPTIVE MODE: Works with limited data by adjusting indicator periods
    """
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    data_len = len(df)
    if data_len < 2:
        raise DataError(f"Not enough data for indicators: {data_len} rows")
    if data_len < 10:
        raise DataError(f"Need at least 10 candles for indicators. Got {data_len}.")

    if data_len < 50:
        ema_short = max(1, min(10, data_len - 1))
        ema_long = max(1, min(20, data_len - 1))
        rsi_period = max(1, min(7, data_len - 1))
        stoch_period = max(1, min(7, data_len - 1))
        # Clamp ADX/ATR to avoid ta index errors on tiny datasets
        adx_period = max(1, min(5, data_len - 2))
        atr_period = max(1, min(5, data_len - 2))
        don_period = max(1, min(10, data_len - 1))
        print(f"  Limited data mode: Using shorter periods (EMA{ema_short}/{ema_long})")
    elif data_len < 200:
        ema_short = 20
        ema_long = max(1, min(50, data_len - 1))
        rsi_period = 14
        stoch_period = 14
        adx_period = 14
        atr_period = 14
        don_period = 20
        print(f"  Reduced data mode: Using EMA{ema_short}/{ema_long}")
    else:
        ema_short = 50
        ema_long = 200
        rsi_period = 14
        stoch_period = 14
        adx_period = 14
        atr_period = 14
        don_period = 20

    df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=ema_short).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=ema_long).ema_indicator()

    rsi = ta.momentum.RSIIndicator(close=df["close"], window=rsi_period)
    df["rsi"] = rsi.rsi()

    stoch = ta.momentum.StochasticOscillator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=stoch_period,
        smooth_window=max(1, min(3, stoch_period)),
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    macd = ta.trend.MACD(close=df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    adx = ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=adx_period
    )
    df["adx"] = adx.adx()

    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=atr_period
    )
    df["atr"] = atr.average_true_range()

    df["don_high"] = df["high"].rolling(window=don_period, min_periods=1).max()
    df["don_low"] = df["low"].rolling(window=don_period, min_periods=1).min()

    df["kumo_top"] = df["ema50"]
    df["kumo_bottom"] = df["ema200"]

    st_period = max(1, min(10, data_len - 1))
    df = add_supertrend(df, period=st_period, multiplier=3)

    # Keep rows even with initial NaNs by forward/backward filling
    result = df.fillna(method="ffill").fillna(method="bfill")
    return result


def add_supertrend(df: pd.DataFrame, period: int = 10, multiplier: int = 3) -> pd.DataFrame:
    """
    Calculate SuperTrend indicator.
    Returns dataframe with:
    - supertrend
    - supertrend_direction (1 for bullish, -1 for bearish)
    """
    df = df.copy()
    period = max(1, period)

    if "atr" not in df.columns:
        atr_calc = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        df["atr"] = atr_calc.average_true_range()

    hl_avg = (df["high"] + df["low"]) / 2
    upper_band = hl_avg + (multiplier * df["atr"])
    lower_band = hl_avg - (multiplier * df["atr"])

    supertrend = [0.0] * len(df)
    direction = [1] * len(df)

    for i in range(period, len(df)):
        curr_close = df["close"].iloc[i]
        prev_close = df["close"].iloc[i - 1]

        if i == period:
            final_upper = upper_band.iloc[i]
            final_lower = lower_band.iloc[i]
        else:
            prev_st = supertrend[i - 1]
            final_upper = upper_band.iloc[i] if (upper_band.iloc[i] < prev_st or prev_close > prev_st) else prev_st
            final_lower = lower_band.iloc[i] if (lower_band.iloc[i] > prev_st or prev_close < prev_st) else prev_st

        if curr_close <= final_upper:
            supertrend[i] = final_upper
            direction[i] = -1
        else:
            supertrend[i] = final_lower
            direction[i] = 1

    df["supertrend"] = supertrend
    df["supertrend_direction"] = direction
    return df
