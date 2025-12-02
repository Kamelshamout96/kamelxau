import pandas as pd
from pathlib import Path

data_file = Path("data/pure_live_gold.csv")

if data_file.exists():
    df = pd.read_csv(data_file)
    
    print("=" * 60)
    print("📊 PURE LIVE DATA STATUS")
    print("=" * 60)
    print(f"Total candles collected: {len(df)}")
    print(f"\nFirst 5 prices:")
    print(df[['timestamp', 'close']].head(5).to_string(index=False))
    print(f"\nLast 5 prices:")
    print(df[['timestamp', 'close']].tail(5).to_string(index=False))
    
    # Check if prices are changing
    unique_prices = df['close'].nunique()
    print(f"\nUnique prices: {unique_prices}")
    
    if unique_prices > 1:
        price_range = df['close'].max() - df['close'].min()
        print(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f} (${price_range:.2f})")
        print(f"\n✅ PRICES ARE CHANGING - Scraper is working correctly!")
    else:
        print(f"\n⚠ WARNING: All prices are the same ({df['close'].iloc[0]:.2f})")
    
    print("=" * 60)
else:
    print("❌ No data file found!")
