"""
ReversalEngine: detects rejection wicks and POI touches for quick scalper confirmations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from . import pa_utils as se


@dataclass
class ReversalConfig:
    zone_conf_threshold: float = 50.0


class ReversalEngine:
    def __init__(self, config: ReversalConfig | None = None) -> None:
        self.cfg = config or ReversalConfig()

    def wick_rejection(self, candle) -> Dict[str, bool]:
        bull, bear = se._wick_rejection(candle)
        return {"bullish": bull, "bearish": bear}

    def poi_touch(self, price: float, zones: Dict[str, Any], imbalances: Dict[str, Any]) -> Dict[str, bool]:
        demand = zones.get("demand", {}).get("zone")
        supply = zones.get("supply", {}).get("zone")
        demand_conf = zones.get("demand", {}).get("confidence", 0)
        supply_conf = zones.get("supply", {}).get("confidence", 0)
        bull_poi = False
        bear_poi = False
        if demand and demand_conf >= self.cfg.zone_conf_threshold:
            bull_poi = demand["low"] <= price <= demand["high"]
        if supply and supply_conf >= self.cfg.zone_conf_threshold:
            bear_poi = supply["low"] <= price <= supply["high"]

        # FVG/imbalance proximity (lightweight)
        if imbalances.get("bullish") and not bull_poi:
            bull_poi = True
        if imbalances.get("bearish") and not bear_poi:
            bear_poi = True

        return {"bullish_poi": bull_poi, "bearish_poi": bear_poi}
