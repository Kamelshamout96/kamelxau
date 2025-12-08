import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from utils import send_telegram, DataError, isMarketOpen, nextMarketOpen
from live_data_collector import (
    append_live_price,
    get_live_collected_data,
    build_timeframe_candles,
)
from indicators import add_all_indicators
from advanced_analysis import analyze_mtf
from signal_engine import check_entry, check_ultra_entry, check_ultra_v3
from signal_engine import check_golden_entry  # noqa: F401 (future use)
from human_like_analyzer import analyze_like_human


app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
COLLECTION_INTERVAL = 60  # seconds

_collector_stop = threading.Event()
_collector_thread = None
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LAST_SIGNAL_FILE = DATA_DIR / "last_signal.json"
LAST_HUMAN_SIGNAL_FILE = DATA_DIR / "last_signal_human.json"
last_entry_price = None


def normalize_signal(signal: dict) -> dict:
    """Round numeric prices to 2 decimals and standardize keys."""
    normalized = dict(signal)
    for key in ("entry", "sl", "tp"):
        if key in normalized and normalized[key] is not None:
            try:
                normalized[key] = round(float(normalized[key]), 2)
            except Exception:
                normalized[key] = normalized[key]
    return normalized


def is_duplicate_signal(current: dict, last: dict, tolerance: float = 0.05) -> bool:
    """Check duplicates using direction, timeframe, trend summary, and price tolerance."""
    if not last:
        return False
    if current.get("action") != last.get("action"):
        return False
    if current.get("timeframe") != last.get("timeframe"):
        return False
    if current.get("market_status") != last.get("market_status"):
        return False
    try:
        c_entry, l_entry = float(current.get("entry", 0)), float(last.get("entry", 0))
        c_sl, l_sl = float(current.get("sl", 0)), float(last.get("sl", 0))
        c_tp, l_tp = float(current.get("tp", 0)), float(last.get("tp", 0))
    except Exception:
        return False
    return (
        abs(c_entry - l_entry) < tolerance
        and abs(c_sl - l_sl) < tolerance
        and abs(c_tp - l_tp) < tolerance
    )


def _load_last_signal():
    if not LAST_SIGNAL_FILE.exists():
        return None
    try:
        with LAST_SIGNAL_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[warn] failed to read last signal: {e}")
        return None


def _save_last_signal(signal: dict):
    try:
        with LAST_SIGNAL_FILE.open("w", encoding="utf-8") as f:
            json.dump(signal, f)
    except Exception as e:
        print(f"[warn] failed to persist last signal: {e}")


def _load_last_human_signals() -> dict:
    if not LAST_HUMAN_SIGNAL_FILE.exists():
        return {}
    try:
        with LAST_HUMAN_SIGNAL_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as e:
        print(f"[warn] failed to read last human signals: {e}")
        return {}


def _save_last_human_signal(tf_name: str, signal: dict):
    try:
        data = _load_last_human_signals()
        data[tf_name] = signal
        with LAST_HUMAN_SIGNAL_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[warn] failed to persist last human signal: {e}")


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
            "/run-signal": "Get trading signal (BUY/SELL/NO_TRADE)",
            "/human-analysis": "🎨 Professional trader-style chart analysis",
            "/live-length": "Get collected data statistics"
        },
        "telegram_configured": bool(TG_TOKEN and TG_CHAT),
        "version": "2.0.0"
    }


