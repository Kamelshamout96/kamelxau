import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from indicators import add_all_indicators
from signal_engine import check_entry
from utils import (
    update_history,
    history_to_candles,
    send_telegram,
    DataError,
)

app = FastAPI()

ALPHA_KEY = os.getenv("ALPHA_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")


@app.get("/run-signal")
def run_signal():
    try:
        # 1) Update local tick history from AlphaVantage (XAU/USD mid-price)
        hist = update_history(ALPHA_KEY)

        # 2) Build multi-timeframe candles from that history
        candles_5m = history_to_candles(hist, "5T")
        candles_15m = history_to_candles(hist, "15T")
        candles_1h = history_to_candles(hist, "60T")
        candles_4h = history_to_candles(hist, "240T")

        # 3) Add indicators
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)

        # 4) Compute signal
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)

        # 5) Notify on Telegram if trade
        if signal.get("action") in ("BUY", "SELL"):
            msg = (
                f"XAUUSD {signal['action']} ({signal.get('timeframe','5m')})\n"
                f"Entry: {signal['entry']:.2f}\n"
                f"SL   : {signal['sl']:.2f}\n"
                f"TP   : {signal['tp']:.2f}"
            )
            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return signal

    except DataError as e:
        return JSONResponse(
            status_code=502,
            content={"error": "data_error", "detail": str(e)},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
