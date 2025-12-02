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


# ===========================
#   Fetch GoldAPI Price
# ===========================
def fetch_spot_from_goldapi(api_key: str) -> Tuple[pd.Timestamp, float]:
    if not api_key:
        raise DataError("GOLDAPI_KEY is not set")

    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": api_key,
        "Content-Type": "application/json",
    }

    # retry 3 times
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            data = resp.json()

            if "price" not in data:
                msg = data.get("error") or data.get("message") or str(data)
                raise DataError(f"GoldAPI error: {msg}")

            price = float(data["price"])

            if "timestamp" in data:
                ts = pd.to_datetime(data["timestamp"], unit="s", utc=True)
            else:
                ts = pd.to_datetime(data.get("date"), utc=True)

            return ts, price

        except Exception as e:
            if attempt == 2:
                raise DataError(f"GoldAPI timeout/error: {str(e)}")


# ===========================
#   Load History
# ===========================
def load_history() -> pd.DataFrame:
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)

        # دعم لكل أنواع الـ timestamps
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
            format="mixed"
        )

        df = df.set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]

        return df

    return pd.DataFrame(columns=["price"]).astype({"price": "float64"})


# ===========================
#   Save History
# ===========================
def save_history(df: pd.DataFrame) -> None:
    df = df.copy().sort_index()
    df = df[~df.index.duplicated(keep="last")]

    df.reset_index().rename(columns={"index": "timestamp"}).to_csv(
        DATA_FILE, index=False
    )


# ===========================
#   Update History with new price
# ===========================
def update_history(api_key: str) -> pd.DataFrame:
    ts, price = fetch_spot_from_goldapi(api_key)
    df = load_history()

    # إذا timestamp الجديد أصغر أو مساوي للقديم → زد 1ms
    if not df.empty and ts <= df.index.max():
        ts = df.index.max() + pd.Timedelta(milliseconds=1)

    df.loc[ts] = price

    # keep last 7 days only
    if not df.empty:
        df = df[df.index >= (df.index.max() - pd.Timedelta(days=7))]

    save_history(df)
    return df


# ===========================
#   Convert History → Candles
# ===========================
def history_to_candles(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty or len(df) < 30:
        raise DataError("Not enough history collected yet")

    df = df.copy().sort_index()
    df = df[~df.index.duplicated(keep="last")]

    try:
        ohlc = df["price"].resample(rule).ohlc().dropna()
    except Exception as e:
        raise DataError(f"Resample failed: {str(e)}")

    ohlc["volume"] = 100.0

    ohlc.index = pd.to_datetime(
        ohlc.index,
        utc=True,
        format="mixed"
    )

    return ohlc


# ===========================
#   Telegram Alerts
# ===========================
def send_telegram(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    bot = Bot(token=token)
    bot.send_message(chat_id=chat_id, text=msg)
