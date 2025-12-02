import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from utils import (
    fetch_gold_data,
    build_single_candle,
    send_telegram,
    DataError
)

from indicators import add_all_indicators
from signal_engine import check_entry

app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")


@app.get("/run-signal")
def run_signal():
    try:
        # 1) جلب بيانات الذهب الحقيقية (price, bid, ask, open, high, low)
        prices = fetch_gold_data()

        # 2) نبني شمعة واحدة OHLC
        candle = build_single_candle(prices)

        # 3) نكرر نفس الشمعة للتايم فريمات (لأن APISed لا يوفر شموع)
        df_5m = add_all_indicators(candle)
        df_15m = add_all_indicators(candle)
        df_1h = add_all_indicators(candle)
        df_4h = add_all_indicators(candle)

        # 4) استخراج الإشارة
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)

        # 5) إرسال تنبيه اگر BUY/SELL
        if signal.get("action") in ("BUY", "SELL"):
            msg = (
                f"XAUUSD {signal['action']} (instant)\n"
                f"Price: {prices['price']:.2f}\n"
                f"Bid : {prices['bid']:.2f}\n"
                f"Ask : {prices['ask']:.2f}"
            )
            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return {
            "prices": prices,
            "signal": signal
        }

    except DataError as e:
        return JSONResponse(status_code=502, content={"error": "api_error", "detail": str(e)})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
