"""
Live Data Signal Generator
===========================
Analyzes live collected data and generates trading signals
"""

from live_data_collector import get_live_collected_data, build_timeframe_candles
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry
from datetime import datetime


def analyze_live_data():
    """
    Analyze collected live data and generate trading signals
    """
    print("=" * 70)
    print("LIVE DATA ANALYSIS & SIGNAL GENERATION")
    print("=" * 70)
    
    try:
        # 1) Load collected 1-minute data
        print("\n📊 Step 1: Loading collected live data...")
        df_1m = get_live_collected_data()
        
        print(f"  ✓ Loaded {len(df_1m)} x 1-minute candles")
        print(f"  Time range: {df_1m.index[0]} to {df_1m.index[-1]}")
        print(f"  Latest price: ${df_1m['close'].iloc[-1]:.2f}")
        print(f"  Data age: {(datetime.now() - df_1m.index[-1]).total_seconds()/60:.1f} minutes")
        
        # 2) Build multi-timeframe candles
        print("\n📊 Step 2: Building multi-timeframe candles...")
        
        candles_5m = build_timeframe_candles(df_1m, "5T")
        candles_15m = build_timeframe_candles(df_1m, "15T")
        candles_1h = build_timeframe_candles(df_1m, "60T")
        candles_4h = build_timeframe_candles(df_1m, "240T")
        
        print(f"  ✓ 5-minute: {len(candles_5m)} candles")
        print(f"  ✓ 15-minute: {len(candles_15m)} candles")
        print(f"  ✓ 1-hour: {len(candles_1h)} candles")
        print(f"  ✓ 4-hour: {len(candles_4h)} candles")
        
        # Check if we have enough data for indicators (need 200 for EMA200)
        min_candles_needed = 200
        if len(candles_4h) < min_candles_needed:
            print(f"\n⚠ WARNING: Need at least {min_candles_needed} x 4H candles for accurate indicators")
            print(f"  Current: {len(candles_4h)} candles")
            print(f"  You need to collect data for ~{min_candles_needed * 4 / 24:.1f} days")
            print(f"  Proceeding with available data (indicators may be less accurate)...")
        
        # 3) Calculate indicators
        print("\n📊 Step 3: Calculating technical indicators...")
        
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)
        
        print("  ✓ All indicators calculated")
        
        # Show latest indicator values for 5m
        last_5m = df_5m.iloc[-1]
        print(f"\n  Latest 5m indicators:")
        print(f"    RSI: {last_5m['rsi']:.1f}")
        print(f"    EMA50: ${last_5m['ema50']:.2f}")
        print(f"    EMA200: ${last_5m['ema200']:.2f}")
        print(f"    ADX: {last_5m['adx']:.1f}")
        
        # 4) Generate signals
        print("\n📊 Step 4: Generating trading signals...")
        print("-" * 70)
        
        # Check regular signals
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)
        
        # If no regular signal, check SuperTrend
        if signal.get("action") == "NO_TRADE":
            supertrend_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
            if supertrend_signal.get("action") in ("BUY", "SELL"):
                signal = supertrend_signal
        
        # 5) Display result
        print("\n🎯 SIGNAL RESULT:")
        print("=" * 70)
        
        if signal.get("action") in ("BUY", "SELL"):
            action_emoji = "🟢" if signal["action"] == "BUY" else "🔴"
            print(f"\n{action_emoji} {signal['action']} SIGNAL DETECTED!")
            print(f"\n  📊 Signal Details:")
            print(f"    Confidence: {signal.get('confidence', 'N/A')} {signal.get('confidence_emoji', '')}")
            print(f"    Signal Type: {signal.get('signal_type', 'REGULAR')}")
            print(f"    Timeframe: {signal.get('timeframe', 'N/A')}")
            
            print(f"\n  💰 Trade Setup:")
            print(f"    Entry Price: ${signal['entry']:.2f}")
            print(f"    Stop Loss (SL): ${signal['sl']:.2f}")
            print(f"    Take Profit (TP): ${signal['tp']:.2f}")
            
            sl_pips = abs(signal['entry'] - signal['sl']) * 10  # Convert to pips
            tp_pips = abs(signal['tp'] - signal['entry']) * 10
            risk_reward = tp_pips / sl_pips if sl_pips > 0 else 0
            
            print(f"\n  📏 Risk Management:")
            print(f"    SL Distance: {sl_pips:.1f} pips (${abs(signal['entry'] - signal['sl']):.2f})")
            print(f"    TP Distance: {tp_pips:.1f} pips (${abs(signal['tp'] - signal['entry']):.2f})")
            print(f"    Risk:Reward = 1:{risk_reward:.2f}")
            
            print(f"\n  📈 Market Context:")
            print(f"    {signal.get('market_status', 'N/A')}")
            
        else:
            print(f"\n⏸ NO TRADE SIGNAL")
            print(f"\n  Reason: {signal.get('reason', 'N/A')}")
            print(f"  Market Status: {signal.get('market_status', 'N/A')}")
        
        print("\n" + "=" * 70)
        print("✓ ANALYSIS COMPLETE")
        print("=" * 70)
        
        return signal
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    analyze_live_data()
