"""
Live Gold Data Collector
========================
This module collects live spot gold prices at regular intervals (1-minute)
and stores them in a database for historical analysis.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
from utils import get_live_gold_price_usa, DataError


# Data storage
LIVE_DATA_DIR = Path("data")
LIVE_DATA_DIR.mkdir(exist_ok=True)
LIVE_DATA_FILE = LIVE_DATA_DIR / "live_gold_data.csv"


def append_live_price():
    """
    Fetch current live gold price and append it to the database
    Creates 1-minute candles
    """
    try:
        # Get live price
        price = get_live_gold_price_usa()
        current_time = datetime.now()
        
        # Round to current minute
        timestamp = current_time.replace(microsecond=0)
        
        # Create new data point (1-minute candle)
        new_data = pd.DataFrame({
            'timestamp': [timestamp],
            'open': [price],
            'high': [price],
            'low': [price],
            'close': [price],
            'volume': [0]
        })
        
        # Load existing data or create new
        if LIVE_DATA_FILE.exists():
            df = pd.read_csv(LIVE_DATA_FILE)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Check if we already have this minute
            existing = df[df['timestamp'] == timestamp]
            if not existing.empty:
                # Update existing candle (update high/low/close)
                idx = existing.index[0]
                df.loc[idx, 'close'] = price
                df.loc[idx, 'high'] = max(df.loc[idx, 'high'], price)
                df.loc[idx, 'low'] = min(df.loc[idx, 'low'], price)
                print(f"✓ Updated 1m candle at {timestamp}: ${price:.2f}")
            else:
                # Append new candle
                df = pd.concat([df, new_data], ignore_index=True)
                print(f"✓ Added new 1m candle at {timestamp}: ${price:.2f}")
        else:
            # First time - create new file
            df = new_data
            print(f"✓ Created new database with 1m candle at {timestamp}: ${price:.2f}")
        
        # Save to CSV
        df.to_csv(LIVE_DATA_FILE, index=False)
        
        return price, timestamp
        
    except Exception as e:
        print(f"✗ Error collecting live price: {e}")
        return None, None


def get_live_collected_data():
    """
    Load all collected live data
    Returns DataFrame with 1-minute candles
    """
    if not LIVE_DATA_FILE.exists():
        raise DataError("No live data collected yet. Run collector first.")
    if LIVE_DATA_FILE.stat().st_size == 0:
        raise DataError("Live data file is empty. Collect at least a few 1m samples first.")

    df = pd.read_csv(LIVE_DATA_FILE)
    if df.empty:
        raise DataError("Live data file is empty. Collect at least a few 1m samples first.")

    # Normalize timestamp index and drop duplicates to keep resampling stable
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DataError("Timestamp column is missing or invalid.")

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Drop obvious bad/outlier rows (zero volume or extreme price spikes)
    if "volume" in df.columns:
        df = df[df["volume"] > 0]
    df = df[df["close"] < 3000]

    return df


def build_timeframe_candles(df_1m, timeframe):
    """
    Build candles for specified timeframe from 1-minute data
    
    Args:
        df_1m: DataFrame with 1-minute candles
        timeframe: '5min', '15min', '60min', '240min', '1D'
    """
    if df_1m is None or len(df_1m) == 0:
        raise DataError("No 1m data available to resample.")

    # Ensure datetime index
    if not isinstance(df_1m.index, pd.DatetimeIndex):
        if "timestamp" in df_1m.columns:
            df_1m = df_1m.copy()
            df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"])
            df_1m = df_1m.set_index("timestamp")
        else:
            raise DataError("Data must have a DatetimeIndex or a 'timestamp' column.")

    df_1m = df_1m.sort_index()
    df_1m = df_1m[~df_1m.index.duplicated(keep="last")]

    if len(df_1m) < 10:
        raise DataError(f"Not enough 1m data: {len(df_1m)} rows")
    
    # normalize deprecated alias
    if isinstance(timeframe, str) and timeframe.endswith("T"):
        timeframe = timeframe[:-1] + "min"
    
    # Resample to desired timeframe
    candles = df_1m.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    if candles.empty:
        raise DataError(f"No candles produced when resampling to {timeframe}. Need more 1m data.")

    return candles


def collect_continuously(duration_minutes=60, interval_seconds=60):
    """
    Collect live prices continuously for specified duration
    
    Args:
        duration_minutes: How long to collect (default 60 minutes = 1 hour)
        interval_seconds: How often to collect (default 60 seconds = 1 minute)
    """
    print("=" * 70)
    print("LIVE GOLD PRICE COLLECTOR - STARTING")
    print("=" * 70)
    print(f"Duration: {duration_minutes} minutes")
    print(f"Interval: {interval_seconds} seconds")
    print(f"Data will be saved to: {LIVE_DATA_FILE}")
    print("-" * 70)
    
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    collection_count = 0
    
    try:
        while datetime.now() < end_time:
            price, timestamp = append_live_price()
            
            if price is not None:
                collection_count += 1
                remaining = (end_time - datetime.now()).total_seconds() / 60
                print(f"  [{collection_count}] Remaining: {remaining:.1f} minutes")
            
            # Wait for next interval
            time.sleep(interval_seconds)
        
        print("\n" + "=" * 70)
        print(f"✓ COLLECTION COMPLETE - {collection_count} data points collected")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print(f"⚠ COLLECTION STOPPED BY USER - {collection_count} data points collected")
        print("=" * 70)


def get_collection_stats():
    """Get statistics about collected data"""
    try:
        df = get_live_collected_data()
        
        print("=" * 70)
        print("LIVE DATA COLLECTION STATISTICS")
        print("=" * 70)
        print(f"Total 1-minute candles: {len(df)}")
        print(f"Time range: {df.index[0]} to {df.index[-1]}")
        print(f"Duration: {(df.index[-1] - df.index[0]).total_seconds() / 3600:.1f} hours")
        print(f"Latest price: ${df['close'].iloc[-1]:.2f}")
        print(f"24h High: ${df['high'].max():.2f}")
        print(f"24h Low: ${df['low'].min():.2f}")
        
        # Calculate how many candles we can build for each timeframe
        print("\nTimeframe candles available:")
        for tf_name, tf_rule in [("5-minute", "5min"), ("15-minute", "15min"), 
                                   ("1-hour", "60min"), ("4-hour", "240min"), ("Daily", "1D")]:
            try:
                candles = build_timeframe_candles(df, tf_rule)
                print(f"  {tf_name}: {len(candles)} candles")
            except:
                print(f"  {tf_name}: Not enough data")
        
        print("=" * 70)
        
        return df
        
    except DataError as e:
        print(f"No data available: {e}")
        return None


if __name__ == "__main__":
    # Quick test
    print("Testing live data collection...")
    print("-" * 70)
    
    # Collect one sample
    append_live_price()
    
    # Show stats if data exists
    get_collection_stats()
