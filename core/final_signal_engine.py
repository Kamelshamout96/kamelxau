"""
FinalSignalEngine: orchestrates Stage 1 (analysis/bias) and Stage 2 (execution),
plus duplicate prevention, and emits the final trading signal.
"""

from __future__ import annotations

from typing import Any, Dict

from .bias_engine import BiasEngine
from .duplicate_prevention_engine import DuplicatePreventionEngine
from .liquidity_engine import LiquidityEngine
from .market_analysis_engine import MarketAnalysisEngine
from .poi_detector import POIDetector
from .reversal_engine import ReversalEngine
from .scalper_execution_engine import ScalperExecutionEngine
from .structure_engine import StructureEngine


class FinalSignalEngine:
    def __init__(self) -> None:
        bias_engine = BiasEngine()
        poi_detector = POIDetector()
        structure_engine = StructureEngine()
        liquidity_engine = LiquidityEngine()
        reversal_engine = ReversalEngine()

        self.analysis_engine = MarketAnalysisEngine(bias_engine, poi_detector, structure_engine, liquidity_engine)
        self.scalper_engine = ScalperExecutionEngine(structure_engine, liquidity_engine, reversal_engine)
        self.dup_engine = DuplicatePreventionEngine()

    def run(self, df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
        analysis = self.analysis_engine.analyze(df_5m, df_15m, df_1h, df_4h)
        bias = analysis.bias
        ctx = analysis.context

        signal, exec_ctx = self.scalper_engine.evaluate(
            bias=bias,
            df_5m=df_5m,
            df_15m=df_15m,
            zones=ctx["zones"],
            imbalances=ctx["imbalances"],
            channel_ctx=ctx["channel"],
            liquidity_pools=ctx["pools"],
        )

        block = self.dup_engine.should_block(
            signal,
            {
                "time": df_5m.index[-1] if len(df_5m) else None,
                "structure_tag": exec_ctx.get("structure_tag"),
                "sweep_tag": exec_ctx.get("sweep_tag"),
                "poi_tag": exec_ctx.get("poi_tag"),
                "momentum": exec_ctx.get("sweeps", {}),
            },
        )
        if block:
            return {"action": "NO_TRADE", "reason": "duplicate_block", "analysis": analysis.context}

        if bias == "NEUTRAL" and signal.get("action") in ("BUY", "SELL"):
            signal["action"] = "NO_TRADE"
            signal["reason"] = "bias_neutral"

        signal["trend"] = {
            "4h": ctx["bias_context"]["htf_structure"]["4h"].get("bias", "neutral"),
            "1h": ctx["bias_context"]["htf_structure"]["1h"].get("bias", "neutral"),
            "15m": ctx["structure_shifts"]["15m"].get("direction"),
            "5m": ctx["structure_shifts"]["5m"].get("direction"),
        }
        signal["structure"] = {"bos": ctx["structure_shifts"]["15m"].get("direction") or ctx["structure_shifts"]["5m"].get("direction"), "choch": None, "pattern": ctx["bias_context"]["htf_structure"]["1h"].get("label")}
        sweeps = ctx["sweeps"]
        signal["liquidity"] = {
            "sweep": sweeps["15m"].get("type") or sweeps["5m"].get("type") or "none",
            "levels": ctx["pools"],
        }
        signal["zones"] = ctx["zones"]
        signal["momentum"] = "light"
        signal["channels"] = ctx["channel"]
        signal["reasoning"] = [
            f"Bias: {bias}",
            f"Structure 15m/5m: {ctx['structure_shifts']}",
            f"Sweeps: {sweeps}",
            f"POIs touched: {exec_ctx.get('poi_tag')}",
        ]
        signal["score_breakdown"] = {
            "structure": 20 if exec_ctx.get("structure_tag") else 0,
            "liquidity": 20 if exec_ctx.get("sweep_tag") else 0,
            "zones": 20 if exec_ctx.get("poi_tag") else 0,
            "momentum": 10,
            "channels": 10 if ctx["channel"].get("tap") else 0,
            "htf_context": 20 if bias != "NEUTRAL" else 0,
        }

        return signal
