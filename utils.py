import os
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
import yfinance as yf
from bs4 import BeautifulSoup


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CACHE_FILE = DATA_DIR / "xau_cache.csv"
CACHE_DURATION = timedelta(seconds=30)  # Refresh data every 30 seconds for real-time accuracy


class DataError(Exception):
    pass


def isMarketOpen(nowUtc: datetime) -> bool:
    """
    CME gold trading hours (UTC):
    - Daily break: 22:00 -> 23:00 (closed)
    - Weekly break: Friday 22:00 -> Sunday 23:00 (closed)
    """
    if nowUtc.tzinfo is None:
        nowUtc = nowUtc.replace(tzinfo=timezone.utc)
    else:
        nowUtc = nowUtc.astimezone(timezone.utc)

    weekday = nowUtc.weekday()  # Monday=0, Sunday=6
    hour = nowUtc.hour

    # Daily 1-hour break
    if 22 <= hour < 23:
        return False

    # Weekly break: Fri 22:00 through Sun 23:00
    if weekday == 4 and hour >= 22:
        return False
    if weekday in (5,):  # Saturday
        return False
    if weekday == 6 and hour < 23:  # Sunday before 23:00
        return False

    return True


def nextMarketOpen(nowUtc: datetime) -> datetime:
    """
    Compute next market open time in UTC based on CME hours.
    """
    if nowUtc.tzinfo is None:
        nowUtc = nowUtc.replace(tzinfo=timezone.utc)
    else:
        nowUtc = nowUtc.astimezone(timezone.utc)

    weekday = nowUtc.weekday()
    hour = nowUtc.hour
    minute = nowUtc.minute

    # If within daily break
    if 22 <= hour < 23 and weekday not in (5,):  # not Saturday
        return nowUtc.replace(hour=23, minute=0, second=0, microsecond=0)

    # If before daily break on an open day (Mon-Thu and Sun after 23:00)
    if weekday in (0, 1, 2, 3):  # Mon-Thu
        return nowUtc
    if weekday == 6 and hour >= 23:  # Sunday after reopen
        return nowUtc

    # Weekly reopen: Sunday 23:00 UTC
    days_ahead = (6 - weekday) % 7  # days until Sunday
    reopen = (nowUtc + timedelta(days=days_ahead)).replace(hour=23, minute=0, second=0, microsecond=0)
    if reopen <= nowUtc:
        reopen = reopen + timedelta(days=7)
    return reopen


