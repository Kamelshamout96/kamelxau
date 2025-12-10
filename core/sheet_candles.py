"""
Utilities to build OHLC candles from the already collected 1-second sheet data.

Relies solely on get_live_collected_data() (no external APIs).
"""

from __future__ import annotations

import pandas as pd

from core.live_data_collector import get_live_collected_data


def _ensure_dt_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
        else:
            raise ValueError("DataFrame must have a DatetimeIndex or a 'timestamp' column.")
    return df.sort_index()


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        df.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )


def build_ohlc_from_sheet(limit: int | None = 50000) -> dict[str, pd.DataFrame]:
    """
    Reads existing 1-second data from get_live_collected_data() and returns OHLC candles.

    Returns:
        {
          "1m": df_1m,
          "5m": df_5m,
          "15m": df_15m,
          "1h": df_1h,
        }
    """
    df = get_live_collected_data(limit=limit)
    df = _ensure_dt_index(df)

    candles = {
        "1m": _resample_ohlc(df, "1min"),
        "5m": _resample_ohlc(df, "5min"),
        "15m": _resample_ohlc(df, "15min"),
        "1h": _resample_ohlc(df, "60min"),
    }
    return candles


# Example usage:
# candles = build_ohlc_from_sheet()
# print(candles["5m"].tail(20))
