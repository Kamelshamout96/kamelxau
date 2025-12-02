from utils import update_history, to_candles
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry
from datetime import datetime

print("=" * 70)
print("TESTING LIVE-ENHANCED SIGNAL SYSTEM")
print("=" * 70)

try:
    # 1) Fetch data with live price integration
    print("\n📊 Step 1: Fetching historical data + LIVE price patch...")
    hist = update_history()
    
    print(f"\n✓ Total data points: {len(hist)}")
    print(f"  Latest timestamp: {hist.index[-1]}")
    print(f"  Latest close: ${hist['close'].iloc[-1]:.2f}")
    print(f"  Current system time: {datetime.now()}")
    
    # Check freshness
    time_diff = datetime.now() - hist.index[-1]
    print(f"  Data age: {time_diff.total_seconds()/60:.1f} minutes")
    
    # 2) Build candles
    print("\n📊 Step 2: Building multi-timeframe candles...")
    candles_5m = to_candles(hist, "5T")
    candles_15m = to_candles(hist, "15T")
    candles_1h = to_candles(hist, "60T")
    candles_4h = to_candles(hist, "240T")
    
    print(f"  5m candles: {len(candles_5m)} (latest: {candles_5m.index[-1]})")
    print(f"  15m candles: {len(candles_15m)}")
    print(f"  1H candles: {len(candles_1h)}")
    print(f"  4H candles: {len(candles_4h)}")
    
    # 3) Add indicators
    print("\n📊 Step 3: Calculating indicators...")
    df_5m = add_all_indicators(candles_5m)
    df_15m = add_all_indicators(candles_15m)
    df_1h = add_all_indicators(candles_1h)
    df_4h = add_all_indicators(candles_4h)
    print("  ✓ All indicators calculated")
    
    # 4) Check for entry signals
    print("\n📊 Step 4: Checking for trading signals...")
    print("-" * 70)
    
    # Check regular signals
    signal = check_entry(df_5m, df_15m, df_1h, df_4h)
    
    # If no regular signal, check SuperTrend
    if signal.get("action") == "NO_TRADE":
        supertrend_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
        if supertrend_signal.get("action") in ("BUY", "SELL"):
            signal = supertrend_signal
    
    # Display result
    print("\n🎯 SIGNAL RESULT:")
    print("=" * 70)
    
    if signal.get("action") in ("BUY", "SELL"):
        action_emoji = "🟢" if signal["action"] == "BUY" else "🔴"
        print(f"\n{action_emoji} {signal['action']} SIGNAL DETECTED!")
        print(f"  Confidence: {signal.get('confidence', 'N/A')} {signal.get('confidence_emoji', '')}")
        print(f"  Signal Type: {signal.get('signal_type', 'REGULAR')}")
        print(f"  Entry Price: ${signal['entry']:.2f}")
        print(f"  Stop Loss: ${signal['sl']:.2f} (Distance: {abs(signal['entry'] - signal['sl']):.2f})")
        print(f"  Take Profit: ${signal['tp']:.2f} (Distance: {abs(signal['tp'] - signal['entry']):.2f})")
        print(f"  Market Status: {signal.get('market_status', 'N/A')}")
    else:
        print(f"\n⏸ NO TRADE")
        print(f"  Reason: {signal.get('reason', 'N/A')}")
        print(f"  Market Status: {signal.get('market_status', 'N/A')}")
    
    print("\n" + "=" * 70)
    print("✓ TEST COMPLETED SUCCESSFULLY")
    print("=" * 70)
    
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
