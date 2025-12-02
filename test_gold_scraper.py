from utils import get_live_gold_price_usa, DataError

print("Testing Spot Gold price scraper...")
print("=" * 50)

try:
    price = get_live_gold_price_usa()
    print(f"\n✓ SUCCESS!")
    print(f"Current Spot Gold Price: ${price:.2f} USD/oz")
except DataError as e:
    print(f"\n✗ FAILED: {e}")
except Exception as e:
    print(f"\n✗ UNEXPECTED ERROR: {e}")
