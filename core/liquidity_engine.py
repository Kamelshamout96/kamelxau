"""
LiquidityEngine: detects sweeps and liquidity pools above/below current price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from . import pa_utils as se


@dataclass
class LiquidityConfig:
    sweep_lookback_15m: int = 30
    sweep_lookback_5m: int = 20


class LiquidityEngine:
    def __init__(self, config: LiquidityConfig | None = None) -> None:
        self.cfg = config or LiquidityConfig()

    def detect_sweeps(self, df_15m, df_5m) -> Dict[str, Any]:
        return {
            "15m": se._liquidity_sweep(df_15m, lookback=self.cfg.sweep_lookback_15m),
            "5m": se._liquidity_sweep(df_5m, lookback=self.cfg.sweep_lookback_5m),
        }

    def liquidity_pools(self, df_15m, df_5m) -> Dict[str, Any]:
        swings15 = se._local_swings(df_15m, lookback=120, window=2)
        swings5 = se._local_swings(df_5m, lookback=120, window=2)
        highs = [h["price"] for h in swings15.get("highs", []) + swings5.get("highs", [])]
        lows = [l["price"] for l in swings15.get("lows", []) + swings5.get("lows", [])]
        return {"highs": sorted(set(highs)), "lows": sorted(set(lows))}
