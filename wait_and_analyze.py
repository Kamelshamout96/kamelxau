"""
🔴 QUICK TEST - Pure Live System
==================================
This script waits for data collection to complete, then analyzes
"""

import time
from pathlib import Path
import pandas as pd

PURE_DATA_FILE = Path("data") / "pure_live_gold.csv"
TARGET_CANDLES = 300

print("=" * 70)
print("🔴 WAITING FOR DATA COLLECTION...")
print("=" * 70)

while True:
    if PURE_DATA_FILE.exists():
        df = pd.read_csv(PURE_DATA_FILE)
        current = len(df)
        
        print(f"\r📊 Current: {current}/{TARGET_CANDLES} candles | ", end="")
        
        if current >= TARGET_CANDLES:
            print(f"\n\n✅ TARGET REACHED! {current} candles collected")
            print("=" * 70)
            print("\n🚀 Running analysis...\n")
            
            # Run analyzer
            import subprocess
            subprocess.run(["py", "pure_analyzer.py"])
            break
        else:
            remaining = TARGET_CANDLES - current
            eta = remaining * 2 / 60  # 2 seconds per candle
            print(f"ETA: ~{eta:.1f} minutes", end="")
    else:
        print(f"\r⏳ Waiting for collector to start...", end="")
    
    time.sleep(5)  # Check every 5 seconds
