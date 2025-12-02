from fastapi import FastAPI
from indicators import add_all_indicators
from utils import fetch_fx, send_telegram
from signal_engine import check_entry
import os

app=FastAPI()
API_KEY=os.getenv("ALPHA_KEY")
TG_TOKEN=os.getenv("TG_TOKEN")
TG_CHAT=os.getenv("TG_CHAT")

@app.get("/run-signal")
def run_signal():
    df15=add_all_indicators(fetch_fx("XAUUSD","15min",API_KEY))
    df1=add_all_indicators(fetch_fx("XAUUSD","60min",API_KEY))
    df4=add_all_indicators(fetch_fx("XAUUSD","240min",API_KEY))
    signal=check_entry(df15,df1,df4)
    if signal["action"] in ("BUY","SELL"):
        msg=f"XAUUSD {signal['action']}\nEntry:{signal['entry']}\nSL:{signal['sl']}\nTP:{signal['tp']}"
        send_telegram(TG_TOKEN,TG_CHAT,msg)
    return signal
