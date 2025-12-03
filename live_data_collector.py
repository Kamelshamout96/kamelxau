"""
Live Gold Data Collector
========================
Collects 1-minute candles from livepriceofgold.com and stores them in Firestore.
This replaces the previous CSV-based storage to avoid losing data on deploy/restart.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account

from utils import DataError, get_live_gold_price_usa

# Firestore setup
FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID")
FIRESTORE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
_db = None  # cached Firestore client

# Legacy constants retained for downstream imports (not used for storage anymore)
LIVE_DATA_DIR = Path("data")
LIVE_DATA_DIR.mkdir(exist_ok=True)
LIVE_DATA_FILE = LIVE_DATA_DIR / "live_gold_data.csv"
# Firestore collection (fixed name)
DAY_COLLECTION = "live_candles"


def _get_db():
    """Create or return a cached Firestore client."""
    global _db
    if _db is not None:
        return _db

    if not FIRESTORE_CREDS_JSON:
        raise DataError("Missing GOOGLE_CREDENTIALS_JSON environment variable for Firestore.")

    try:
        info = json.loads(FIRESTORE_CREDS_JSON)
        creds = service_account.Credentials.from_service_account_info(info)
        _db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=creds)
        return _db
    except Exception as exc:
        raise DataError(f"Failed to initialize Firestore client: {exc}")


def _day_collection(timestamp: datetime):
    """Return the subcollection for the given day (doc per day)."""
    day_key = timestamp.date().isoformat()  # YYYY-MM-DD
    db = _get_db()
    day_doc = db.collection(DAY_COLLECTION).document(day_key)
    # Ensure day doc exists with minimal metadata
    day_doc.set({"day": day_key}, merge=True)
    return day_doc.collection("candles")


def append_live_price():
    """
    Fetch current live gold price and upsert it into Firestore as a 1-minute candle.
    """
    try:
        price = get_live_gold_price_usa()
        current_time = datetime.now()
        timestamp = current_time.replace(microsecond=0)  # minute resolution

        doc_ref = _day_collection(timestamp).document(timestamp.isoformat())
        snap = doc_ref.get()

        if snap.exists:
            data = snap.to_dict() or {}
            updated = {
                "timestamp": data.get("timestamp", timestamp.isoformat()),
                "open": data.get("open", price),
                "high": max(data.get("high", price), price),
                "low": min(data.get("low", price), price),
                "close": price,
                "volume": data.get("volume", 0),
            }
            status = "Updated"
        else:
            updated = {
                "timestamp": timestamp.isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0,
            }
            status = "Created"

        doc_ref.set(updated, merge=True)
        print(f"[OK] {status} 1m candle at {timestamp}: ${price:.2f}")
        return price, timestamp

    except Exception as e:
        print(f"[ERR] Error collecting live price: {e}")
        return None, None


def get_live_collected_data(limit_per_day: int = 2000, days_back: int = 3):
    """
    Load collected live data from Firestore.

    Args:
        limit_per_day: Max documents to pull per day (ordered oldest->newest).
        days_back: How many days (including today) to pull.
    """
    rows = []
    today = datetime.now().date()

    try:
        for i in range(days_back):
            day = today - timedelta(days=i)
            col = (
                _get_db()
                .collection(DAY_COLLECTION)
                .document(day.isoformat())
                .collection("candles")
            )
            docs = col.order_by("timestamp").limit(limit_per_day).stream()
            rows.extend(d.to_dict() for d in docs)
    except Exception as exc:
        raise DataError(f"Failed to load data from Firestore: {exc}")

    if not rows:
        raise DataError("No live data collected yet. Run collector first.")

    df = pd.DataFrame(rows)
    if df.empty:
        raise DataError("Live data is empty. Collect at least a few 1m samples first.")

    if "timestamp" not in df.columns:
        raise DataError("Timestamp column is missing in Firestore data.")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Drop obvious outlier price spikes only (keep zero-volume rows allowed by design)
    df = df[df["close"] < 1_000_000]

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
