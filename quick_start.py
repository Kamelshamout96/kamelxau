"""
Quick Start Script for Live Gold Trading System
================================================

This script helps you:
1. Collect live gold price data
2. Analyze the data and get trading signals

USAGE:
------
To collect data for 1 hour:
    py quick_start.py collect 60

To analyze collected data:
    py quick_start.py analyze

To see statistics:
    py quick_start.py stats
"""

import sys
from live_data_collector import collect_continuously, append_live_price, get_collection_stats
from live_signal_analyzer import analyze_live_data


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "collect":
        # Collect data
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        print(f"\n🚀 Starting data collection for {duration} minutes...")
        print("   Press Ctrl+C to stop early\n")
        collect_continuously(duration_minutes=duration, interval_seconds=60)
        
    elif command == "once":
        # Collect one data point
        print("\n📊 Collecting single data point...")
        append_live_price()
        get_collection_stats()
        
    elif command == "stats":
        # Show statistics
        get_collection_stats()
        
    elif command == "analyze":
        # Analyze and generate signals
        analyze_live_data()
        
    elif command == "auto":
        # Auto mode: collect one point then analyze
        print("\n🔄 AUTO MODE: Collect + Analyze")
        print("=" * 70)
        
        # Collect latest price
        print("\n1️⃣ Collecting latest price...")
        append_live_price()
        
        # Analyze
        print("\n2️⃣ Analyzing data...")
        analyze_live_data()
        
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
