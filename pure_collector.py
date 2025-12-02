"""
PURE LIVE DATA COLLECTOR - NO YAHOO FINANCE
===========================================
Collects data ONLY from livepriceofgold.com web scraping
Runs continuously to build historical database
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
from utils import get_live_gold_price_usa, DataError


# Pure live data storage
PURE_DATA_DIR = Path("data")
PURE_DATA_DIR.mkdir(exist_ok=True)
PURE_DATA_FILE = PURE_DATA_DIR / "pure_live_gold.csv"


def collect_pure_live_price():
    """
    Collect PURE live price - NO Yahoo Finance
    Stores as 1-minute candles
    """
    try:
        # Get PURE live price from web scraping ONLY
        price = get_live_gold_price_usa()
        current_time = datetime.now()
        
        # Round to current minute
        timestamp = current_time.replace(second=0, microsecond=0)
        
        # Load or create database
        if PURE_DATA_FILE.exists():
            df = pd.read_csv(PURE_DATA_FILE)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Check if minute exists
            existing = df[df['timestamp'] == timestamp]
            
            if not existing.empty:
                # Update existing candle
                idx = existing.index[0]
                df.loc[idx, 'close'] = price
                df.loc[idx, 'high'] = max(df.loc[idx, 'high'], price)
                df.loc[idx, 'low'] = min(df.loc[idx, 'low'], price)
                status = "UPDATED"
            else:
                # Add new candle
                new_row = pd.DataFrame({
                    'timestamp': [timestamp],
                    'open': [price],
                    'high': [price],
                    'low': [price],
                    'close': [price],
                    'volume': [0]
                })
                df = pd.concat([df, new_row], ignore_index=True)
                status = "NEW"
        else:
            # Create new database
            df = pd.DataFrame({
                'timestamp': [timestamp],
                'open': [price],
                'high': [price],
                'low': [price],
                'close': [price],
                'volume': [0]
            })
            status = "CREATED"
        
        # Save
        df.to_csv(PURE_DATA_FILE, index=False)
        
        print(f"[{status}] {timestamp.strftime('%Y-%m-%d %H:%M')} | Price: ${price:.2f} | Total: {len(df)} candles")
        
        return price, timestamp, len(df)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return None, None, 0


def rapid_collection(target_candles=300, delay_seconds=2):
    """
    Rapid data collection to build database quickly
    
    Args:
        target_candles: How many candles to collect (300 = enough for 4H indicators)
        delay_seconds: Delay between collections (default 2 seconds)
    """
    print("=" * 70)
    print("🔴 PURE LIVE DATA COLLECTOR - RAPID MODE")
    print("=" * 70)
    print(f"Target: {target_candles} candles")
    print(f"Delay: {delay_seconds} seconds")
    print(f"Source: livepriceofgold.com (NO Yahoo Finance)")
    print(f"Data file: {PURE_DATA_FILE}")
    print("-" * 70)
    
    # Check existing data
    if PURE_DATA_FILE.exists():
        df = pd.read_csv(PURE_DATA_FILE)
        existing = len(df)
        print(f"✓ Found existing data: {existing} candles")
        
        if existing >= target_candles:
            print(f"✓ Already have enough data ({existing}/{target_candles})")
            print("=" * 70)
            return
    else:
        existing = 0
        print(f"Starting fresh collection...")
    
    needed = target_candles - existing
    print(f"Need to collect: {needed} more candles")
    print(f"Estimated time: ~{(needed * delay_seconds) / 60:.1f} minutes")
    print("-" * 70)
    
    start_time = datetime.now()
    collected = 0
    
    try:
        while True:
            price, timestamp, total = collect_pure_live_price()
            
            if price is not None:
                collected += 1
                
                if total >= target_candles:
                    print("\n" + "=" * 70)
                    print(f"🎉 TARGET REACHED!")
                    print(f"   Total candles: {total}")
                    print(f"   Collected this session: {collected}")
                    elapsed = (datetime.now() - start_time).total_seconds()
                    print(f"   Time elapsed: {elapsed / 60:.1f} minutes")
                    print("=" * 70)
                    break
                
                # Progress update every 10 candles
                if collected % 10 == 0:
                    remaining = target_candles - total
                    eta_seconds = remaining * delay_seconds
                    print(f"   Progress: {total}/{target_candles} | Remaining: ~{eta_seconds/60:.1f}m")
            
            time.sleep(delay_seconds)
    
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print(f"⚠ STOPPED BY USER")
        print(f"   Collected this session: {collected}")
        print(f"   Total in database: {total if 'total' in locals() else 'Unknown'}")
        print("=" * 70)


def get_pure_data_stats():
    """Show statistics about pure collected data"""
    if not PURE_DATA_FILE.exists():
        print("❌ No data collected yet. Run collector first!")
        return None
    
    df = pd.read_csv(PURE_DATA_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print("=" * 70)
    print("📊 PURE LIVE DATA STATISTICS")
    print("=" * 70)
    print(f"Total candles: {len(df)}")
    print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    duration = df['timestamp'].max() - df['timestamp'].min()
    print(f"Duration: {duration.total_seconds() / 3600:.1f} hours")
    
    print(f"\nLatest price: ${df['close'].iloc[-1]:.2f}")
    print(f"Highest: ${df['high'].max():.2f}")
    print(f"Lowest: ${df['low'].min():.2f}")
    
    # Check if enough for indicators
    print(f"\n📈 Indicator Readiness:")
    
    required_1m = 300  # For building 4H candles with 200+ periods
    if len(df) >= required_1m:
        print(f"   ✅ Sufficient data ({len(df)} >= {required_1m})")
        
        # Estimate candles per timeframe
        print(f"\n   Estimated available candles:")
        print(f"   - 5-minute: ~{len(df) // 5} candles")
        print(f"   - 15-minute: ~{len(df) // 15} candles")
        print(f"   - 1-hour: ~{len(df) // 60} candles")
        print(f"   - 4-hour: ~{len(df) // 240} candles")
    else:
        print(f"   ⚠ Need more data ({len(df)}/{required_1m})")
        print(f"   Run: py pure_collector.py collect {required_1m}")
    
    print("=" * 70)
    
    return df


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "collect":
            target = int(sys.argv[2]) if len(sys.argv) > 2 else 300
            rapid_collection(target_candles=target, delay_seconds=2)
        elif command == "stats":
            get_pure_data_stats()
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  py pure_collector.py collect [target_candles]")
            print("  py pure_collector.py stats")
    else:
        print("PURE LIVE DATA COLLECTOR")
        print("=" * 70)
        print("Usage:")
        print("  py pure_collector.py collect 300    # Collect 300 candles")
        print("  py pure_collector.py stats          # Show statistics")
