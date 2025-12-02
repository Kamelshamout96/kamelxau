import os
from pathlib import Path
from typing import Tuple

import pandas as pd
import requests
from telegram import Bot

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "xau_history.csv"
DATA_DIR.mkdir(exist_ok=True)


class DataError(Exception):
    pass


def fetch_spot_from_goldapi(api_key: str) -> Tuple[pd.Timestamp, float]:
    if not api_key:
        raise DataError("GOLDAPI_KEY is not set")

    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": api_key,
        "Content-Type": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    try:
        data = resp.json()
    except Exception:
        raise DataError(f"GoldAPI invalid response: HTTP {resp.status_code}")

    if "price" not in data:
        msg = data.get("error") or data.get("message") or str(data)
        raise DataError(f"GoldAPI error: {msg}")

    price = float(data["price"])
    if "timestamp" in data:
        ts = pd.to_datetime(data["timestamp"], unit="s", utc=True)
    else:
        ts = pd.to_datetime(data.get("date"), utc=True)

    return ts, price


def load_history() -> pd.DataFrame:
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
        return df
    return pd.DataFrame(columns=["price"]).astype({"price": "float64"})


def save_history(df: pd.DataFrame) -> None:
    df = df.copy()
    df = df.sort_index()
    df.reset_index().rename(columns={"index": "timestamp"}).to_csv(
        DATA_FILE, index=False
    )


def update_history(api_key: str) -> pd.DataFrame:
    ts, price = fetch_spot_from_goldapi(api_key)
    df = load_history()
    df.loc[ts] = price
    if not df.empty:
        max_ts = df.index.max()
        df = df[df.index >= (max_ts - pd.Timedelta(days=7))]
    save_history(df)
    return df


def history_to_candles(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty or len(df) < 30:
        raise DataError("Not enough history collected yet")
    ohlc = df["price"].resample(rule).ohlc().dropna()
    ohlc["volume"] = 100.0
    ohlc.index = pd.to_datetime(ohlc.index, utc=True)
    ohlc = ohlc.rename(
        columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
        }
    )
    return ohlc


def send_telegram(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    bot = Bot(token=token)
    bot.send_message(chat_id=chat_id, text=msg)
