"""
PURE LIVE SIGNAL ANALYZER
==========================
Analyzes ONLY pure live collected data (NO Yahoo Finance)
Generates trading signals from web-scraped data
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry


PURE_DATA_FILE = Path("data") / "pure_live_gold.csv"


def load_pure_data():
    """Load pure live collected data"""
    if not PURE_DATA_FILE.exists():
        raise Exception("No pure data available! Run: py pure_collector.py collect 300")
    
    df = pd.read_csv(PURE_DATA_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp').sort_index()
    
    return df


def build_candles_pure(df_1m, timeframe):
    """Build candles from 1-minute pure data"""
    if len(df_1m) < 10:
        raise Exception(f"Not enough data: {len(df_1m)} rows. Need 300+")
    
    candles = df_1m.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    return candles


def analyze_pure():
    """
    Complete analysis using PURE live data ONLY
    """
    print("\n" + "=" * 70)
    print("🔴 PURE LIVE SIGNAL ANALYZER - NO YAHOO FINANCE")
    print("=" * 70)
    print("Data source: livepriceofgold.com (Web Scraping ONLY)")
    print("-" * 70)
    
    try:
        # 1) Load pure 1-minute data
        print("\n📊 Step 1: Loading pure live data...")
        df_1m = load_pure_data()
        
        print(f"  ✅ Loaded {len(df_1m)} x 1-minute candles")
        print(f"  📅 Range: {df_1m.index[0]} → {df_1m.index[-1]}")
        print(f"  💰 Latest: ${df_1m['close'].iloc[-1]:.2f}")
        print(f"  ⏰ Age: {(datetime.now() - df_1m.index[-1]).total_seconds()/60:.1f} min")
        
        # Check sufficiency
        if len(df_1m) < 300:
            print(f"\n  ⚠ WARNING: Only {len(df_1m)} candles available")
            print(f"     Recommended: 300+ candles for accurate indicators")
            print(f"     Run: py pure_collector.py collect 300")
            print(f"     Proceeding with available data...")
        
        # 2) Build multi-timeframe candles
        print("\n📊 Step 2: Building timeframe candles...")
        
        candles_5m = build_candles_pure(df_1m, "5T")
        candles_15m = build_candles_pure(df_1m, "15T")
        candles_1h = build_candles_pure(df_1m, "60T")
        candles_4h = build_candles_pure(df_1m, "240T")
        
        print(f"  ✅ 5m:  {len(candles_5m):3d} candles")
        print(f"  ✅ 15m: {len(candles_15m):3d} candles")
        print(f"  ✅ 1H:  {len(candles_1h):3d} candles")
        print(f"  ✅ 4H:  {len(candles_4h):3d} candles")
        
        # Warn if not enough for EMA200
        if len(candles_4h) < 200:
            print(f"\n  ⚠ Only {len(candles_4h)} x 4H candles (need 200 for EMA200)")
            print(f"     Indicators will use available data")
        
        # 3) Calculate indicators
        print("\n📊 Step 3: Calculating indicators...")
        
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)
        
        print("  ✅ All indicators calculated")
        
        # Show current indicators
        last = df_5m.iloc[-1]
        print(f"\n  📈 Current 5m Indicators:")
        print(f"     Price: ${last['close']:.2f}")
        print(f"     RSI: {last['rsi']:.1f}")
        print(f"     MACD: {last['macd']:.2f} (Signal: {last['macd_signal']:.2f})")
        print(f"     EMA50: ${last['ema50']:.2f} | EMA200: ${last['ema200']:.2f}")
        print(f"     ADX: {last['adx']:.1f}")
        if 'supertrend_direction' in last.index:
            print(f"     SuperTrend: {'🟢 Bullish' if last['supertrend_direction'] == 1 else '🔴 Bearish'}")
        
        # 4) Generate signals
        print("\n📊 Step 4: Analyzing market & generating signals...")
        print("-" * 70)
        
        # Try multi-indicator signals
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)
        signal_type = "MULTI-INDICATOR"
        
        # Fallback to SuperTrend if no signal
        if signal.get("action") == "NO_TRADE":
            st_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
            if st_signal.get("action") in ("BUY", "SELL"):
                signal = st_signal
                signal_type = "SUPERTREND"
        
        # 5) Display results
        print("\n" + "=" * 70)
        print("🎯 SIGNAL RESULT")
        print("=" * 70)
        
        if signal.get("action") in ("BUY", "SELL"):
            # 🚨 TRADE SIGNAL!
            action = signal["action"]
            emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
            
            print(f"\n{emoji} SIGNAL DETECTED!\n")
            
            # Signal info
            print(f"📊 SIGNAL INFO:")
            print(f"   Type: {signal_type}")
            print(f"   Confidence: {signal.get('confidence', 'N/A')} {signal.get('confidence_emoji', '')}")
            print(f"   Timeframe: {signal.get('timeframe', 'N/A')}")
            
            # Trade setup
            entry = signal['entry']
            sl = signal['sl']
            tp = signal['tp']
            
            print(f"\n💰 TRADE SETUP:")
            print(f"   Entry: ${entry:.2f}")
            print(f"   Stop Loss: ${sl:.2f}")
            print(f"   Take Profit: ${tp:.2f}")
            
            # Risk calculations
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            sl_pips = sl_dist * 10
            tp_pips = tp_dist * 10
            rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 0
            
            print(f"\n📏 RISK MANAGEMENT:")
            print(f"   SL: ${sl_dist:.2f} ({sl_pips:.0f} pips)")
            print(f"   TP: ${tp_dist:.2f} ({tp_pips:.0f} pips)")
            print(f"   Risk:Reward = 1:{rr_ratio:.2f}")
            
            # Position sizing (example)
            account = 10000
            risk_pct = 1.0
            risk_amt = account * (risk_pct / 100)
            position = risk_amt / sl_dist
            potential_profit = position * tp_dist
            
            print(f"\n💼 POSITION SIZE (${account} account, {risk_pct}% risk):")
            print(f"   Risk: ${risk_amt:.2f}")
            print(f"   Position: {position:.4f} oz")
            print(f"   Potential Profit: ${potential_profit:.2f}")
            print(f"   Potential Loss: ${risk_amt:.2f}")
            
            # Market context
            print(f"\n📈 MARKET:")
            print(f"   {signal.get('market_status', 'N/A')}")
            
            # Telegram message
            print(f"\n📱 TELEGRAM MESSAGE:")
            print("-" * 70)
            
            conf = signal.get('confidence', 'UNKNOWN')
            conf_emoji = signal.get('confidence_emoji', '')
            
            if signal_type == "SUPERTREND":
                conf_text = "⭐ SuperTrend (Fast)"
            elif conf == "HIGH":
                conf_text = "⭐⭐⭐ High Accuracy"
            else:
                conf_text = "⭐⭐ Medium Accuracy"
            
            msg = (
                f"<b>═══════════════════</b>\n"
                f"<b>{emoji} XAUUSD (PURE LIVE)</b>\n"
                f"<b>═══════════════════</b>\n\n"
                f"🎯 <b>Confidence:</b> {conf} {conf_emoji}\n"
                f"📊 <b>Type:</b> {signal_type}\n"
                f"💰 <b>Entry:</b> {entry:.2f}\n"
                f"🛑 <b>SL:</b> {sl:.2f} ({sl_pips:.0f} pips)\n"
                f"🎯 <b>TP:</b> {tp:.2f} ({tp_pips:.0f} pips)\n"
                f"📊 <b>R:R:</b> 1:{rr_ratio:.2f}\n\n"
                f"<i>{conf_text}</i>\n"
                f"<b>═══════════════════</b>"
            )
            print(msg)
            print("-" * 70)
            
        else:
            # ⏸ NO TRADE
            print(f"\n⏸ NO TRADE")
            print(f"\n  Reason: {signal.get('reason', 'N/A')}")
            print(f"  Market: {signal.get('market_status', 'N/A')}")
        
        print("\n" + "=" * 70)
        print("✅ ANALYSIS COMPLETE (100% PURE LIVE DATA)")
        print("=" * 70 + "\n")
        
        return signal
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    analyze_pure()
