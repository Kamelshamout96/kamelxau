import requests
import pandas as pd
from telegram import Bot

def fetch_fx(symbol, interval, api_key):
    url = (
        "https://www.alphavantage.co/query"
        f"?function=FX_INTRADAY&from_symbol=XAU&to_symbol=USD"
        f"&interval={interval}&apikey={api_key}&outputsize=full"
    )
    data = requests.get(url).json()
    key = f"Time Series FX ({interval})"
    df = pd.DataFrame.from_dict(data[key], orient="index").astype(float)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df["volume"] = 100
    return df

def send_telegram(token, chat_id, msg):
    bot = Bot(token=token)
    bot.send_message(chat_id=chat_id, text=msg)
