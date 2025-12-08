import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from core.utils import DataError, get_live_gold_price_usa, isMarketOpen

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LIVE_DATA_FILE = DATA_DIR / "live_1m.csv"
CACHE_TTL_SECONDS = 60
_cache = {"ts": 0.0, "df": None}


def append_live_price() -> Tuple[Optional[float], Optional[datetime]]:
    now_utc = datetime.now(timezone.utc)
    if not isMarketOpen(now_utc):
        return None, None

    price = get_live_gold_price_usa()
    current_time = datetime.now(ZoneInfo("Asia/Riyadh")).replace(microsecond=0)
    row = {"timestamp": current_time.isoformat(), "open": price, "high": price, "low": price, "close": price, "volume": 0}
    if LIVE_DATA_FILE.exists():
        df = pd.read_csv(LIVE_DATA_FILE)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(LIVE_DATA_FILE, index=False)
    _cache["ts"] = 0.0
    return price, current_time


def _load_local_1m(limit: int = 50000) -> pd.DataFrame:
    if not LIVE_DATA_FILE.exists():
        raise DataError("No local live data available. Collect first.")
    df = pd.read_csv(LIVE_DATA_FILE)
    if "timestamp" not in df.columns:
        raise DataError("Timestamp column missing in live data.")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    if limit and len(df) > limit:
        df = df.tail(limit)
    return df


def get_live_collected_data(limit: int = 50000, days_back: int = 40):
    now_ts = time.time()
    if _cache["df"] is not None and now_ts - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["df"].copy()
    df = _load_local_1m(limit=limit)
    _cache["df"] = df
    _cache["ts"] = now_ts
    return df.copy()


def build_timeframe_candles(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if df_1m is None or len(df_1m) == 0:
        raise DataError("No 1m data available to resample.")
    if not isinstance(df_1m.index, pd.DatetimeIndex):
        if "timestamp" in df_1m.columns:
            df_1m = df_1m.copy()
            df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"])
            df_1m = df_1m.set_index("timestamp")
        else:
            raise DataError("Data must have a DatetimeIndex or a 'timestamp' column.")
    df_1m = df_1m.sort_index()
    df_1m = df_1m[~df_1m.index.duplicated(keep="last")]
    if len(df_1m) < 10:
        raise DataError(f"Not enough 1m data: {len(df_1m)} rows")

    if isinstance(timeframe, str) and timeframe.endswith("T"):
        timeframe = timeframe[:-1] + "min"

    candles = df_1m.resample(timeframe).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    if candles.empty:
        raise DataError(f"No candles produced when resampling to {timeframe}.")
    return candles


def get_collection_stats() -> dict:
    df = _load_local_1m()
    return {
        "rows": len(df),
        "start": df.index[0].isoformat(),
        "end": df.index[-1].isoformat(),
        "latest_price": float(df["close"].iloc[-1]),
    }
