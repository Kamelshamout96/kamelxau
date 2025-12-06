"""
Quick test for Human-Like Analysis System
==========================================
Tests the new chart analysis features
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from live_data_collector import get_live_collected_data, build_timeframe_candles
from indicators import add_all_indicators
from human_like_analyzer import HumanLikeAnalyzer, analyze_like_human


def test_human_analysis():
    """Test complete human-like analysis"""
    print("=" * 70)
    print("🎨 TESTING HUMAN-LIKE ANALYSIS SYSTEM")
    print("=" * 70)
    
    try:
        # Load data
        print("\n📊 Loading data...")
        hist = get_live_collected_data(limit=10000, days_back=10)
        print(f"   Loaded {len(hist)} 1-minute candles")
        
        # Build timeframes
        print("\n⏱ Building timeframes...")
        candles_5m = build_timeframe_candles(hist, "5min")
        candles_15m = build_timeframe_candles(hist, "15min")
        candles_1h = build_timeframe_candles(hist, "60min")
        candles_4h = build_timeframe_candles(hist, "240min")
        
        print(f"   5m: {len(candles_5m)} candles")
        print(f"   15m: {len(candles_15m)} candles")
        print(f"   1H: {len(candles_1h)} candles")
        print(f"   4H: {len(candles_4h)} candles")
        
        # Add indicators
        print("\n📈 Calculating indicators...")
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)
        print("   ✓ Indicators ready")
        
        # Test swing detection
        print("\n🔍 Testing swing point detection...")
        analyzer = HumanLikeAnalyzer()
        swings = analyzer.find_swing_points(df_1h, window=5)
        print(f"   Found {len(swings)} swing points on 1H")
        
        if swings:
            swing_highs = [s for s in swings if s.swing_type == 'high']
            swing_lows = [s for s in swings if s.swing_type == 'low']
            print(f"   - {len(swing_highs)} swing highs")
            print(f"   - {len(swing_lows)} swing lows")
            
            # Show top 3 strongest
            top_swings = sorted(swings, key=lambda x: x.strength, reverse=True)[:3]
            print(f"\n   Top 3 strongest swings:")
            for i, swing in enumerate(top_swings, 1):
                print(f"      {i}. {swing.swing_type.upper()}: ${swing.price:.2f} "
                      f"(strength {swing.strength}/5) @ {swing.time.strftime('%Y-%m-%d %H:%M')}")
        
        # Test S/R levels
        print("\n📏 Testing Support/Resistance detection...")
        sr_levels = analyzer.find_support_resistance(df_1h, swings)
        print(f"   Found {len(sr_levels)} S/R levels")
        
        if sr_levels:
            print(f"\n   Top 5 strongest levels:")
            for i, level in enumerate(sr_levels[:5], 1):
                print(f"      {i}. {level.level_type.upper()}: ${level.price:.2f} "
                      f"({level.strength} touches)")
        
        # Test trendlines
        print("\n📐 Testing trendline detection...")
        trendlines = analyzer.find_trendlines(df_1h, swings)
        print(f"   Found {len(trendlines)} trendlines")
        
        if trendlines:
            print(f"\n   Top 3 strongest trendlines:")
            for i, line in enumerate(trendlines[:3], 1):
                direction = "↗" if line.slope > 0 else "↘"
                print(f"      {i}. {line.line_type.replace('_', ' ').title()}: "
                      f"${line.start_price:.2f} → ${line.end_price:.2f} {direction} "
                      f"(strength {line.strength:.0f}, {line.touches} touches)")
        
        # Test channel detection
        print("\n📊 Testing channel detection...")
        channel = analyzer.detect_channel(trendlines)
        
        if channel:
            print(f"   ✅ CHANNEL DETECTED!")
            print(f"      Type: {channel.pattern_type.replace('_', ' ').title()}")
            print(f"      Confidence: {channel.confidence:.0f}%")
            print(f"      Expected breakout: {channel.expected_breakout.upper()}")
            if channel.target_price:
                print(f"      Target price: ${channel.target_price:.2f}")
        else:
            print("   ❌ No channel detected")
        
        # Test supply/demand zones
        print("\n🎯 Testing Supply/Demand zones...")
        zones = analyzer.find_supply_demand_zones(df_1h, swings)
        print(f"   Found {len(zones)} zones")
        
        if zones:
            demand_zones = [z for z in zones if z.zone_type == 'demand']
            supply_zones = [z for z in zones if z.zone_type == 'supply']
            print(f"   - {len(demand_zones)} demand zones")
            print(f"   - {len(supply_zones)} supply zones")
            
            print(f"\n   Fresh zones:")
            fresh_zones = [z for z in zones if z.fresh]
            for zone in fresh_zones[:3]:
                print(f"      {zone.zone_type.upper()}: "
                      f"${zone.lower_price:.2f} - ${zone.upper_price:.2f} "
                      f"(strength {zone.strength}/5)")
        
        # Test complete analysis
        print("\n" + "=" * 70)
        print("🚀 RUNNING FULL HUMAN-LIKE ANALYSIS")
        print("=" * 70)
        
        result = analyze_like_human(df_5m, df_15m, df_1h, df_4h)
        
        print(f"\n📊 FINAL RESULT:")
        print(f"   Action: {result['action']}")
        print(f"   Overall Confidence: {result['confidence']:.0f}%")
        
        if result['action'] != 'NO_TRADE':
            rec = result['recommendation']
            print(f"\n💰 Recommendation:")
            print(f"   Entry: ${rec['entry']:.2f}")
            print(f"   Stop Loss: ${rec['sl']:.2f}")
            print(f"   Take Profit: ${rec['tp']:.2f}")
            
            print(f"\n💡 Reasoning:")
            for reason in rec['reasoning'][:5]:
                print(f"     • {reason}")
        
        # Show timeframe analysis
        print(f"\n📈 Timeframe Analysis:")
        
        for tf_name in ['4H', '1H']:
            tf = result['timeframe_analysis'][tf_name]
            print(f"\n   {tf_name}:")
            print(f"     Action: {tf['action']}")
            print(f"     Confidence: {tf['confidence']:.0f}%")
            
            if tf['patterns']:
                print(f"     Patterns: {', '.join(tf['patterns'])}")
            
            if tf['key_levels']:
                print(f"     Key Levels:")
                for level_name, price in tf['key_levels'].items():
                    print(f"       - {level_name}: ${price:.2f}")
            
            if tf['action'] != 'NO_TRADE':
                print(f"     Risk:Reward: 1:{tf['risk_reward']:.2f}")
        
        print("\n" + "=" * 70)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_human_analysis()
