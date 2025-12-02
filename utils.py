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
#   Fetch AlphaVantage XAUUSD
# ===========================
def fetch_spot_from_alpha(api_key: str) -> Tuple[pd.Timestamp, float]:
    if not api_key:
        raise DataError("ALPHA_KEY is not set")

    url = (
        "https://www.alphavantage.co/query"
        "?function=CURRENCY_EXCHANGE_RATE"
        "&from_currency=XAU&to_currency=USD"
        f"&apikey={api_key}"
    )

    resp = requests.get(url, timeout=20)
    try:
        data = resp.json()
    except Exception:
        raise DataError(f"AlphaVantage invalid JSON, HTTP {resp.status_code}")

    if "Realtime Currency Exchange Rate" not in data:
        # Often when limit reached, we get 'Note' or 'Error Message'
        msg = data.get("Note") or data.get("Error Message") or str(data)
        raise DataError(f"AlphaVantage error: {msg}")

    info = data["Realtime Currency Exchange Rate"]

    # Use bid/ask if available, fallback to exchange rate
    ex_rate = float(info.get("5. Exchange Rate"))
    bid = float(info.get("8. Bid Price", ex_rate))
    ask = float(info.get("9. Ask Price", ex_rate))
    mid = (bid + ask) / 2.0

    ts_str = info.get("6. Last Refreshed")
    ts = pd.to_datetime(ts_str, utc=True)

    return ts, mid


# ===========================
#   Load History (Auto-Clean)
# ===========================
def load_history() -> pd.DataFrame:
    if not DATA_FILE.exists():
        return pd.DataFrame(columns=["price"]).astype({"price": "float64"})

    try:
        df = pd.read_csv(DATA_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df.set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df
    except Exception:
        # corrupted file → delete and reset
        try:
            DATA_FILE.unlink()
        except Exception:
            pass
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
#   Update History
# ===========================
def update_history(api_key: str) -> pd.DataFrame:
    ts, price = fetch_spot_from_alpha(api_key)
    df = load_history()

    # ensure strictly increasing index
    if not df.empty and ts <= df.index.max():
        ts = df.index.max() + pd.Timedelta(seconds=1)

    df.loc[ts] = price

    # keep last 7 days only
    if not df.empty:
        df = df[df.index >= (df.index.max() - pd.Timedelta(days=7))]

    save_history(df)
    return df


# ===========================
#   Candles Builder
# ===========================
def history_to_candles(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty or len(df) < 50:
        raise DataError("Not enough history collected yet")

    df = df.copy().sort_index()
    df = df[~df.index.duplicated(keep="last")]

    try:
        ohlc = df["price"].resample(rule).ohlc().dropna()
    except Exception as e:
        # corrupted data → reset file
        try:
            DATA_FILE.unlink()
        except Exception:
            pass
        raise DataError("Corrupted data detected, history has been reset.")

    ohlc["volume"] = 100.0
    ohlc.index = pd.to_datetime(ohlc.index, utc=True)
    return ohlc


# ===========================
#   Telegram Alerts
# ===========================
def send_telegram(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    bot = Bot(token=token)
    bot.send_message(chat_id=chat_id, text=msg)
