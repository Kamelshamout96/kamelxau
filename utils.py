import os
import requests
import pandas as pd
from pathlib import Path
from telegram import Bot


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

HISTORY_FILE = DATA_DIR / "xau_history.csv"


class DataError(Exception):
    pass


GOLD_API_KEY = os.getenv("GOLD_API_KEY")


def fetch_gold_data():
    if not GOLD_API_KEY:
        raise DataError("Missing GOLD_API_KEY")

    url = (
        "https://gold.g.apised.com/v1/latest?"
        "metals=XAU&base_currency=USD&currencies=USD&weight_unit=toz"
    )

    headers = {"x-api-key": GOLD_API_KEY}

    r = requests.get(url, headers=headers, timeout=15)
    data = r.json()

    if data.get("status") != "success":
        raise DataError(f"API Error: {data}")

    xau = data["data"]["metal_prices"]["XAU"]

    return {
        "open": float(xau["open"]),
        "high": float(xau["high"]),
        "low": float(xau["low"]),
        "close": float(xau["price"]),
    }


def load_history():
    if not HISTORY_FILE.exists():
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    try:
        df = pd.read_csv(HISTORY_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
        return df
    except:
        HISTORY_FILE.unlink(missing_ok=True)
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def save_history(df):
    df = df.copy().sort_index()
    df.reset_index().rename(columns={"index": "timestamp"}).to_csv(HISTORY_FILE, index=False)


def update_history():
    prices = fetch_gold_data()
    df = load_history()

    ts = pd.Timestamp.utcnow()

    df.loc[ts] = {
        "open": prices["open"],
        "high": prices["high"],
        "low": prices["low"],
        "close": prices["close"],
        "volume": 1,
    }

    df = df.last("7d")  # احتفظ بآخر 7 أيام فقط

    save_history(df)
    return df


def to_candles(df, rule):
    if len(df) < 50:  # أقل من 50 شمعة = لا EMA ولا مؤشرات
        raise DataError("Not enough history yet. Keep calling run-signal.")

    ohlc = df["close"].resample(rule).ohlc()
    ohlc["high"] = df["high"].resample(rule).max()
    ohlc["low"] = df["low"].resample(rule).min()
    ohlc["open"] = df["open"].resample(rule).first()
    ohlc["volume"] = df["volume"].resample(rule).sum()

    return ohlc.dropna()


def send_telegram(token, chat_id, msg):
    if not token or not chat_id:
        return
    Bot(token=token).send_message(chat_id=chat_id, text=msg)
