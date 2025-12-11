"""
StructureEngine: detects BOS/CHOCH on 15m/5m and channel/premium-discount context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from . import pa_utils as se


@dataclass
class StructureConfig:
    channel_lookback: int = 60


class StructureEngine:
    def __init__(self, config: StructureConfig | None = None) -> None:
        self.cfg = config or StructureConfig()

    def detect_structure_shifts(self, df_15m, df_5m) -> Dict[str, Any]:
        return {
            "15m": se._detect_bos_choch(df_15m, "15m"),
            "5m": se._detect_bos_choch(df_5m, "5m"),
        }

    def channel_context(self, df_1h, price: float) -> Dict[str, Any]:
        return se._detect_channel_context(df_1h, price)

    def premium_discount(self, price: float, bounds: Dict[str, Any]) -> str:
        if not bounds:
            return "unknown"
        upper = bounds.get("upper")
        lower = bounds.get("lower")
        if upper is None or lower is None:
            return "unknown"
        mid = (upper + lower) / 2
        return "premium" if price >= mid else "discount"

    def higher_high_breakout(self, df_5m, price: float) -> Dict[str, Any]:
        """
        Detect a higher-high breakout using the latest swing high on 5m data.
        """
        return se._detect_hh_breakout(df_5m, price, buffer=0.5)
