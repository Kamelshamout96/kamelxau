from utils import update_history
import pandas as pd
from datetime import datetime

print("Fetching data with Real-Time Patch (XAUUSD=X Priority)...")
try:
    df = update_history()
    print("\nLast 5 rows of data:")
    print(df.tail(5))
    print("\nLatest timestamp:", df.index[-1])
    print(f"Current System Time: {datetime.now()}")
    
    # Check if we have the current hour
    current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    if df.index[-1] >= current_hour:
        print("✓ SUCCESS: Data includes current hour!")
    else:
        print("✗ FAILURE: Data is still old.")
        
except Exception as e:
    print(f"Error: {e}")