def clean_yf_data(df):
    """Helper to clean Yahoo Finance data columns and timezone"""
    if df.empty:
        return df
        
    # Handle MultiIndex columns (Price, Ticker)
    if isinstance(df.columns, pd.MultiIndex):
        found_price_level = False
        for i in range(df.columns.nlevels):
            level_values = df.columns.get_level_values(i)
            if "Close" in level_values:
                df.columns = level_values
                found_price_level = True
                break
        
        if not found_price_level:
            df.columns = df.columns.droplevel(0)
            
    df.columns = [col.lower() for col in df.columns]
    
    # Ensure required columns
    required = ["open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in required):
        if "volume" not in df.columns:
            df["volume"] = 0
            
    df = df[["open", "high", "low", "close", "volume"]]
    
    # Convert to local time (UTC+3)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Etc/GMT-3")
        df.index = df.index.tz_localize(None)
        
    return df


def fetch_gold_historical_data(period="59d", interval="5m"):
    """
    Fetch historical gold data using yf.download()
    We use 5m interval to ensure accurate indicators for the 5m strategy.
    """
    import time
    import random
    import yfinance as yf
    
    # Try multiple tickers
    tickers = [
        ("XAUUSD=X", "Gold Spot"),
        ("GC=F", "Gold Futures"),
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
                    auto_adjust=True
                )
                
                if not hist.empty and len(hist) > 100:
                    print(f"✓ Successfully fetched {len(hist)} rows from {ticker_name}")
                    
                    # Clean main historical data
                    hist = clean_yf_data(hist)
                    
                    # PATCH: Fetch latest 1m data to ensure real-time accuracy for the last candle
                    if interval == "5m":
                        try:
                            print(f"  Fetching real-time 1m data from {ticker_name} to patch latest candle...")
                            rt_data = yf.download(
                                tickers=ticker_symbol,
                                period="1d",
                                interval="1m",
                                progress=False,
                                timeout=10,
                                auto_adjust=True
                            )
                            
                            if not rt_data.empty:
                                print(f"  ✓ Fetched {len(rt_data)} 1m rows. Last: {rt_data.index[-1]}")
                                rt_data = clean_yf_data(rt_data)
                                
                                # Resample 1m to 5m to get the latest incomplete candle(s) correctly formed
                                rt_5m = rt_data.resample("5T").agg({
                                    'open': 'first',
                                    'high': 'max',
                                    'low': 'min',
                                    'close': 'last',
                                    'volume': 'sum'
                                }).dropna()
                                
                                if not rt_5m.empty:
                                    # Update hist with rt_5m
                                    # Remove overlapping rows from hist
                                    hist = hist[~hist.index.isin(rt_5m.index)]
                                    # Append new/updated rows
                                    hist = pd.concat([hist, rt_5m]).sort_index()
                                    print(f"  ✓ Patched with real-time data. Latest candle: {hist.index[-1]}")
                                else:
                                    print("  ⚠ Resampled 1m data is empty")
                            else:
                                print("  ⚠ 1m data fetch returned empty")
                                    
                        except Exception as e:
                            print(f"  ⚠ Real-time patch warning: {e}")
                    
                    # Check freshness
                    last_time = hist.index[-1]
                    time_diff = datetime.now() - last_time
                    print(f"  📅 Current Candle Open Time: {last_time} (Time since open: {time_diff.total_seconds()/60:.1f} minutes)")
                    
                    # For 5m candles, the timestamp is the START of the 5-minute period.
                    # We allow up to 10 minutes lag.
                    if time_diff > timedelta(minutes=10):
                         msg = f"{ticker_name} data is stale (Last: {last_time}). Time diff: {time_diff.total_seconds()/60:.1f}m"
                         print(f"⚠ {msg}. Trying next ticker...")
                         last_error = msg
                         continue
                    
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
    Now enhanced with LIVE SPOT GOLD PRICE for real-time accuracy
    """
    # Try to use cache first
    cached = get_cached_data()
    if cached is not None and len(cached) > 0:
        cache_age = (datetime.now() - cached.index[-1].to_pydatetime()).total_seconds()
        
        # If cache is very fresh (< 30 seconds), use it as-is
        if cache_age < 30:
            print(f"✓ Using cached data ({len(cached)} rows) - Age: {cache_age:.0f}s - Latest: {cached.index[-1]}")
            return cached
    
    print("Fetching fresh gold data from Yahoo Finance...")
    
    # Fetch 59 days of 5-minute data (max allowed by YF is usually 60d for 5m)
    # This gives us enough data for 4H indicators (needs ~30-40 days)
    df = fetch_gold_historical_data(period="59d", interval="5m")
    
    print(f"✓ Fetched {len(df)} data points from Yahoo Finance")
    
    # ENHANCEMENT: Get LIVE SPOT GOLD PRICE and update latest candle
    try:
        live_price = get_live_gold_price_usa()
        current_time = datetime.now()
        
        # Round to nearest 5-minute interval for 5m candle
        current_5m = current_time.replace(second=0, microsecond=0)
        minutes = current_5m.minute
        rounded_minutes = (minutes // 5) * 5
        current_5m = current_5m.replace(minute=rounded_minutes)
        
        print(f"  🔴 LIVE PATCH: Using real-time Spot Gold price: ${live_price:.2f}")
        
        # Check if we already have a candle for current 5m period
        if current_5m in df.index:
            # Update the existing candle's close price and high/low if needed
            df.loc[current_5m, 'close'] = live_price
            df.loc[current_5m, 'high'] = max(df.loc[current_5m, 'high'], live_price)
            df.loc[current_5m, 'low'] = min(df.loc[current_5m, 'low'], live_price)
            print(f"  ✓ Updated existing 5m candle at {current_5m} with live price")
        else:
            # Create a new candle for the current 5m period
            new_candle = pd.DataFrame({
                'open': [live_price],
                'high': [live_price],
                'low': [live_price],
                'close': [live_price],
                'volume': [0]
            }, index=[current_5m])
            
            df = pd.concat([df, new_candle]).sort_index()
            print(f"  ✓ Created new 5m candle at {current_5m} with live price")
        
    except DataError as e:
        print(f"  ⚠ Could not fetch live price: {e}")
        print(f"  → Continuing with Yahoo Finance data only")
    except Exception as e:
        print(f"  ⚠ Unexpected error getting live price: {e}")
    
    # Cache the enhanced data
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


def get_live_gold_price_usa():
    """
    Fetch live Spot Gold price per ounce in USD from livepriceofgold.com.
    Includes cache-busting and a JSON API fallback to avoid stale first-read values.
    """
    import re

    url = "https://www.livepriceofgold.com/usa-gold-price.html"
    goldprice_api = "https://data-asg.goldprice.org/dbXRates/USD"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    try:
        print(f"Scraping live Spot Gold price from {url}...")
        response = requests.get(
            url,
            params={"t": int(time.time())},
            timeout=10,
            headers=headers,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        xauusd_cell = soup.find("td", {"data-price": "XAUUSD"})
        if xauusd_cell:
            price_text = xauusd_cell.get_text(strip=True).replace(",", "").replace("$", "")
            try:
                price = float(price_text)
                print(f"Live Spot Gold price (XAUUSD cell): ${price:.2f} USD/oz")
                return price
            except ValueError:
                pass

        page_text = soup.get_text()

        spot_gold_pattern = re.search(
            r"SPOT\s+GOLD[^0-9]*([0-9,]+\.[0-9]{2})", page_text, re.IGNORECASE
        )
        if spot_gold_pattern:
            price_text = spot_gold_pattern.group(1).replace(",", "")
            price = float(price_text)
            print(f"Live Spot Gold price (SPOT GOLD pattern): ${price:.2f} USD/oz")
            return price

        title = soup.find("title")
        if title:
            title_price = re.search(r"[\$]?\s*([4-5],?\d{3}\.\d{2})", title.get_text())
            if title_price:
                price_text = title_price.group(1).replace(",", "")
                price = float(price_text)
                print(f"Live Spot Gold price (title): ${price:.2f} USD/oz")
                return price

        all_prices = re.findall(r"([4-5],?\d{3}\.\d{2})", page_text)
        if all_prices:
            price_text = all_prices[0].replace(",", "")
            price = float(price_text)
            print(f"Live Spot Gold price (fallback): ${price:.2f} USD/oz")
            return price

        print("Primary page did not yield a price. Trying goldprice API...")
        api_resp = requests.get(goldprice_api, timeout=10, headers=headers)
        api_resp.raise_for_status()
        data = api_resp.json()
        items = data.get("items", [])
        if items:
            api_price = float(items[0].get("xauPrice"))
            print(f"Live Spot Gold price (goldprice API): ${api_price:.2f} USD/oz")
            return api_price

        raise DataError("Could not find Spot Gold price in page content")

    except requests.RequestException as e:
        raise DataError(f"Network error fetching live gold price: {e}")
    except Exception as e:
        raise DataError(f"Error parsing live gold price: {e}")
