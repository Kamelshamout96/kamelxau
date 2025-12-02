from signal_engine import calculate_sl_tp, check_entry, check_supertrend_entry
import pandas as pd
import numpy as np

def test_calculate_sl_tp():
    print("Testing calculate_sl_tp...")
    
    # Case 1: Normal ATR (small)
    # Entry 2000, ATR 2.0
    # SL dist = 1.6 (0.8 * 2), TP dist = 3.0 (1.5 * 2)
    # Both < 10.0, so no cap
    sl, tp = calculate_sl_tp(2000.0, 2.0, "BUY")
    print(f"Case 1 (BUY, ATR=2): SL={sl}, TP={tp}")
    assert sl == 2000.0 - 1.6
    assert tp == 2000.0 + 3.0
    
    # Case 2: High ATR (large)
    # Entry 2000, ATR 20.0
    # SL dist = 16.0 (0.8 * 20), TP dist = 30.0 (1.5 * 20)
    # Both > 10.0, so capped at 10.0
    sl, tp = calculate_sl_tp(2000.0, 20.0, "BUY")
    print(f"Case 2 (BUY, ATR=20): SL={sl}, TP={tp}")
    assert sl == 2000.0 - 10.0
    assert tp == 2000.0 + 10.0
    
    # Case 3: SELL High ATR
    sl, tp = calculate_sl_tp(2000.0, 20.0, "SELL")
    print(f"Case 3 (SELL, ATR=20): SL={sl}, TP={tp}")
    assert sl == 2000.0 + 10.0
    assert tp == 2000.0 - 10.0
    
    print("✓ calculate_sl_tp tests passed")

def create_mock_df(trend="bullish", close_price=2000.0, atr=2.0):
    df = pd.DataFrame(index=[0])
    df["close"] = close_price
    df["high"] = close_price + 5
    df["low"] = close_price - 5
    df["open"] = close_price
    df["volume"] = 1000
    
    if trend == "bullish":
        df["ema50"] = close_price - 10
        df["ema200"] = close_price - 20
        df["supertrend_direction"] = 1
    elif trend == "bearish":
        df["ema50"] = close_price + 10
        df["ema200"] = close_price + 20
        df["supertrend_direction"] = -1
    else: # neutral
        df["ema50"] = close_price + 10
        df["ema200"] = close_price - 10
        df["supertrend_direction"] = 1
        
    # Add other required columns
    df["rsi"] = 60 if trend == "bullish" else 40
    df["macd"] = 1 if trend == "bullish" else -1
    df["macd_signal"] = 0
    df["stoch_k"] = 60 if trend == "bullish" else 40
    df["stoch_d"] = 50
    df["adx"] = 25
    df["don_high"] = close_price - 1 if trend == "bullish" else close_price + 10 # Trigger breakout
    df["don_low"] = close_price + 1 if trend == "bearish" else close_price - 10
    df["atr"] = atr
    
    return df

def test_signals_capped():
    print("\nTesting signal capping...")
    
    # Create scenario for BUY signal with High ATR
    df_4h = create_mock_df("bullish", atr=20.0)
    df_1h = create_mock_df("bullish", atr=20.0)
    df_15m = create_mock_df("bullish", atr=20.0)
    df_5m = create_mock_df("bullish", atr=20.0)
    
    # Check regular entry
    # We need to make sure conditions are met for BUY
    # RSI > 55 (60), MACD > Signal (1>0), StochK > StochD (60>50), ADX > 20 (25), Close > DonHigh
    
    result = check_entry(df_5m, df_15m, df_1h, df_4h)
    print("Signal Result:", result)
    
    if result["action"] == "BUY":
        entry = result["entry"]
        sl = result["sl"]
        tp = result["tp"]
        
        sl_dist = entry - sl
        tp_dist = tp - entry
        
        print(f"Entry: {entry}, SL: {sl} (dist: {sl_dist}), TP: {tp} (dist: {tp_dist})")
        
        if abs(sl_dist - 10.0) < 0.001 and abs(tp_dist - 10.0) < 0.001:
            print("✓ Signal SL/TP capped correctly")
        else:
            print("✗ Signal SL/TP NOT capped correctly")
    else:
        print("✗ No BUY signal generated, cannot test cap")

if __name__ == "__main__":
    test_calculate_sl_tp()
    test_signals_capped()
