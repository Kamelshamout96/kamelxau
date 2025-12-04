from signal_engine import calculate_sl_tp, check_entry, check_supertrend_entry
import pandas as pd
import numpy as np


def test_calculate_sl_tp():
    print("Testing calculate_sl_tp...")

    # BUY with distinct ATR sources (SL from HTF ATR, TP from LTF ATR)
    sl, tp = calculate_sl_tp(
        2000.0,
        2.0,
        "BUY",
        sl_atr_mult=1.0,
        tp_atr_mult=1.0,
        sl_atr=10.0,
        sl_max_dist=20.0,
        tp_max_dist=7.0,
    )
    assert abs(sl - 1990.0) < 1e-9  # 10 dollars below
    assert abs(tp - 2002.0) < 1e-9  # 2 dollars above (capped by 5m ATR)

    # Caps respect max distances
    sl, tp = calculate_sl_tp(
        2000.0,
        2.0,
        "BUY",
        sl_atr_mult=1.0,
        tp_atr_mult=1.0,
        sl_atr=50.0,
        sl_max_dist=20.0,
        tp_max_dist=7.0,
    )
    assert abs(sl - 1980.0) < 1e-9  # capped at 20
    assert abs(tp - 2002.0) < 1e-9

    # SELL mirrors correctly
    sl, tp = calculate_sl_tp(
        2000.0,
        2.0,
        "SELL",
        sl_atr_mult=1.0,
        tp_atr_mult=1.0,
        sl_atr=12.0,
        sl_max_dist=20.0,
        tp_max_dist=7.0,
    )
    assert abs(sl - 2012.0) < 1e-9
    assert abs(tp - 1998.0) < 1e-9
    print("calculate_sl_tp tests passed")


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
    else:  # neutral
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
    df["don_high"] = close_price - 1 if trend == "bullish" else close_price + 10  # Trigger breakout
    df["don_low"] = close_price + 1 if trend == "bearish" else close_price - 10
    df["atr"] = atr

    return df


def test_signals_capped():
    print("\nTesting signal capping with HTF ATR for SL...")

    # Create scenario for BUY signal with higher ATR for SL
    base = create_mock_df("bullish", atr=20.0)
    # replicate rows to satisfy minimum length requirements
    df_4h = pd.concat([base] * 10, ignore_index=True)
    df_1h = pd.concat([base] * 10, ignore_index=True)
    df_15m = pd.concat([base] * 10, ignore_index=True)
    df_5m = pd.concat([base] * 10, ignore_index=True)

    result = check_entry(df_5m, df_15m, df_1h, df_4h)
    import json
    print("Signal Result:", json.dumps(result, ensure_ascii=True))

    if result["action"] == "BUY":
        entry = result["entry"]
        sl = result["sl"]
        tp = result["tp"]

        sl_dist = entry - sl
        tp_dist = tp - entry

        print(f"Entry: {entry}, SL: {sl} (dist: {sl_dist}), TP: {tp} (dist: {tp_dist})")

        # Expect SL capped at 20, TP capped at 7 with the new logic
        if abs(sl_dist - 20.0) < 0.001 and abs(tp_dist - 7.0) < 0.001:
            print("OK Signal SL/TP capped correctly (HTF ATR for SL, 5m ATR for TP)")
        else:
            print("X Signal SL/TP NOT capped correctly")
    else:
        print("X No BUY signal generated, cannot test cap")


if __name__ == "__main__":
    test_calculate_sl_tp()
    test_signals_capped()
