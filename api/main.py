import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from core.indicators import add_all_indicators
from core.live_data_collector import append_live_price, build_timeframe_candles, get_live_collected_data
from core.signal_engine import check_entry, check_ultra_entry, check_ultra_v3
from core.utils import DataError, isMarketOpen, nextMarketOpen, send_telegram, update_history, validate_direction_consistency

app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
FORWARD_CHANNEL_ID = -1002938646549
DATA_DIR = Path("data")
LAST_SIGNAL_FILE = DATA_DIR / "last_signal.json"
DATA_DIR.mkdir(exist_ok=True)


def _load_last_signal() -> dict:
    if not LAST_SIGNAL_FILE.exists():
        return {}
    try:
        return json.loads(LAST_SIGNAL_FILE.read_text())
    except Exception:
        return {}


def _save_last_signal(signal: dict) -> None:
    try:
        LAST_SIGNAL_FILE.write_text(json.dumps(signal))
    except Exception:
        return


def _fallback_history() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hist = update_history()
    candles_5m = hist
    candles_15m = hist.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    candles_1h = hist.resample("60min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    candles_4h = hist.resample("240min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return candles_5m, candles_15m, candles_1h, candles_4h


def forward_to_channel(update: dict) -> None:
    """
    Forward any incoming Telegram message to the configured broadcast channel.
    Uses forwardMessage so media and formatting stay intact.
    """
    if not TG_TOKEN:
        return

    try:
        message = None
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            if key in update and update.get(key):
                message = update[key]
                break

        if not message:
            return

        from_chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        if from_chat_id is None or message_id is None:
            return

        if from_chat_id == FORWARD_CHANNEL_ID:
            return

        url = f"https://api.telegram.org/bot{TG_TOKEN}/forwardMessage"
        payload = {"chat_id": FORWARD_CHANNEL_ID, "from_chat_id": from_chat_id, "message_id": message_id}
        requests.post(url, json=payload, timeout=10)
    except Exception:
        try:
            print("Warning: failed to forward Telegram update")
        except Exception:
            pass


@app.get("/")
def root():
    return {"service": "KAMEL-XAU", "status": "online"}


@app.get("/health")
def health():
    now = datetime.now(timezone.utc)
    return {
        "status": "healthy",
        "market_open": isMarketOpen(now),
        "next_open": nextMarketOpen(now).isoformat(),
        "telegram_configured": bool(TG_TOKEN and TG_CHAT),
    }


@app.get("/live-length")
def live_length():
    try:
        df = get_live_collected_data(limit=50000)
        return {"rows": len(df), "latest": df.index[-1].isoformat()}
    except DataError as e:
        return JSONResponse(status_code=200, content={"status": "waiting", "detail": str(e)})


@app.get("/run-signal")
def run_signal():
    try:
        try:
            append_live_price()
        except Exception:
            pass

        try:
            hist = get_live_collected_data(limit=50000)
            candles_5m = build_timeframe_candles(hist, "5min")
            candles_15m = build_timeframe_candles(hist, "15min")
            candles_1h = build_timeframe_candles(hist, "60min")
            candles_4h = build_timeframe_candles(hist, "240min")
        except DataError:
            candles_5m, candles_15m, candles_1h, candles_4h = _fallback_history()

        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)

        unified = check_entry(df_5m, df_15m, df_1h, df_4h)
        if unified.get("action") == "NO_TRADE":
            alt_v3 = check_ultra_v3(df_5m, df_15m, df_1h, df_4h)
            if alt_v3.get("action") in ("BUY", "SELL"):
                unified = alt_v3
            else:
                alt_ultra = check_ultra_entry(df_5m, df_15m, df_1h, df_4h)
                if alt_ultra.get("action") in ("BUY", "SELL"):
                    unified = alt_ultra

        unified = validate_direction_consistency(unified)

        # Duplicate guard: block re-emitting same action within 2 USD of last entry
        last_sig = _load_last_signal()
        try:
            if (
                last_sig
                and last_sig.get("action") == unified.get("action") in ("BUY", "SELL")
                and last_sig.get("entry") is not None
                and unified.get("entry") is not None
            ):
                if abs(float(unified["entry"]) - float(last_sig["entry"])) <= 2.0:
                    return {"status": "duplicate_blocked", "detail": "entry within 2 USD of last signal", "last": last_sig}
        except Exception:
            pass

        _save_last_signal(unified)

        if unified.get("action") in ("BUY", "SELL") and TG_TOKEN and TG_CHAT:
            action_icon = "BUY" if unified["action"] == "BUY" else "SELL"
            confidence = unified.get("confidence")
            stars = ""
            try:
                if confidence is not None:
                    c_val = float(confidence)
                    stars_count = 3 if c_val >= 85 else 2 if c_val >= 70 else 1
                    stars = " " + ("⭐" * stars_count)
            except Exception:
                stars = ""

            tp_lines = []
            for key in ("tp1", "tp2", "tp3"):
                val = unified.get(key)
                if val is not None:
                    tp_lines.append(f"{key.upper()}: {val}")
            tp_text = "\n".join(tp_lines) if tp_lines else "TP: n/a"

            side_icon = "🟢" if unified["action"] == "BUY" else "🔴"
            msg = (
                f"{side_icon} {action_icon} XAUUSD {stars} \n"
                f"💰 Entry: {unified.get('entry')} \n"
                f"🛑 Stop Loss: {unified.get('sl')} \n"
                f"{tp_text} \n"
                "🕒 Timeframes: 5m > 15m > 1H > 4H"
            )

            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return unified

    except DataError as e:
        return JSONResponse(status_code=200, content={"status": "waiting", "detail": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/telegram/update")
async def telegram_update(update: dict):
    forward_to_channel(update)
    return {"ok": True}
