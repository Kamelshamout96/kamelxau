"""
POIDetector: detects supply/demand, FVGs/imbalances, simple order blocks, liquidity highs/lows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from . import pa_utils as se


@dataclass
class POIConfig:
    zone_conf_threshold: float = 50.0  # configurable; not hardcoded in logic


class POIDetector:
    def __init__(self, config: POIConfig | None = None) -> None:
        self.cfg = config or POIConfig()

    def detect_zones(self, df_1h) -> Dict[str, Any]:
        return se._detect_zones(df_1h)

    def detect_imbalance(self, df_15m) -> Dict[str, Any]:
        return se._detect_imbalance(df_15m)

    def detect_order_blocks(self, df_1h) -> Dict[str, Any]:
        # Lightweight OB proxy: last engulfing candle on 1H swings
        swings = se._local_swings(df_1h, lookback=60, window=2)
        highs = swings.get("highs", [])
        lows = swings.get("lows", [])
        ob: Dict[str, Any] = {"bullish": None, "bearish": None}
        if len(lows) >= 2:
            last_low = lows[-1]["price"]
            ob["bullish"] = {"low": last_low * 0.998, "high": last_low * 1.002}
        if len(highs) >= 2:
            last_high = highs[-1]["price"]
            ob["bearish"] = {"low": last_high * 0.998, "high": last_high * 1.002}
        return ob

    def detect_liquidity_levels(self, df_15m, df_5m) -> Dict[str, List[float]]:
        highs = [h["price"] for h in se._local_swings(df_15m, lookback=80, window=2).get("highs", [])[-5:]]
        lows = [l["price"] for l in se._local_swings(df_15m, lookback=80, window=2).get("lows", [])[-5:]]
        highs += [h["price"] for h in se._local_swings(df_5m, lookback=80, window=2).get("highs", [])[-5:]]
        lows += [l["price"] for l in se._local_swings(df_5m, lookback=80, window=2).get("lows", [])[-5:]]
        return {"above": sorted(set(highs)), "below": sorted(set(lows))}