@app.get("/health")
def health():
    """Health check endpoint for monitoring"""
    now_utc = datetime.now(timezone.utc)
    market_state = "OPEN" if isMarketOpen(now_utc) else "CLOSED"
    if market_state == "CLOSED":
        nxt = nextMarketOpen(now_utc).astimezone(ZoneInfo("Asia/Riyadh"))
        nxt_str = nxt.isoformat()
    else:
        nxt_str = None
    return {
        "status": "healthy",
        "telegram": "configured" if (TG_TOKEN and TG_CHAT) else "not configured",
        "market_status": market_state,
        "market_next_open_riyadh": nxt_str,
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
        global last_entry_price
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
        # ULTRA V3 primary fallback
        ultra_v3 = check_ultra_v3(df_5m, df_15m, df_1h, df_4h)
        if signal.get("action") == "NO_TRADE" and ultra_v3.get("action") in ("BUY", "SELL"):
            ultra_v3.setdefault("timeframe", "5m")
            signal = ultra_v3
        # ULTRA v1 secondary fallback
        ultra_signal = check_ultra_entry(df_5m, df_15m, df_1h, df_4h)
        if signal.get("action") == "NO_TRADE" and ultra_signal.get("action") in ("BUY", "SELL"):
            ultra_signal.setdefault("timeframe", "5m")
            signal = ultra_signal

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
            entry = float(signal.get("entry", 0))
            if last_entry_price is not None and abs(entry - last_entry_price) < 2:
                return {"status": "skipped", "reason": "entry too close to previous"}
            last_entry_price = entry

            confidence = signal.get("confidence", "UNKNOWN")
            confidence_emoji = signal.get("confidence_emoji", "")
            signal_type = signal.get("signal_type", "REGULAR")
            title = f"{signal['action']} XAUUSD Signal"
            confidence_text = confidence if confidence != "UNKNOWN" else signal_type

            normalized = normalize_signal(
                {
                    "action": signal.get("action"),
                    "timeframe": signal.get("timeframe"),
                    "entry": signal.get("entry"),
                    "sl": signal.get("sl"),
                    "tp": signal.get("tp"),
                    "market_status": signal.get("market_status"),
                }
            )
            last_signal = _load_last_signal()
            already_sent = is_duplicate_signal(normalized, last_signal)

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
                _save_last_signal(normalized)
            else:
                print("[info] signal already sent, skipping telegram")

        signal["analysis"] = analysis_summary
        signal["ultra_v3"] = ultra_v3
        signal["ultra"] = ultra_signal
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


@app.get("/human-analysis")
def human_analysis():
    """
    🎨 Professional Trader-Style Chart Analysis
    
    This endpoint mimics how a human trader would analyze the charts:
    - Support & Resistance levels
    - Trendlines & Channels (like the green lines in trading apps)
    - Chart Patterns (ascending/descending channels, triangles, etc.)
    - Supply & Demand Zones
    - Complete trade setups with reasoning
    
    Returns detailed analysis similar to what you'd see on TradingView!
    """
    try:
        # Fetch fresh live price
        append_live_price()
        
        # Load collected data
        hist = get_live_collected_data(limit=50000, days_back=40)
        
        # Build timeframes
        candles_5m = build_timeframe_candles(hist, "5min")
        candles_15m = build_timeframe_candles(hist, "15min")
        candles_1h = build_timeframe_candles(hist, "60min")
        candles_4h = build_timeframe_candles(hist, "240min")
        
        # Add indicators
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)
        
        # Run human-like analysis
        human_analysis_result = analyze_like_human(df_5m, df_15m, df_1h, df_4h)
        
        current_price = df_5m['close'].iloc[-1]
        
        # Send Telegram per timeframe if action is BUY or SELL
        if human_analysis_result['action'] in ['BUY', 'SELL']:
            tf_map = human_analysis_result['timeframe_analysis']
            tf_order = ['1H', '15m', '5m']

            def _build_msg(tf_name: str, tf_data: dict, rec: dict, tf_conf: float) -> str:
                reasoning_text = "\n".join([f"  • {r}" for r in rec.get('reasoning', [])[:5]])
                patterns_text = ", ".join(tf_data.get('patterns', []))

                levels_text = ""
                for level_name, level_price in tf_data.get('key_levels', {}).items():
                    levels_text += f"\n  📍 {level_name}: ${level_price:.2f}"

                tp_lines = ""
                for idx, key in enumerate(["tp1", "tp2", "tp3"], start=1):
                    val = rec.get(key)
                    if val is not None:
                        tp_lines += f"✅ TP{idx}: ${val:.2f}\n"
                if not tp_lines and rec.get('tp') is not None:
                    tp_lines = f"🎯 Take Profit: ${rec['tp']:.2f}\n"

                early_note = ""
                if tf_data.get('early_prediction', False):
                    early_note = "⚠️ NOTE: EARLY PREDICTION SIGNAL\n"

                return (
                    f"🎨 <b>{human_analysis_result['action']} - ANALYSIS {tf_name}</b>\n"
                    f"━━━━━━━━━━━━\n"
                    f"{early_note}"
                    f"📊 Current Price: ${current_price:.2f}\n"
                    f"🎯 Entry: ${rec.get('entry', 0):.2f}\n"
                    f"🛑 Stop Loss: ${rec.get('sl', 0):.2f}\n"
                    f"{tp_lines}"
                    f"⚖️ Risk:Reward: 1:{tf_data.get('risk_reward', 0.0):.2f}\n"
                    f"🔥 Confidence: {tf_conf:.0f}%\n"
                    f"\n"
                    f"📈 Patterns Detected:\n  {patterns_text}\n"
                    f"{levels_text}\n"
                    f"\n"
                    f"💡 Analysis Reasoning:\n{reasoning_text}\n"
                )

            if TG_TOKEN and TG_CHAT:
                last_human = _load_last_human_signals()
                for tf_name in tf_order:
                    tf_data = tf_map.get(tf_name)
                    if not tf_data or tf_data.get('action') != human_analysis_result['action']:
                        continue

                    rec = human_analysis_result['recommendation'] if tf_name == '1H' else tf_data
                    normalized = normalize_signal(
                        {
                            "action": tf_data.get("action"),
                            "timeframe": f"{tf_name}-HUMAN",
                            "entry": rec.get("entry"),
                            "sl": rec.get("sl"),
                            "tp": rec.get("tp"),
                            "market_status": "HUMAN",
                        }
                    )

                    tf_conf = tf_data.get("confidence", human_analysis_result.get("confidence", 0.0))
                    msg = _build_msg(tf_name, tf_data, rec, tf_conf)
                    already_sent = is_duplicate_signal(normalized, last_human.get(tf_name, {}))
                    if not already_sent:
                        send_telegram(TG_TOKEN, TG_CHAT, msg)
                        _save_last_human_signal(tf_name, normalized)
                        last_human[tf_name] = normalized
                    else:
                        print(f"[info] human analysis signal already sent for {tf_name}, skipping telegram")

        return human_analysis_result
    
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
