import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from utils import (
    update_history,
    to_candles,
    send_telegram,
    DataError
)
from indicators import add_all_indicators
from signal_engine import check_entry


app = FastAPI()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")


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



@app.get("/run-signal")
def run_signal():
    try:
        # 1) تحديث التاريخ
        hist = update_history()

        # 2) بناء الشموع
        candles_5m = to_candles(hist, "5T")
        candles_15m = to_candles(hist, "15T")
        candles_1h = to_candles(hist, "60T")
        candles_4h = to_candles(hist, "240T")

        # 3) المؤشرات
        df_5m = add_all_indicators(candles_5m)
        df_15m = add_all_indicators(candles_15m)
        df_1h = add_all_indicators(candles_1h)
        df_4h = add_all_indicators(candles_4h)

        # 4) الإشارة
        signal = check_entry(df_5m, df_15m, df_1h, df_4h)

        # 5) تنبيه تيليجرام
        if signal.get("action") in ("BUY", "SELL"):
            action_emoji = "🟢 BUY" if signal["action"] == "BUY" else "🔴 SELL"
            msg = (
                f"<b>═══════════════════</b>\n"
                f"<b>{action_emoji} XAUUSD Signal</b>\n"
                f"<b>═══════════════════</b>\n\n"
                f"📊 <b>Timeframe:</b> {signal['timeframe']}\n"
                f"📈 <b>Trend:</b> {signal.get('market_status', 'N/A')}\n"
                f"💰 <b>Entry Price:</b> {signal['entry']:.2f}\n"
                f"🛑 <b>Stop Loss (SL):</b> {signal['sl']:.2f}\n"
                f"🎯 <b>Take Profit (TP):</b> {signal['tp']:.2f}\n\n"
                f"<b>═══════════════════</b>"
            )
            send_telegram(TG_TOKEN, TG_CHAT, msg)

        return signal

    except DataError as e:
        return JSONResponse(
            status_code=200, 
            content={"status": "waiting", "detail": str(e)}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
