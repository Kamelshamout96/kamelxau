import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from core.utils import DataError, get_live_gold_price_usa, isMarketOpen

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:  # pragma: no cover - optional dependency
    gspread = None
    Credentials = None

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LIVE_DATA_FILE = DATA_DIR / "live_1m.csv"
CACHE_TTL_SECONDS = 60
_cache = {"ts": 0.0, "df": None}

# Google Sheets configuration (optional)
SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID") or os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKSHEET", "live_candles")
_sheet = None


def _sheet_enabled() -> bool:
    return bool(SHEETS_ID and gspread and Credentials)


def _get_sheet():
    """Return a Google Sheet worksheet if configured; otherwise raise DataError."""
    global _sheet
    if _sheet is not None:
        return _sheet
    if not _sheet_enabled():
        raise DataError("Google Sheets not configured.")
    info = None
    if GOOGLE_CREDS_JSON:
        info = json.loads(GOOGLE_CREDS_JSON)
    elif GOOGLE_CREDS_FILE:
        cred_path = Path(GOOGLE_CREDS_FILE)
        if not cred_path.exists():
            raise DataError(f"Google credentials file not found at {cred_path}")
        info = json.loads(cred_path.read_text(encoding="utf-8-sig"))
    else:
        raise DataError("Missing Google credentials.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEETS_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="10")
        ws.update("A1:F1", [["timestamp", "open", "high", "low", "close", "volume"]])
    _sheet = ws
    return _sheet


def append_live_price() -> Tuple[Optional[float], Optional[datetime]]:
    now_utc = datetime.now(timezone.utc)
    if not isMarketOpen(now_utc):
        return None, None

    price = get_live_gold_price_usa()
    current_time = datetime.now(ZoneInfo("Asia/Riyadh")).replace(microsecond=0)
    row = [current_time.isoformat(), price, price, price, price, 0]

    if _sheet_enabled():
        try:
            ws = _get_sheet()
            ws.append_row(row, value_input_option="RAW")
            _cache["ts"] = 0.0
            return price, current_time
        except Exception:
            pass  # fallback to local below

    # Local CSV fallback
    row_dict = {"timestamp": row[0], "open": price, "high": price, "low": price, "close": price, "volume": 0}
    if LIVE_DATA_FILE.exists():
        df = pd.read_csv(LIVE_DATA_FILE)
        df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)
    else:
        df = pd.DataFrame([row_dict])
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


def _load_sheet_1m(limit: int = 50000) -> pd.DataFrame:
    ws = _get_sheet()
    rows = ws.get_all_records()
    if not rows:
        raise DataError("No live data collected yet in Google Sheets.")
    df = pd.DataFrame(rows)
    if "timestamp" not in df.columns:
        raise DataError("Timestamp column missing in sheet data.")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    if limit and len(df) > limit:
        df = df.tail(limit)
    return df


def get_live_collected_data(limit: int = 50000, days_back: int = 40):
    now_ts = time.time()
    if _cache["df"] is not None and now_ts - _cache["ts"] < CACHE_TTL_SECONDS:
        return _cache["df"].copy()
    if _sheet_enabled():
        try:
            df = _load_sheet_1m(limit=limit)
        except Exception:
            df = _load_local_1m(limit=limit)
    else:
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


def build_ohlc_from_sheet(limit: int | None = 50000) -> dict[str, pd.DataFrame]:
    """
    Build OHLC candles from the already collected raw data (1-second rows) without any external API.

    Returns:
        {
          "1m": df_1m,
          "5m": df_5m,
          "15m": df_15m,
          "1h": df_1h
        }
    Raises:
        DataError if data is missing or insufficient for any timeframe.
    """
    df = get_live_collected_data(limit=limit)
    if df is None or df.empty:
        raise DataError("No live data available to build OHLC.")

    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
        else:
            raise DataError("Data must have a DatetimeIndex or a 'timestamp' column.")

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    def _resample(rule: str) -> pd.DataFrame:
        candles = (
            df.resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )
        if candles.empty:
            raise DataError(f"Not enough data to build {rule} candles.")
        return candles

    candles_1m = _resample("1T")
    candles_5m = _resample("5T")
    candles_15m = _resample("15T")
    candles_1h = _resample("1H")

    return {"1m": candles_1m, "5m": candles_5m, "15m": candles_15m, "1h": candles_1h}


def get_collection_stats() -> dict:
    df = _cache["df"] if _cache["df"] is not None else _load_local_1m()
    return {
        "rows": len(df),
        "start": df.index[0].isoformat(),
        "end": df.index[-1].isoformat(),
        "latest_price": float(df["close"].iloc[-1]),
    }
