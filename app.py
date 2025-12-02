from fastapi import FastAPI
from indicators import add_all_indicators
from utils import fetch_fx, send_telegram
from signal_engine import check_entry
import os

app = FastAPI()

API_KEY = os.getenv("ALPHA_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

@app.get("/run-signal")
def run_signal():
    df15 = fetch_fx("XAUUSD", "15min", API_KEY)
    df1h = fetch_fx("XAUUSD", "60min", API_KEY)
    df4h = fetch_fx("XAUUSD", "240min", API_KEY)
    df15 = add_all_indicators(df15)
    df1h = add_all_indicators(df1h)
    df4h = add_all_indicators(df4h)
    signal = check_entry(df15, df1h, df4h)
    if signal["action"] in ("BUY", "SELL"):
        msg = f"XAUUSD Signal {signal['action']}\nEntry: {signal['entry']}"
        send_telegram(TG_TOKEN, TG_CHAT, msg)
    return signal
