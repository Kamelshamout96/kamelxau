from signal_engine import check_entry
import pandas as pd
import numpy as np

# Mock data helper
def create_mock_df(trend="bullish", close_price=2000.0):
    df = pd.DataFrame(index=[0])
    df["close"] = close_price
    
    if trend == "bullish":
        df["ema50"] = close_price - 10
        df["ema200"] = close_price - 20
    elif trend == "bearish":
        df["ema50"] = close_price + 10
        df["ema200"] = close_price + 20
    else: # neutral
        df["ema50"] = close_price + 10
        df["ema200"] = close_price - 10
        
    # Add other required columns with dummy values
    df["rsi"] = 50
    df["macd"] = 0
    df["macd_signal"] = 0
    df["stoch_k"] = 50
    df["stoch_d"] = 50
    df["adx"] = 25
    df["don_high"] = close_price + 5
    df["don_low"] = close_price - 5
    df["atr"] = 2.0
    return df

print("Test 1: All Bullish (Should be NO_TRADE waiting for 5m triggers)")
df_4h = create_mock_df("bullish")
df_1h = create_mock_df("bullish")
df_15m = create_mock_df("bullish")
df_5m = create_mock_df("bullish") # But indicators are neutral

result = check_entry(df_5m, df_15m, df_1h, df_4h)
print("Result:", result)

print("\nTest 2: HTF Mismatch (4H Bearish, 1H Bullish)")
df_4h_bear = create_mock_df("bearish")
result = check_entry(df_5m, df_15m, df_1h, df_4h_bear)
print("Result:", result)
