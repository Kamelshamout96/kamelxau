import os
import threading
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from utils import send_telegram, DataError
from live_data_collector import (
    append_live_price,
    get_live_collected_data,
    build_timeframe_candles,
)
from indicators import add_all_indicators
from advanced_analysis import analyze_mtf
from signal_engine import check_entry, check_supertrend_entry
from signal_engine import check_golden_entry  # noqa: F401 (future use)


app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
COLLECTION_INTERVAL = 60  # seconds

_collector_stop = threading.Event()
_collector_thread = None
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SENT_LOG = DATA_DIR / "sent_signals.csv"


def _normalize_trade_value(value) -> str:
    """
    Normalize trade numeric values so deduplication ignores decimal separators.
    Falls back to stripping dots/commas if parsing fails.
    """
    try:
        return str(int(float(str(value).replace(",", ".").strip())))
    except Exception:
        value_str = str(value)
        return value_str.replace(".", "").replace(",", "")


def _normalize_signal_key(raw_key: str) -> str:
    """Normalize an existing log key to the same decimal-insensitive form."""
    parts = raw_key.split("-")
    if len(parts) >= 5:
        action, timeframe, entry, sl, tp = parts[:5]
        return "-".join(
            [
                action,
                timeframe,
                _normalize_trade_value(entry),
                _normalize_trade_value(sl),
                _normalize_trade_value(tp),
            ]
        )
    return raw_key


def _build_signal_key(signal: dict) -> str:
    """Build a key that ignores decimal separators for deduplication."""
    return "-".join(
        [
            signal.get("action", ""),
            signal.get("timeframe", ""),
            _normalize_trade_value(signal.get("entry")),
            _normalize_trade_value(signal.get("sl")),
            _normalize_trade_value(signal.get("tp")),
        ]
    )


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
        # Fetch last 40 days (~50k rows) for a broader view
        df = get_live_collected_data(limit=50000, days_back=40)
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
        # Use a wide window to satisfy higher TF indicators (4H EMA200 needs ~33 days)
        hist = get_live_collected_data(limit=50000, days_back=40)

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

        latest_price = df_5m["close"].iloc[-1]

        # Generate signals
        analysis_summary = analyze_mtf(
            {"4H": df_4h, "1H": df_1h, "15m": df_15m, "5m": df_5m}
        )
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)
        if signal.get("action") == "NO_TRADE":
            supertrend_signal = check_supertrend_entry(df_5m, df_15m, df_1h, df_4h)
            if supertrend_signal.get("action") in ("BUY", "SELL"):
                signal = supertrend_signal

        # Telegram alerts for potential setups / trend updates
        def _send_alert(title: str, body: str) -> None:
            if TG_TOKEN and TG_CHAT:
                send_telegram(TG_TOKEN, TG_CHAT, f"{title}\n{body}")

        # if signal.get("action") == "NO_TRADE":
        #     status = signal.get("market_status", "N/A")
        #     reason = signal.get("reason", "N/A")
        #     body = (
        #         f"Status: {status}\n"
        #         f"Reason: {reason}\n"
        #         f"Last price: ${latest_price:.2f}"
        #     )
        #     _send_alert("[POTENTIAL SETUP]", body)
        #     if "trend" in reason.lower() or "trend" in status.lower():
        #         _send_alert("[TREND ALERT]", f"{status}\nLast price: ${latest_price:.2f}")

        # Send Telegram if a trade exists
        if signal.get("action") in ("BUY", "SELL"):
            confidence = signal.get("confidence", "UNKNOWN")
            confidence_emoji = signal.get("confidence_emoji", "")
            signal_type = signal.get("signal_type", "REGULAR")
            title = f"{signal['action']} XAUUSD Signal"
            confidence_text = confidence if confidence != "UNKNOWN" else signal_type

            # Deduplicate signals and purge entries older than 1 hour
            key = _build_signal_key(signal)
            already_sent = False
            now_ts = time.time()
            kept = {}
            try:
                if SENT_LOG.exists():
                    with SENT_LOG.open("r", encoding="utf-8") as f:
                        for line in f:
                            parts = line.strip().split(",")
                            if len(parts) != 2:
                                continue
                            k, ts_str = parts
                            try:
                                ts_val = float(ts_str)
                            except ValueError:
                                continue
                            if now_ts - ts_val > 3600:
                                continue
                            normalized_k = _normalize_signal_key(k)
                            if normalized_k == key:
                                already_sent = True
                            kept[normalized_k] = max(ts_val, kept.get(normalized_k, 0))
            except Exception as e:
                print(f"[warn] failed to read signal log: {e}")
                kept = {}

            if not already_sent:
                kept[key] = now_ts
                try:
                    with SENT_LOG.open("w", encoding="utf-8") as f:
                        for k, ts_val in kept.items():
                            f.write(f"{k},{ts_val}\\n")
                except Exception as e:
                    print(f"[warn] failed to log signal: {e}")

            msg = (
                f"🚀 <b>{title}</b>\n"
                f"🔖 Confidence: {confidence} {confidence_emoji}\n"
                f"🧭 Type: {signal_type}\n"
                f"⏱ Timeframe: {signal.get('timeframe', 'N/A')}\n"
                f"📈 Trend: {signal.get('market_status', 'N/A')}\n"
                f"🎯 Entry: {signal['entry']:.2f}\n"
                f"🛑 SL: {signal['sl']:.2f}\n"
                f"✅ TP: {signal['tp']:.2f}\n"
                f"🗒 Notes: {confidence_text}"
            )

            if not already_sent:
                send_telegram(TG_TOKEN, TG_CHAT, msg)
            else:
                print("[info] signal already sent, skipping telegram")

        signal["analysis"] = analysis_summary
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
