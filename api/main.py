import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from core.indicators import add_all_indicators
from core.live_data_collector import append_live_price, build_timeframe_candles, get_live_collected_data
from core.signal_engine import check_entry, check_ultra_entry, check_ultra_v3
from core.utils import DataError, isMarketOpen, nextMarketOpen, send_telegram, update_history, validate_direction_consistency

app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")
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
        _save_last_signal(unified)

        if unified.get("action") in ("BUY", "SELL") and TG_TOKEN and TG_CHAT:
            msg = (
                f"{unified['action']} XAUUSD\n"
                f"Entry: {unified.get('entry')}\n"
                f"SL: {unified.get('sl')}\n"
                f"TP: {unified.get('tp1', unified.get('tp'))}"
            )
            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return unified

    except DataError as e:
        return JSONResponse(status_code=200, content={"status": "waiting", "detail": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
