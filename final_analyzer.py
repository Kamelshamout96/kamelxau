"""
FINAL LIVE SIGNAL ANALYZER
==========================
Pure web-scraped pipeline using livepriceofgold.com data only.
Collects the latest price, builds multi-timeframe candles, adds indicators,
then generates trade signals.
"""

from datetime import datetime

from live_data_collector import (
    append_live_price,
    build_timeframe_candles,
    get_live_collected_data,
)
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry
from utils import DataError

TIMEFRAMES = [
    ("5m", "5min"),
    ("15m", "15min"),
    ("1h", "60min"),
    ("4h", "240min"),
]


def _collect_latest_sample():
    """Grab a fresh price so analysis always uses live data."""
    price, ts = append_live_price()
    if price is not None:
        print(f"Fetched live price ${price:.2f} at {ts}")
    else:
        print("Live price fetch returned None; proceeding with existing data if available.")
    return price


def _build_timeframes(df_1m):
    candles = {}
    for label, rule in TIMEFRAMES:
        candles[label] = build_timeframe_candles(df_1m, rule)
        print(f"{label} candles: {len(candles[label])}")
    return candles


def _add_indicators(candles):
    return {label: add_all_indicators(df) for label, df in candles.items()}


def analyze_live():
    """Analyze pure web-scraped data and return a signal dict."""
    print("\n" + "=" * 70)
    print("LIVE WEB-SCRAPED SIGNAL ANALYZER")
    print("=" * 70)
    try:
        _collect_latest_sample()

        df_1m = get_live_collected_data()
        print(f"Loaded {len(df_1m)} x 1-minute candles")
        print(f"Range: {df_1m.index[0]} -> {df_1m.index[-1]}")
        print(f"Latest price: ${df_1m['close'].iloc[-1]:.2f}")
        print(f"Data age (minutes): {(datetime.now() - df_1m.index[-1]).total_seconds()/60:.1f}")

        candles = _build_timeframes(df_1m)

        print("\nCalculating indicators...")
        inds = _add_indicators(candles)
        last_5m = inds["5m"].iloc[-1]
        print(
            f"5m snapshot -> Close: ${last_5m['close']:.2f}, RSI: {last_5m['rsi']:.1f}, "
            f"MACD: {last_5m['macd']:.2f}/{last_5m['macd_signal']:.2f}, "
            f"EMA50/200: {last_5m['ema50']:.2f}/{last_5m['ema200']:.2f}"
        )

        print("\nGenerating signals...")
        signal = check_entry(inds["5m"], inds["15m"], inds["1h"], inds["4h"])
        if signal.get("action") == "NO_TRADE":
            st_signal = check_supertrend_entry(inds["5m"], inds["15m"], inds["1h"], inds["4h"])
            if st_signal.get("action") in ("BUY", "SELL"):
                signal = st_signal

        print("\n" + "=" * 70)
        if signal.get("action") in ("BUY", "SELL"):
            print(f"{signal['action']} SIGNAL")
            print(f"Confidence: {signal.get('confidence', 'N/A')} {signal.get('confidence_emoji', '')}")
            print(f"Timeframe: {signal.get('timeframe', 'N/A')}")
            print(f"Entry: ${signal['entry']:.2f} | SL: ${signal['sl']:.2f} | TP: ${signal['tp']:.2f}")
            sl_pips = abs(signal['entry'] - signal['sl']) * 10
            tp_pips = abs(signal['tp'] - signal['entry']) * 10
            rr = tp_pips / sl_pips if sl_pips else 0
            print(f"Pips -> SL: {sl_pips:.1f}, TP: {tp_pips:.1f}, R:R=1:{rr:.2f}")
            print(f"Market status: {signal.get('market_status', 'N/A')}")
        else:
            print("NO TRADE")
            print(f"Reason: {signal.get('reason', 'N/A')}")
            print(f"Market status: {signal.get('market_status', 'N/A')}")
        print("=" * 70 + "\n")
        return signal

    except DataError as e:
        print(f"Data error: {e}")
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
    return None


if __name__ == "__main__":
    analyze_live()
