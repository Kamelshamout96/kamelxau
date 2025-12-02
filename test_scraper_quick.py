from utils import get_live_gold_price_usa

print("Testing ENHANCED scraper with XAUUSD cell targeting...")
print("=" * 60)

try:
    price = get_live_gold_price_usa()
    print(f"\n✅ SUCCESS! Current Spot Gold: ${price:.2f} USD/oz")
except Exception as e:
    print(f"\n❌ FAILED: {e}")
