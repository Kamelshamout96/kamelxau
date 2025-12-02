"""
CLEAN SIGNAL ANALYZER
=====================
Analyzes collected gold prices and generates trading signals
NO Yahoo Finance - 100% Pure Data
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry


DATA_FILE = Path("data") / "gold_prices.csv"


def load_data():
    """Load collected data"""
    if not DATA_FILE.exists():
        raise Exception(f"No data found! Run: py gold_system.py collect 300")
    
    df = pd.read_csv(DATA_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').sort_index()
    
    return df


def build_candles(df_1m, timeframe):
    """Build higher timeframe candles"""
    candles = df_1m.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    return candles


def analyze():
    """Main analysis function"""
    print("\n" + "=" * 70)
    print("🔴 GOLD TRADING SIGNAL ANALYZER")
    print("=" * 70)
    print("Data Source: 100% Web Scraping (NO Yahoo Finance)")
    print("-" * 70)
    
    try:
        # Load 1-minute data
        print("\n📊 Loading data...")
        df_1m = load_data()
        
        print(f"  ✓ {len(df_1m)} x 1-minute candles")
        print(f"  📅 {df_1m.index[0]} → {df_1m.index[-1]}")
        print(f"  💰 Latest: ${df_1m['close'].iloc[-1]:.2f}")
        
        # Build timeframes
        print("\n📊 Building timeframes...")
        
        c_5m = build_candles(df_1m, "5min")
        c_15m = build_candles(df_1m, "15min")
        c_1h = build_candles(df_1m, "60min")
        c_4h = build_candles(df_1m, "240min")
        
        print(f"  5m: {len(c_5m)} | 15m: {len(c_15m)} | 1H: {len(c_1h)} | 4H: {len(c_4h)}")
        
        # Add indicators
        print("\n📊 Calculating indicators...")
        
        df_5m = add_all_indicators(c_5m)
        df_15m = add_all_indicators(c_15m)
        df_1h = add_all_indicators(c_1h)
        df_4h = add_all_indicators(c_4h)
        
        print("  ✓ Done")
        
        # Show latest indicators
        last = df_5m.iloc[-1]
        print(f"\n  📈 5m Indicators:")
        print(f"     Price: ${last['close']:.2f}")
        print(f"     RSI: {last['rsi']:.1f}")
        print(f"     EMA50: ${last['ema50']:.2f} | EMA200: ${last['ema200']:.2f}")
        print(f"     ADX: {last['adx']:.1f}")
        
        # Generate signals
        print("\n📊 Generating signals...")
        print("-" * 70)
        
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)
        
        # Try SuperTrend if no signal
        if signal.get("action") == "NO_TRADE":
            st_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
            if st_signal.get("action") in ("BUY", "SELL"):
                signal = st_signal
        
        # Display result
        print("\n" + "=" * 70)
        print("🎯 SIGNAL RESULT")
        print("=" * 70)
        
        if signal.get("action") in ("BUY", "SELL"):
            action = signal["action"]
            emoji = "🟢" if action == "BUY" else "🔴"
            
            print(f"\n{emoji} {action} SIGNAL!")
            print(f"\n📊 Confidence: {signal.get('confidence', 'N/A')} {signal.get('confidence_emoji', '')}")
            
            entry = signal['entry']
            sl = signal['sl']
            tp = signal['tp']
            
            print(f"\n💰 TRADE:")
            print(f"   Entry: ${entry:.2f}")
            print(f"   SL: ${sl:.2f} ({abs(entry-sl)*10:.0f} pips)")
            print(f"   TP: ${tp:.2f} ({abs(tp-entry)*10:.0f} pips)")
            
            rr = abs(tp-entry) / abs(entry-sl) if abs(entry-sl) > 0 else 0
            print(f"   R:R = 1:{rr:.2f}")
            
            print(f"\n📈 Market: {signal.get('market_status', 'N/A')}")
            
        else:
            print(f"\n⏸ NO TRADE")
            print(f"   {signal.get('reason', 'N/A')}")
            print(f"   {signal.get('market_status', 'N/A')}")
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze()
