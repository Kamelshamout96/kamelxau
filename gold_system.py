"""
CLEAN GOLD SCRAPER & COLLECTOR
===============================
Simple, clean system for collecting live gold prices
NO Yahoo Finance - 100% Web Scraping
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import time
import requests
from bs4 import BeautifulSoup


# Configuration
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DATA_FILE = DATA_DIR / "gold_prices.csv"


def get_live_price():
    """Get current spot gold price - SIMPLE & CLEAN"""
    url = "https://www.livepriceofgold.com/usa-gold-price.html"
    
    try:
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Target XAUUSD cell
        cell = soup.find('td', {'data-price': 'XAUUSD'})
        if cell:
            price_text = cell.get_text(strip=True).replace(',', '').replace('$', '')
            price = float(price_text)
            return price
        
        # Fallback: pattern search
        import re
        text = soup.get_text()
        pattern = re.search(r'SPOT\s+GOLD[^0-9]*([0-9,]+\.[0-9]{2})', text, re.IGNORECASE)
        if pattern:
            price = float(pattern.group(1).replace(',', ''))
            return price
        
        return None
        
    except Exception as e:
        print(f"  ✗ Error fetching price: {e}")
        return None


def save_price(price, timestamp):
    """Save price to CSV - SIMPLE"""
    
    # Create or load data
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    else:
        df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Check if this minute already exists
    existing = df[df['timestamp'] == timestamp]
    
    if not existing.empty:
        # Update existing
        idx = existing.index[0]
        df.loc[idx, 'close'] = price
        df.loc[idx, 'high'] = max(df.loc[idx, 'high'], price)
        df.loc[idx, 'low'] = min(df.loc[idx, 'low'], price)
        status = "UPDATED"
    else:
        # Add new
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
    
    # Save
    df.to_csv(DATA_FILE, index=False)
    
    return status, len(df)


def collect(target=300, interval=60):
    """
    Collect prices
    
    Args:
        target: How many 1-minute candles to collect
        interval: Seconds between collections (default 60 = 1 minute)
    """
    print("=" * 70)
    print("🔴 GOLD PRICE COLLECTOR - PURE SCRAPING")
    print("=" * 70)
    print(f"Target: {target} candles")
    print(f"Interval: Every minute (on the minute)")
    print(f"Data: {DATA_FILE}")
    print("-" * 70)
    
    collected = 0
    
    try:
        while True:
            # Get current time
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)
            
            # Fetch price
            print(f"\n[{now.strftime('%H:%M:%S')}] Fetching price...", end=" ")
            price = get_live_price()
            
            if price:
                # Save
                status, total = save_price(price, current_minute)
                print(f"✓ ${price:.2f} [{status}] Total: {total}")
                
                collected += 1
                
                # Check if target reached
                if total >= target:
                    print("\n" + "=" * 70)
                    print(f"🎉 TARGET REACHED! {total} candles")
                    print("=" * 70)
                    break
            else:
                print("✗ Failed")
            
            # Wait until next minute
            # Calculate seconds until next minute (00 seconds)
            next_minute = (current_minute + pd.Timedelta(minutes=1))
            seconds_to_wait = (next_minute - now).total_seconds()
            
            if seconds_to_wait > 0:
                print(f"  ⏳ Next collection at {next_minute.strftime('%H:%M')} ({int(seconds_to_wait)}s)...")
                time.sleep(seconds_to_wait)
    
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print(f"⚠ STOPPED - Collected {collected} this session")
        print("=" * 70)


def stats():
    """Show data statistics"""
    if not DATA_FILE.exists():
        print("❌ No data yet. Run: py gold_system.py collect")
        return
    
    df = pd.read_csv(DATA_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print("=" * 70)
    print("📊 DATA STATISTICS")
    print("=" * 70)
    print(f"Total candles: {len(df)}")
    print(f"Time range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"Latest price: ${df['close'].iloc[-1]:.2f}")
    print(f"Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
    print(f"\nUnique prices: {df['close'].nunique()}")
    
    # Show last 5
    print(f"\nLast 5 prices:")
    print(df[['timestamp', 'close']].tail(5).to_string(index=False))
    print("=" * 70)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  py gold_system.py collect [target]  - Collect prices")
        print("  py gold_system.py stats             - Show statistics")
        print("\nExample:")
        print("  py gold_system.py collect 300")
    else:
        cmd = sys.argv[1].lower()
        
        if cmd == "collect":
            target = int(sys.argv[2]) if len(sys.argv) > 2 else 300
            collect(target=target, interval=60)
        
        elif cmd == "stats":
            stats()
        
        else:
            print(f"Unknown command: {cmd}")
