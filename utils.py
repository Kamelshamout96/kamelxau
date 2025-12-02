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


def fetch_gold_historical_data(period="30d", interval="1h"):
    """
    Fetch historical gold data using yf.download() which is more robust
    """
    import time
    import random
    import yfinance as yf
    
    # Try multiple tickers
    tickers = [
        ("GC=F", "Gold Futures"),
        ("XAUUSD=X", "Gold Spot"),
    ]
    
    last_error = None
    
    for ticker_symbol, ticker_name in tickers:
        for attempt in range(3):
            try:
                print(f"Attempting fetch from {ticker_name} ({ticker_symbol})... Attempt {attempt + 1}/3")
                
                # Use yf.download which handles sessions internally better than Ticker.history
                hist = yf.download(
                    tickers=ticker_symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    timeout=20,
                    auto_adjust=True  # Adjusts for splits/dividends automatically
                )
                
                if not hist.empty and len(hist) > 100:
                    print(f"✓ Successfully fetched {len(hist)} rows from {ticker_name}")
                    
                    # Clean up data
                    # yf.download might return MultiIndex columns.
                    # Recent versions often return (Price, Ticker) -> Level 0 is Price.
                    # Older versions or different settings might return (Ticker, Price) -> Level 1 is Price.
                    if isinstance(hist.columns, pd.MultiIndex):
                        # Try to find the level containing 'Close'
                        found_price_level = False
                        for i in range(hist.columns.nlevels):
                            level_values = hist.columns.get_level_values(i)
                            if "Close" in level_values:
                                hist.columns = level_values
                                found_price_level = True
                                break
                        
                        # Fallback if 'Close' not found (unlikely)
                        if not found_price_level:
                            hist.columns = hist.columns.droplevel(0)
                        
                    hist.columns = [col.lower() for col in hist.columns]
                    
                    # Ensure we have required columns
                    required = ["open", "high", "low", "close", "volume"]
                    if not all(col in hist.columns for col in required):
                        # Sometimes volume is missing for forex/spot
                        if "volume" not in hist.columns:
                            hist["volume"] = 0
                    
                    hist = hist[["open", "high", "low", "close", "volume"]]
                    
                    # Remove timezone info
                    if hist.index.tz is not None:
                        hist.index = hist.index.tz_localize(None)
                    
                    return hist
                
                print(f"⚠ {ticker_name} returned empty/insufficient data")
                
            except Exception as e:
                last_error = str(e)
                print(f"✗ Error: {last_error}")
                
                # Randomized exponential backoff
                if "Too Many Requests" in last_error or "429" in last_error:
                    sleep_time = (attempt + 1) * 5 + random.uniform(1, 3)
                    print(f"  Rate limited. Sleeping {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    time.sleep(2)
    
    # If we get here, all attempts failed
    raise DataError(
        f"Unable to fetch data. Last error: {last_error}\n"
        "Try waiting a few minutes or use a different network."
    )


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
    
    # Fetch 60 days of 1-hour data to ensure enough candles for 4H timeframe (needs 200 candles)
    df = fetch_gold_historical_data(period="60d", interval="1h")
    
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
    
    # Check if we have enough candles for indicators (need 200 for EMA200)
    if len(result) < 200:
        raise DataError(
            f"Not enough candles after resampling to {rule}: {len(result)}/200. "
            f"Try fetching more historical data."
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
