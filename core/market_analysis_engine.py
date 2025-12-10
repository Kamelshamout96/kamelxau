"""
MarketAnalysisEngine: Stage 1 analysis to derive bias and POIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .bias_engine import BiasEngine
from .poi_detector import POIDetector
from .structure_engine import StructureEngine
from .liquidity_engine import LiquidityEngine


@dataclass
class MarketAnalysisResult:
    bias: str
    context: Dict[str, Any]


class MarketAnalysisEngine:
    def __init__(
        self,
        bias_engine: BiasEngine,
        poi_detector: POIDetector,
        structure_engine: StructureEngine,
        liquidity_engine: LiquidityEngine,
    ) -> None:
        self.bias_engine = bias_engine
        self.poi_detector = poi_detector
        self.structure_engine = structure_engine
        self.liquidity_engine = liquidity_engine

    def analyze(self, df_5m, df_15m, df_1h, df_4h) -> MarketAnalysisResult:
        bias, bias_ctx = self.bias_engine.compute_bias(df_4h, df_1h)
        zones = self.poi_detector.detect_zones(df_1h)
        imbalances = self.poi_detector.detect_imbalance(df_15m)
        order_blocks = self.poi_detector.detect_order_blocks(df_1h)
        liquidity_levels = self.poi_detector.detect_liquidity_levels(df_15m, df_5m)
        sweeps = self.liquidity_engine.detect_sweeps(df_15m, df_5m)
        shifts = self.structure_engine.detect_structure_shifts(df_15m, df_5m)
        channel = self.structure_engine.channel_context(df_1h, float(df_5m.iloc[-1]["close"]))
        prem_disc = self.structure_engine.premium_discount(float(df_5m.iloc[-1]["close"]), channel.get("bounds", {}))
        pools = self.liquidity_engine.liquidity_pools(df_15m, df_5m)

        ctx: Dict[str, Any] = {
            "zones": zones,
            "imbalances": imbalances,
            "order_blocks": order_blocks,
            "liquidity_levels": liquidity_levels,
            "sweeps": sweeps,
            "structure_shifts": shifts,
            "channel": channel,
            "premium_discount": prem_disc,
            "pools": pools,
            "bias_context": bias_ctx,
        }
        return MarketAnalysisResult(bias=bias, context=ctx)
