"""
FinalSignalEngine: orchestrates Stage 1 (analysis/bias) and Stage 2 (execution),
plus duplicate prevention, fallback light mode, and emits the final trading signal.
"""

from __future__ import annotations

from typing import Any, Dict
from datetime import timedelta

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
        self.last_signal_time = None
        self.fallback_timeout = timedelta(minutes=15)
        self.fallback_timeout_light = timedelta(minutes=2)

    def run(self, df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
        analysis = self.analysis_engine.analyze(df_5m, df_15m, df_1h, df_4h)
        bias = analysis.bias
        ctx = analysis.context
        ctx["momentum"] = ctx.get("momentum", "unknown")

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
                "momentum": ctx.get("momentum", "unknown"),
            },
        )
        if block:
            return {"action": "NO_TRADE", "reason": "duplicate_block", "analysis": analysis.context}

        force_fallback = False
        last_time = df_5m.index[-1] if len(df_5m) else None
        if signal.get("action") == "NO_TRADE" and last_time is not None:
            if self.last_signal_time is None or (last_time - self.last_signal_time) >= self.fallback_timeout_light:
                force_fallback = True

        # Only block primary BUY/SELL when bias is neutral
        if not force_fallback:
            if bias == "NEUTRAL" and signal.get("action") in ("BUY", "SELL"):
                signal["action"] = "NO_TRADE"
                signal["reason"] = "bias_neutral"

        if force_fallback and signal.get("action") == "NO_TRADE" and last_time is not None:
            price = float(df_5m.iloc[-1]["close"])
            last_candle = df_5m.iloc[-1]
            sweeps_ctx = ctx["sweeps"]
            zones_ctx = ctx["zones"]
            pools = ctx["pools"]
            momentum_state = ctx.get("momentum", "unknown")
            momentum_ok = momentum_state != "weak"

            def _in_zone(zone):
                return zone and zone.get("low") is not None and zone.get("high") is not None and zone["low"] <= price <= zone["high"]

            demand_zone = zones_ctx.get("demand", {}).get("zone")
            supply_zone = zones_ctx.get("supply", {}).get("zone")
            bullish_candle = float(last_candle["close"]) > float(last_candle["open"])
            bearish_candle = float(last_candle["close"]) < float(last_candle["open"])
            bear_sweep = sweeps_ctx["5m"].get("type") == "above"
            bull_sweep = sweeps_ctx["5m"].get("type") == "below"

            action_fb = "NO_TRADE"
            sl = tp1 = tp2 = tp3 = None
            atr = ctx.get("indicators", {}).get("atr_5m")
            if not atr:
                for col in ("atr", "atr_14", "ATR", "ATR_14"):
                    if col in df_5m.columns:
                        try:
                            atr = float(df_5m[col].iloc[-1])
                            break
                        except Exception:
                            atr = None
            if atr is None:
                import numpy as np
                import pandas as pd

                def _atr14(df):
                    tr = np.maximum.reduce(
                        [
                            df["high"] - df["low"],
                            (df["high"] - df["close"].shift(1)).abs(),
                            (df["low"] - df["close"].shift(1)).abs(),
                        ]
                    )
                    return pd.Series(tr, index=df.index).rolling(14).mean().iloc[-1]

                atr = float(_atr14(df_5m))

            atr = float(atr)

            if _in_zone(demand_zone) and bullish_candle and not bear_sweep and momentum_ok and bias in ("BUY ONLY", "NEUTRAL"):
                action_fb = "BUY"
                sl_raw = price - (atr * 2.5)
                sl_hard = price - 10
                sl = min(sl_raw, sl_hard)

                tp1 = price + (atr * 1.0)
                tp2 = price + (atr * 1.6)
                tp3 = price + (atr * 2.2)
            elif _in_zone(supply_zone) and bearish_candle and not bull_sweep and momentum_ok and bias in ("SELL ONLY", "NEUTRAL"):
                action_fb = "SELL"
                sl_raw = price + (atr * 2.5)
                sl_hard = price + 10
                sl = max(sl_raw, sl_hard)

                tp1 = price - (atr * 1.0)
                tp2 = price - (atr * 1.6)
                tp3 = price - (atr * 2.2)

            if action_fb in ("BUY", "SELL"):
                fb_signal = {
                    "action": action_fb,
                    "entry": round(price, 2),
                    "sl": round(sl, 2) if sl else None,
                    "tp": round(tp1, 2) if tp1 else None,
                    "tp1": round(tp1, 2) if tp1 else None,
                    "tp2": round(tp2, 2) if tp2 else None,
                    "tp3": round(tp3, 2) if tp3 else None,
                    "confidence": 45,
                    "reason": "fallback_light_mode",
                }
                fb_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": sweeps_ctx["5m"].get("type"),
                    "poi_tag": "bull" if action_fb == "BUY" else "bear",
                    "momentum": momentum_state,
                }
                block_fb = self.dup_engine.should_block(fb_signal, fb_context, price_delta_override=0.2)
                if block_fb:
                    return {"action": "NO_TRADE", "reason": "duplicate_block", "analysis": analysis.context}
                signal = fb_signal
                exec_ctx = {
                    "structure": ctx["structure_shifts"],
                    "sweeps": sweeps_ctx,
                    "wick": {},
                    "poi_touch": {},
                    "structure_tag": fb_context["structure_tag"],
                    "sweep_tag": fb_context["sweep_tag"],
                    "poi_tag": fb_context["poi_tag"],
                }

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

        if signal.get("action") in ("BUY", "SELL") and len(df_5m):
            self.last_signal_time = df_5m.index[-1]

        return signal
