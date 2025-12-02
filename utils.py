import os
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CACHE_FILE = DATA_DIR / "xau_cache.csv"
CACHE_DURATION = timedelta(minutes=5)  # Refresh data every 5 minutes


class DataError(Exception):
    pass


def fetch_gold_historical_data(period="30d", interval="1m"):
    """
    Fetch historical gold data from Yahoo Finance (Gold Futures: GC=F)
    
    Args:
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
    
    Returns:
        DataFrame with OHLCV data
    """
    try:
        # Download gold futures data (GC=F) or spot gold (XAUUSD=X)
        # Using GC=F (Gold Futures) as it has better intraday data
        ticker = yf.Ticker("GC=F")
        
        # Get historical data
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
            raise DataError("No data received from Yahoo Finance")
        
        # Rename columns to lowercase for consistency
        hist.columns = [col.lower() for col in hist.columns]
        
        # Keep only OHLCV
        hist = hist[["open", "high", "low", "close", "volume"]]
        
        # Remove timezone info and convert to UTC
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        
        return hist
        
    except Exception as e:
        raise DataError(f"Failed to fetch gold data: {str(e)}")


def get_cached_data():
    """Load cached data if it exists and is fresh"""
    if not CACHE_FILE.exists():
        return None
    
    try:
        df = pd.read_csv(CACHE_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        
        # Check cache age
        cache_age = datetime.now() - df.index[-1].to_pydatetime()
        if cache_age > CACHE_DURATION:
            return None
        
        return df
    except:
        return None


def save_cache(df):
    """Save data to cache"""
    df = df.copy().sort_index()
    df.reset_index().rename(columns={"index": "timestamp"}).to_csv(CACHE_FILE, index=False)


def update_history():
    """
    Fetch fresh historical data or return cached data
    This will work on the FIRST call - no need to accumulate data!
    """
    # Try to use cache first
    cached = get_cached_data()
    if cached is not None and len(cached) > 0:
        print(f"✓ Using cached data ({len(cached)} rows)")
        return cached
    
    print("Fetching fresh gold data from Yahoo Finance...")
    
    # Fetch 30 days of 1-minute data to ensure we have enough for all timeframes
    df = fetch_gold_historical_data(period="30d", interval="1m")
    
    print(f"✓ Fetched {len(df)} data points")
    
    # Cache the data
    save_cache(df)
    
    return df


def to_candles(df, rule):
    """
    Resample data to the specified timeframe
    """
    if len(df) < 10:
        raise DataError(f"Not enough raw data: {len(df)} rows")

    ohlc = df["close"].resample(rule).ohlc()
    ohlc["high"] = df["high"].resample(rule).max()
    ohlc["low"] = df["low"].resample(rule).min()
    ohlc["open"] = df["open"].resample(rule).first()
    ohlc["volume"] = df["volume"].resample(rule).sum()

    result = ohlc.dropna()
    
    # Check if we have enough candles for indicators
    if len(result) < 250:
        raise DataError(
            f"Not enough candles after resampling to {rule}: {len(result)}/250. "
            f"Try fetching more historical data or use a shorter indicator period."
        )
    
    return result


def send_telegram(token, chat_id, msg):
    """Send message via Telegram using direct API call"""
    if not token or not chat_id:
        print("Warning: Telegram token or chat_id not configured")
        return
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✓ Telegram message sent successfully")
    except Exception as e:
        print(f"✗ Failed to send Telegram message: {e}")
