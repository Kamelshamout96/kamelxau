import os
import threading
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from utils import send_telegram, DataError
from live_data_collector import (
    append_live_price,
    get_live_collected_data,
    build_timeframe_candles,
)
from indicators import add_all_indicators
from signal_engine import check_entry, check_supertrend_entry


app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
COLLECTION_INTERVAL = 60  # seconds

_collector_stop = threading.Event()
_collector_thread = None


def _collector_loop():
    """Background loop to keep live data fresh."""
    while not _collector_stop.is_set():
        try:
            append_live_price()
        except Exception as exc:
            print(f"[collector] error: {exc}")
        # wait with interruption support
        _collector_stop.wait(COLLECTION_INTERVAL)


@app.on_event("startup")
def start_background_collector():
    global _collector_thread
    if _collector_thread is None or not _collector_thread.is_alive():
        _collector_thread = threading.Thread(target=_collector_loop, daemon=True)
        _collector_thread.start()
        print("[collector] started background collection")


@app.on_event("shutdown")
def stop_background_collector():
    _collector_stop.set()
    if _collector_thread and _collector_thread.is_alive():
        _collector_thread.join(timeout=5)
        print("[collector] stopped background collection")


@app.get("/")
def root():
    """Root endpoint - provides API documentation"""
    return {
        "service": "XAUUSD Trading Signal Tool",
        "status": "online",
        "endpoints": {
            "/": "This documentation",
            "/health": "Health check",
            "/run-signal": "Get trading signal (BUY/SELL/NO_TRADE)"
        },
        "telegram_configured": bool(TG_TOKEN and TG_CHAT),
        "version": "1.0.0"
    }


@app.get("/health")
def health():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "telegram": "configured" if (TG_TOKEN and TG_CHAT) else "not configured"
    }


@app.get("/live-length")
def live_length():
    """Return count and time range of collected 1m live data."""
    try:
        df = get_live_collected_data()
        return {
            "count": int(len(df)),
            "first": df.index[0].isoformat(),
            "last": df.index[-1].isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



@app.get("/run-signal")
def run_signal():
    try:
        # Always fetch a fresh live price first
        append_live_price()

        # Load collected 1-minute candles from web scraping
        hist = get_live_collected_data()

        # Build higher timeframes
        candles_5m = build_timeframe_candles(hist, "5min")
        candles_15m = build_timeframe_candles(hist, "15min")
        candles_1h = build_timeframe_candles(hist, "60min")
        candles_4h = build_timeframe_candles(hist, "240min")

        # Calculate indicators
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)

        # Generate signals
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)
        if signal.get("action") == "NO_TRADE":
            supertrend_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
            if supertrend_signal.get("action") in ("BUY", "SELL"):
                signal = supertrend_signal

        # Send Telegram if a trade exists
        if signal.get("action") in ("BUY", "SELL"):
            confidence = signal.get("confidence", "UNKNOWN")
            confidence_emoji = signal.get("confidence_emoji", "")
            signal_type = signal.get("signal_type", "REGULAR")
            title = f"{signal['action']} XAUUSD Signal"
            confidence_text = confidence if confidence != "UNKNOWN" else signal_type

            msg = (
                f"<b>{title}</b>\\n"
                f"Confidence: {confidence} {confidence_emoji}\\n"
                f"Type: {signal_type}\\n"
                f"Timeframe: {signal.get('timeframe', 'N/A')}\\n"
                f"Trend: {signal.get('market_status', 'N/A')}\\n"
                f"Entry: {signal['entry']:.2f}\\n"
                f"SL: {signal['sl']:.2f}\\n"
                f"TP: {signal['tp']:.2f}\\n"
                f"Notes: {confidence_text}"
            )
            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return signal

    except DataError as e:
        return JSONResponse(
            status_code=200,
            content={"status": "waiting", "detail": str(e)}
        )

    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=traceback.format_exc()
        )

    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=str(e))
