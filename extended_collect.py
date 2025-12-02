"""
Extended Data Collection Script
================================
Collects 250+ data points to ensure we have enough for all indicators
Collects every 3 seconds for ~12 minutes
"""

from live_data_collector import append_live_price, get_collection_stats
import time
from datetime import datetime

print("=" * 70)
print("EXTENDED DATA COLLECTION")
print("=" * 70)
print("Collecting 250 samples every 3 seconds (~12 minutes total)")
print("This provides enough data for accurate indicator calculation")
print("-" * 70)

start_time = datetime.now()
samples_collected = 0
target_samples = 250

try:
    for i in range(target_samples):
        if i % 10 == 0:  # Print every 10 samples
            print(f"\n[{i+1}/{target_samples}] ", end="")
            
        price, timestamp = append_live_price()
        
        if price:
            samples_collected += 1
            if i % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining = (target_samples - i - 1) * 3
                print(f"Price: ${price:.2f} | Elapsed: {elapsed:.0f}s | Remaining: ~{remaining:.0f}s")
        
        if i < target_samples - 1:
            time.sleep(3)  # Wait 3 seconds
    
    print("\n" + "=" * 70)
    print(f"✓ COLLECTION COMPLETE")
    print(f"  Total samples: {samples_collected}")
    print(f"  Total time: {(datetime.now() - start_time).total_seconds()/60:.1f} minutes")
    print("=" * 70)
    
    # Show stats
    print("\n")
    get_collection_stats()
    
except KeyboardInterrupt:
    print("\n" + "=" * 70)
    print(f"⚠ STOPPED BY USER - {samples_collected} samples collected")
    print("=" * 70)
    get_collection_stats()
except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
