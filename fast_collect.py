"""
Fast Data Collection Script
============================
Collects 60+ data points in ~5 minutes by sampling every 5 seconds
This is for TESTING ONLY - normally you'd collect every 60 seconds
"""

from live_data_collector import append_live_price, get_collection_stats
import time
from datetime import datetime, timedelta

print("=" * 70)
print("FAST DATA COLLECTION (Testing Mode)")
print("=" * 70)
print("Collecting 60 samples every 5 seconds (~5 minutes total)")
print("This simulates 1 hour of real data for testing purposes")
print("-" * 70)

start_time = datetime.now()
samples_collected = 0
target_samples = 60

try:
    for i in range(target_samples):
        print(f"\n[{i+1}/{target_samples}] ", end="")
        price, timestamp = append_live_price()
        
        if price:
            samples_collected += 1
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining = (target_samples - i - 1) * 5
            print(f"  Elapsed: {elapsed:.0f}s | Remaining: ~{remaining:.0f}s")
        
        if i < target_samples - 1:  # Don't sleep on last iteration
            time.sleep(5)  # Wait 5 seconds between samples
    
    print("\n" + "=" * 70)
    print(f"✓ COLLECTION COMPLETE")
    print(f"  Total samples: {samples_collected}")
    print(f"  Total time: {(datetime.now() - start_time).total_seconds():.0f} seconds")
    print("=" * 70)
    
    # Show stats
    print("\n")
    get_collection_stats()
    
except KeyboardInterrupt:
    print("\n" + "=" * 70)
    print(f"⚠ STOPPED BY USER - {samples_collected} samples collected")
    print("=" * 70)
except Exception as e:
    print(f"\n✗ ERROR: {e}")
