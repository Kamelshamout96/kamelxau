import os
import requests
import pandas as pd
from telegram import Bot


class DataError(Exception):
    pass


GOLD_API_KEY = os.getenv("GOLD_API_KEY")


def fetch_gold_data():

    if not GOLD_API_KEY:
        raise DataError("GOLD_API_KEY is missing")

    url = (
        "https://gold.g.apised.com/v1/latest"
        "?metals=XAU&base_currency=USD&currencies=USD&weight_unit=toz"
    )

    headers = {"x-api-key": GOLD_API_KEY}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
    except Exception as e:
        raise DataError(f"Connection error: {e}")

    # التحقق من النجاح
    if data.get("status") != "success":
        raise DataError(f"API Error: {data}")

    xau = data["data"]["metal_prices"]["XAU"]

    return {
        "price": float(xau["price"]),
        "bid": float(xau["bid"]),
        "ask": float(xau["ask"]),
        "open": float(xau["open"]),
        "high": float(xau["high"]),
        "low": float(xau["low"]),
    }


def build_single_candle(prices: dict) -> pd.DataFrame:

    df = pd.DataFrame(
        [
            {
                "open": prices["open"],
                "high": prices["high"],
                "low": prices["low"],
                "close": prices["price"],
                "volume": 1
            }
        ],
        index=[pd.Timestamp.utcnow()]
    )

    return df


def send_telegram(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    bot = Bot(token=token)
    bot.send_message(chat_id=chat_id, text=msg)
