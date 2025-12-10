import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from core.final_signal_engine import FinalSignalEngine
from core.indicators import add_all_indicators
from core.live_data_collector import append_live_price, build_timeframe_candles, get_live_collected_data
from core.utils import DataError, isMarketOpen, nextMarketOpen, send_telegram, update_history

app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
DATA_DIR = Path("data")
LAST_SIGNAL_FILE = DATA_DIR / "last_signal.json"
DATA_DIR.mkdir(exist_ok=True)
ENGINE = FinalSignalEngine()


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

        signal = ENGINE.run(df_5m, df_15m, df_1h, df_4h)

        _save_last_signal(signal)

        if signal.get("action") in ("BUY", "SELL") and TG_TOKEN and TG_CHAT:
            action_icon = "🟢 BUY" if signal["action"] == "BUY" else "🔴 SELL"
            confidence = signal.get("confidence")
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
                val = signal.get(key)
                if val is not None:
                    tp_lines.append(f"{key.upper()}: {val}")
            tp_text = "\n".join(tp_lines) if tp_lines else "TP: n/a"

            side_icon = action_icon
            msg = (
                f"{side_icon} XAUUSD {stars} \n"
                f"💰 Entry: {signal.get('entry')} \n"
                f"🛑 Stop Loss: {signal.get('sl')} \n"
                f"{tp_text} \n"
            )

            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return signal

    except DataError as e:
        return JSONResponse(status_code=200, content={"status": "waiting", "detail": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
