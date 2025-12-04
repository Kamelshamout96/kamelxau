"""
Live Gold Data Collector
========================
Collects 1-minute candles from livepriceofgold.com and stores them in Google Sheets.
This replaces the previous CSV-based storage to avoid losing data on deploy/restart.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from utils import DataError, get_live_gold_price_usa

# Simple in-process cache to reduce external reads (Sheets API quotas)
CACHE_TTL_SECONDS = 300  # 5 minutes
_data_cache = {}  # key: (limit, days_back) -> {"ts": float, "df": DataFrame}

# Google Sheets setup
SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID") or os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or str(Path("data") / "blissful-shore-480201-b1-6ec756a16a9e.json")
WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKSHEET", "live_candles")
_sheet = None  # cached worksheet client
SHEETS_ID_FILE = Path("data/google_sheet_id.json")

# Legacy constants retained for downstream imports (not used for storage anymore)
LIVE_DATA_DIR = Path("data")
LIVE_DATA_DIR.mkdir(exist_ok=True)
LIVE_DATA_FILE = LIVE_DATA_DIR / "live_gold_data.csv"


def _get_sheet():
    """Create or return a cached Google Sheet worksheet."""
    global _sheet, SHEETS_ID
    if _sheet is not None:
        return _sheet

    if not SHEETS_ID:
        # Optional fallback: read from JSON file data/google_sheet_id.json
        if SHEETS_ID_FILE.exists():
            try:
                sheet_info = json.loads(SHEETS_ID_FILE.read_text(encoding="utf-8"))
                SHEETS_ID = sheet_info.get("GOOGLE_SHEETS_ID") or sheet_info.get("sheet_id") or sheet_info.get("id")
            except Exception as exc:
                raise DataError(f"Failed to read Google Sheets ID from {SHEETS_ID_FILE}: {exc}")
    if not SHEETS_ID:
        raise DataError("❌ Missing GOOGLE_SHEETS_ID (or GOOGLE_SHEET_ID) environment variable, and no sheet id found in data/google_sheet_id.json.")

    info = None
    cred_path = None
    if GOOGLE_CREDS_JSON:
        try:
            info = json.loads(GOOGLE_CREDS_JSON.strip())
        except Exception as exc:
            raise DataError(f"Invalid JSON in GOOGLE_CREDENTIALS_JSON: {exc}")
    else:
        if GOOGLE_CREDS_FILE:
            cred_path = Path(GOOGLE_CREDS_FILE)
        else:
            default_path = Path("data/blissful-shore-480201-b1-6ec756a16a9e.json")
            cred_path = default_path if default_path.exists() else None
        if cred_path:
            if not cred_path.exists():
                raise DataError(f"Google credentials file not found at {cred_path}")
            raw = cred_path.read_text(encoding="utf-8-sig").strip()
            if not raw:
                raise DataError(f"Credentials file {cred_path} is empty")
            info = json.loads(raw)
    if info is None:
        raise DataError(
            "Missing Google credentials. Set GOOGLE_CREDENTIALS_JSON or "
            "GOOGLE_CREDENTIALS_FILE/GOOGLE_APPLICATION_CREDENTIALS, or place "
            "data/firebase_creds.json with your service account JSON."
        )

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEETS_ID)
        try:
            ws = sh.worksheet(WORKSHEET_NAME)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="10")
        headers = ["timestamp", "open", "high", "low", "close", "volume"]
        current = [c.lower() for c in ws.row_values(1)]
        if current != headers:
            ws.update("A1:F1", [headers])
        _sheet = ws
        return _sheet
    except Exception as exc:
        raise DataError(f"Failed to initialize Google Sheets client: {exc}")


def append_live_price():
    """
    Fetch current live gold price and append it into Sheets as a 1-minute candle.
    """
    try:
        price = get_live_gold_price_usa()
        # Use Riyadh local time for storage (tz-aware) then store ISO with offset
        current_time = datetime.now(ZoneInfo("Asia/Riyadh"))
        timestamp = current_time.replace(microsecond=0)  # minute resolution

        ws = _get_sheet()
        ws.append_row(
            [
                timestamp.isoformat(),
                price,
                price,
                price,
                price,
                0,
            ],
            value_input_option="RAW",
        )
        print(f"[OK] Appended 1m candle at {timestamp}: ${price:.2f}")
        _data_cache.clear()
        return price, timestamp

    except Exception as e:
        print(f"[ERR] Error collecting live price: {e}")
        return None, None


def get_live_collected_data(limit: int = 50000, days_back: int = 40):
    """
    Load collected live data from Sheets.

    Args:
        limit: Max total rows to return (latest). Defaults to ~50k to cover 4H EMA200.
        days_back: Ignored for Sheets (kept for compatibility).
    """
    cache_key = (limit, days_back)
    now_ts = time.time()
    cached = _data_cache.get(cache_key)
    if cached and now_ts - cached["ts"] < CACHE_TTL_SECONDS:
        return cached["df"].copy()

    try:
        ws = _get_sheet()
        rows = ws.get_all_records()
    except Exception as exc:
        raise DataError(f"Failed to load data from Sheets: {exc}")

    if not rows:
        raise DataError("No live data collected yet. Run collector first.")

    df = pd.DataFrame(rows)
    if df.empty:
        raise DataError("Live data is empty. Collect at least a few 1m samples first.")

    if "timestamp" not in df.columns:
        raise DataError("Timestamp column is missing in Firestore data.")

    # Robust ISO parsing with timezone support (+03:00). Coerce bad rows out.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="ISO8601", errors="coerce", utc=True
    )
    df = df.dropna(subset=["timestamp"])
    # Normalize to Riyadh tz for consistency
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Riyadh")

    df = df.set_index("timestamp").sort_index()
    # Keep only the latest {limit} rows overall
    if limit and len(df) > limit:
        df = df.tail(limit)
    df = df[~df.index.duplicated(keep="last")]

    # Cache result
    _data_cache[cache_key] = {"ts": now_ts, "df": df}

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
