"""
FinalSignalEngine: orchestrates Stage 1 (analysis/bias) and Stage 2 (execution),
plus decision aggregation, duplicate prevention, fallback light mode, and emits the final trading signal.
"""

from __future__ import annotations

from typing import Any, Dict
from datetime import timedelta

from .bias_engine import BiasEngine
from .duplicate_prevention_engine import DuplicatePreventionEngine
from .discretionary_layer import DiscretionaryLayer
from .liquidity_engine import LiquidityEngine
from .market_analysis_engine import MarketAnalysisEngine
from .poi_detector import POIDetector
from .reversal_engine import ReversalEngine
from .scalper_execution_engine import ScalperExecutionEngine
from .structure_engine import StructureEngine
from .ultralight_execution_engine import UltraLightExecutionEngine
from .momentum_breakout_layer import MomentumBreakoutLayer
from .momentum_breakout_buy_engine import MomentumBreakoutBuyEngine
from .price_action_analyst_layer import PriceActionAnalystLayer
from .human_scalper_layer import HumanScalperLayer


class FinalSignalEngine:
    def __init__(self) -> None:
        bias_engine = BiasEngine()
        poi_detector = POIDetector()
        structure_engine = StructureEngine()
        liquidity_engine = LiquidityEngine()
        reversal_engine = ReversalEngine()

        self.analysis_engine = MarketAnalysisEngine(bias_engine, poi_detector, structure_engine, liquidity_engine)
        self.scalper_engine = ScalperExecutionEngine(structure_engine, liquidity_engine, reversal_engine)
        self.discretionary_layer = DiscretionaryLayer()
        self.ultralight_engine = UltraLightExecutionEngine()
        self.mbl = MomentumBreakoutLayer()
        self.breakout_buy_engine = MomentumBreakoutBuyEngine()
        self.price_action_layer = PriceActionAnalystLayer()
        self.human_scalper = HumanScalperLayer()
        self.dup_engine = DuplicatePreventionEngine()
        self.last_signal_time = None
        self.session_direction = None
        self.session_day = None
        self.last_structure_direction = None
        self.fallback_timeout = timedelta(minutes=15)
        self.fallback_timeout_light = timedelta(minutes=2)
        self.layer_weights = {
            "scalper": 1.0,
            "breakout_buy": 0.65,
            "discretionary": 0.7,
            "price_action": 0.8,
            "momentum_breakout": 0.75,
            "human_scalper": 0.85,
            "ultralight": 0.6,
            "fallback_light": 0.5,
        }
        self.duplicate_bands = {
            "human_scalper": 2.0,
            "price_action": 0.4,
            "momentum_breakout": 0.4,
            "ultralight": 0.3,
            "fallback_light": 0.2,
            "default": 0.6,
        }

    def run(self, df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
        analysis = self.analysis_engine.analyze(df_5m, df_15m, df_1h, df_4h)
        bias = analysis.bias
        ctx = analysis.context
        ctx["momentum"] = ctx.get("momentum", "unknown")
        breakout_filter_active = ctx.get("breakout_hh", False)
        last_time = df_5m.index[-1] if len(df_5m) else None
        self._reset_session(last_time)

        signal_pool, discretionary_ctx = self._collect_candidates(
            df_5m=df_5m,
            df_15m=df_15m,
            ctx=ctx,
            bias=bias,
            breakout_filter_active=breakout_filter_active,
            last_time=last_time,
            analysis_ctx=analysis.context,
        )

        if not signal_pool:
            return {"action": "NO_TRADE", "reason": "no_candidate", "analysis": analysis.context, "discretionary_context": discretionary_ctx}

        final_candidate = self._rank_and_select(signal_pool, bias, breakout_filter_active, ctx)
        if final_candidate is None:
            return {"action": "NO_TRADE", "reason": "duplicate_block", "analysis": analysis.context, "discretionary_context": discretionary_ctx}

        signal = final_candidate["signal"]
        exec_ctx = final_candidate.get("exec_ctx", {})
        sweeps = ctx["sweeps"]

        signal["trend"] = {
            "4h": ctx["bias_context"]["htf_structure"]["4h"].get("bias", "neutral"),
            "1h": ctx["bias_context"]["htf_structure"]["1h"].get("bias", "neutral"),
            "15m": ctx["structure_shifts"]["15m"].get("direction"),
            "5m": ctx["structure_shifts"]["5m"].get("direction"),
        }
        signal["structure"] = {
            "bos": ctx["structure_shifts"]["15m"].get("direction") or ctx["structure_shifts"]["5m"].get("direction"),
            "choch": None,
            "pattern": ctx["bias_context"]["htf_structure"]["1h"].get("label"),
        }
        signal["liquidity"] = {
            "sweep": sweeps["15m"].get("type") or sweeps["5m"].get("type") or "none",
            "levels": ctx["pools"],
        }
        signal["zones"] = ctx["zones"]
        signal["momentum"] = ctx.get("momentum", "light")
        signal["channels"] = ctx["channel"]
        reasoning = [
            f"Bias: {bias}",
            f"Selected layer: {final_candidate.get('layer')}",
            f"Score: {round(final_candidate.get('score', 0), 3)}",
            f"Structure 15m/5m: {ctx['structure_shifts']}",
            f"Sweeps: {sweeps}",
            f"POIs touched: {exec_ctx.get('poi_tag')}",
        ]
        if breakout_filter_active and signal.get("action") == "SELL":
            reasoning.append("Breakout filter active: SELL soft-penalized")
        if signal.get("reason") == "momentum_breakout":
            reasoning.append("Momentum Breakout Layer active: high-momentum continuation entry")
        if signal.get("reason") and "bias_neutral_soft" in signal.get("reason"):
            reasoning.append("Bias neutral: confidence/TP trimmed")
        signal["reasoning"] = reasoning
        signal["score_breakdown"] = {
            "structure": 20 if exec_ctx.get("structure_tag") else 0,
            "liquidity": 20 if exec_ctx.get("sweep_tag") else 0,
            "zones": 20 if exec_ctx.get("poi_tag") else 0,
            "momentum": 10,
            "channels": 10 if ctx["channel"].get("tap") else 0,
            "htf_context": 20 if bias != "NEUTRAL" else 10,
            "layer_weight": int(self.layer_weights.get(final_candidate.get("layer"), 0) * 10),
        }
        signal["discretionary_context"] = discretionary_ctx

        if signal.get("action") in ("BUY", "SELL") and len(df_5m):
            self.last_signal_time = df_5m.index[-1]
            self.session_direction = signal.get("action")
            self.last_structure_direction = ctx["structure_shifts"]["15m"].get("direction") or ctx["structure_shifts"]["5m"].get("direction")

        return signal

    def _rank_and_select(self, signal_pool, bias, breakout_filter_active, ctx):
        scored_pool = []
        for candidate in signal_pool:
            sig = self._apply_bias_softening(candidate["signal"], bias)
            if breakout_filter_active and sig.get("action") == "SELL":
                sig["breakout_penalty"] = True
            candidate = {**candidate, "signal": sig}

            if self.session_direction and sig.get("action") in ("BUY", "SELL"):
                if sig["action"] != self.session_direction and not self._allow_direction_flip(ctx):
                    continue

            candidate["score"] = self._score_candidate(
                sig,
                candidate.get("context", {}),
                candidate.get("exec_ctx", {}),
                candidate.get("layer"),
                breakout_filter_active,
            )
            scored_pool.append(candidate)

        if not scored_pool:
            return None

        scored_pool.sort(key=lambda c: c.get("score", 0), reverse=True)
        for candidate in scored_pool:
            sig = candidate["signal"]
            ctx_candidate = candidate.get("context", {})
            price_band = self.duplicate_bands.get(candidate.get("layer"), self.duplicate_bands["default"])
            if not self.dup_engine.should_block(sig, ctx_candidate, price_delta_override=price_band):
                return candidate
        return None

    def _apply_bias_softening(self, signal: Dict[str, Any], bias: str) -> Dict[str, Any]:
        if bias != "NEUTRAL" or signal.get("action") not in ("BUY", "SELL"):
            return signal
        softened = signal.copy()
        softened["confidence"] = round(softened.get("confidence", 0) * 0.7, 1)
        for tp_key in ("tp", "tp1", "tp2", "tp3"):
            if softened.get(tp_key) is not None:
                softened[tp_key] = round(float(softened[tp_key]) * 0.8, 2)
        reason = softened.get("reason") or ""
        tag = "bias_neutral_soft"
        softened["reason"] = f"{reason}; {tag}" if reason else tag
        return softened

    def _allow_direction_flip(self, ctx: Dict[str, Any]) -> bool:
        structure_dir = ctx["structure_shifts"]["15m"].get("direction") or ctx["structure_shifts"]["5m"].get("direction")
        if structure_dir and self.last_structure_direction and structure_dir != self.last_structure_direction:
            return True
        return False

    def _score_candidate(
        self,
        signal: Dict[str, Any],
        context: Dict[str, Any],
        exec_ctx: Dict[str, Any],
        layer: str,
        breakout_filter_active: bool,
    ) -> float:
        score = self.layer_weights.get(layer, 0.5)
        if context.get("structure_tag"):
            score += 0.2
        if context.get("sweep_tag"):
            score += 0.2
        if context.get("poi_tag"):
            score += 0.2
        if context.get("momentum") and context.get("momentum") != "weak":
            score += 0.1
        score += min(signal.get("confidence", 0) / 150.0, 0.6)
        if breakout_filter_active and signal.get("action") == "SELL":
            score -= 0.4
        return round(score, 4)

    def _reset_session(self, last_time: Any) -> None:
        if last_time is None:
            return
        try:
            day = last_time.date()
        except Exception:
            return
        if self.session_day != day:
            self.session_day = day
            self.session_direction = None
            self.last_structure_direction = None

    def _collect_candidates(self, df_5m, df_15m, ctx, bias, breakout_filter_active, last_time, analysis_ctx):
        signal_pool = []
        discretionary_ctx: Dict[str, Any] = {}

        signal, exec_ctx = self.scalper_engine.evaluate(
            bias=bias,
            df_5m=df_5m,
            df_15m=df_15m,
            zones=ctx["zones"],
            imbalances=ctx["imbalances"],
            channel_ctx=ctx["channel"],
            liquidity_pools=ctx["pools"],
            breakout_hh=ctx.get("breakout_hh", False),
        )
        if signal.get("action") in ("BUY", "SELL"):
            signal_pool.append(
                {
                    "signal": signal,
                    "exec_ctx": exec_ctx,
                    "context": {
                        "time": last_time,
                        "structure_tag": exec_ctx.get("structure_tag"),
                        "sweep_tag": exec_ctx.get("sweep_tag"),
                        "poi_tag": exec_ctx.get("poi_tag"),
                        "momentum": ctx.get("momentum", "unknown"),
                    },
                    "layer": "scalper",
                }
            )

        bo_signal = self.breakout_buy_engine.evaluate(df_5m, ctx, analysis_ctx.get("discretionary_context", {}))
        if bo_signal and bo_signal.get("action") in ("BUY", "SELL"):
            signal_pool.append(
                {
                    "signal": bo_signal,
                    "exec_ctx": {
                        "structure": ctx["structure_shifts"],
                        "sweeps": ctx["sweeps"],
                        "wick": {},
                        "poi_touch": {},
                        "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                        "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                        "poi_tag": "breakout",
                        "breakout_hh": breakout_filter_active,
                    },
                    "context": {
                        "time": last_time,
                        "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                        "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                        "poi_tag": "breakout",
                        "momentum": analysis_ctx.get("discretionary_context", {}).get("momentum_bias"),
                    },
                    "layer": "breakout_buy",
                }
            )

        quiet_enough = last_time is not None and (self.last_signal_time is None or (last_time - self.last_signal_time) >= self.fallback_timeout_light)
        if quiet_enough:
            fb_signal, fb_exec_ctx, fb_context = self._build_fallback_signal(df_5m, ctx, bias, breakout_filter_active, last_time)
            if fb_signal:
                signal_pool.append({"signal": fb_signal, "exec_ctx": fb_exec_ctx, "context": fb_context, "layer": "fallback_light"})

        if len(df_5m) >= 30:
            discretionary_ctx = self.discretionary_layer.analyze(df_5m, analysis_ctx)
            disc_signal = (discretionary_ctx.get("signal") or {}) if discretionary_ctx else {}
            if disc_signal.get("action") in ("BUY", "SELL"):
                disc_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                    "poi_tag": discretionary_ctx.get("zone_type"),
                    "momentum": ctx.get("momentum", "unknown"),
                }
                signal_pool.append(
                    {
                        "signal": disc_signal,
                        "exec_ctx": {
                            "structure": ctx["structure_shifts"],
                            "sweeps": ctx["sweeps"],
                            "wick": {},
                            "poi_touch": {},
                            "structure_tag": disc_context["structure_tag"],
                            "sweep_tag": disc_context["sweep_tag"],
                            "poi_tag": disc_context["poi_tag"],
                            "breakout_hh": breakout_filter_active,
                        },
                        "context": disc_context,
                        "layer": "discretionary",
                    }
                )

            pa_signal = self.price_action_layer.evaluate(
                df_5m=df_5m,
                ctx=analysis_ctx,
                discretionary_ctx=discretionary_ctx,
                bias=bias,
                breakout_filter_active=breakout_filter_active,
            )
            if pa_signal.get("action") in ("BUY", "SELL"):
                pa_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                    "poi_tag": "price_action",
                    "momentum": ctx.get("momentum", "unknown"),
                }
                signal_pool.append(
                    {
                        "signal": pa_signal,
                        "exec_ctx": {
                            "structure": ctx["structure_shifts"],
                            "sweeps": ctx["sweeps"],
                            "wick": {},
                            "poi_touch": {},
                            "structure_tag": pa_context["structure_tag"],
                            "sweep_tag": pa_context["sweep_tag"],
                            "poi_tag": pa_context["poi_tag"],
                            "breakout_hh": breakout_filter_active,
                        },
                        "context": pa_context,
                        "layer": "price_action",
                    }
                )

            mbl_signal = self.mbl.evaluate(
                df_5m=df_5m,
                ctx=analysis_ctx,
                discretionary_ctx=discretionary_ctx,
                bias=bias,
                breakout_filter_active=breakout_filter_active,
            )
            if mbl_signal.get("action") in ("BUY", "SELL"):
                mbl_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                    "poi_tag": discretionary_ctx.get("zone_type"),
                    "momentum": ctx.get("momentum", "unknown"),
                }
                signal_pool.append(
                    {
                        "signal": mbl_signal,
                        "exec_ctx": {
                            "structure": ctx["structure_shifts"],
                            "sweeps": ctx["sweeps"],
                            "wick": {},
                            "poi_touch": {},
                            "structure_tag": mbl_context["structure_tag"],
                            "sweep_tag": mbl_context["sweep_tag"],
                            "poi_tag": mbl_context["poi_tag"],
                            "breakout_hh": breakout_filter_active,
                        },
                        "context": mbl_context,
                        "layer": "momentum_breakout",
                    }
                )

            human_signal = self.human_scalper.evaluate(
                df_5m=df_5m,
                df_15m=df_15m,
                ctx=analysis_ctx,
                bias=bias,
            )
            if breakout_filter_active and human_signal.get("action") == "SELL":
                human_signal = {}
            if human_signal.get("action") in ("BUY", "SELL"):
                human_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                    "poi_tag": "human_scalper",
                    "momentum": ctx.get("momentum", "unknown"),
                }
                signal_pool.append(
                    {
                        "signal": human_signal,
                        "exec_ctx": {
                            "structure": ctx["structure_shifts"],
                            "sweeps": ctx["sweeps"],
                            "wick": {},
                            "poi_touch": {},
                            "structure_tag": human_context["structure_tag"],
                            "sweep_tag": human_context["sweep_tag"],
                            "poi_tag": human_context["poi_tag"],
                            "breakout_hh": breakout_filter_active,
                        },
                        "context": human_context,
                        "layer": "human_scalper",
                    }
                )

            ultra_signal = self.ultralight_engine.evaluate(
                df_5m=df_5m,
                df_15m=df_15m,
                ctx=analysis_ctx,
                discretionary_ctx=discretionary_ctx,
                bias=bias,
            )
            if breakout_filter_active and ultra_signal.get("action") == "SELL":
                ultra_signal = {}
            if ultra_signal.get("action") in ("BUY", "SELL"):
                ultra_context = {
                    "time": last_time,
                    "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
                    "sweep_tag": ctx["sweeps"]["5m"].get("type"),
                    "poi_tag": discretionary_ctx.get("zone_type"),
                    "momentum": ctx.get("momentum", "unknown"),
                }
                signal_pool.append(
                    {
                        "signal": ultra_signal,
                        "exec_ctx": {
                            "structure": ctx["structure_shifts"],
                            "sweeps": ctx["sweeps"],
                            "wick": {},
                            "poi_touch": {},
                            "structure_tag": ultra_context["structure_tag"],
                            "sweep_tag": ultra_context["sweep_tag"],
                            "poi_tag": ultra_context["poi_tag"],
                            "breakout_hh": breakout_filter_active,
                        },
                        "context": ultra_context,
                        "layer": "ultralight",
                    }
                )

        return signal_pool, discretionary_ctx

    def _build_fallback_signal(self, df_5m, ctx, bias, breakout_filter_active, last_time):
        if not len(df_5m):
            return None, None, None
        price = float(df_5m.iloc[-1]["close"])
        last_candle = df_5m.iloc[-1]
        sweeps_ctx = ctx["sweeps"]
        zones_ctx = ctx["zones"]
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
        elif (
            _in_zone(supply_zone)
            and bearish_candle
            and not bull_sweep
            and momentum_ok
            and bias in ("SELL ONLY", "NEUTRAL")
            and not breakout_filter_active
        ):
            action_fb = "SELL"
            sl_raw = price + (atr * 2.5)
            sl_hard = price + 10
            sl = max(sl_raw, sl_hard)

            tp1 = price - (atr * 1.0)
            tp2 = price - (atr * 1.6)
            tp3 = price - (atr * 2.2)

        if action_fb not in ("BUY", "SELL"):
            return None, None, None

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
            "layer": "fallback_light",
        }
        fb_context = {
            "time": last_time,
            "structure_tag": ctx["structure_shifts"]["5m"].get("direction"),
            "sweep_tag": sweeps_ctx["5m"].get("type"),
            "poi_tag": "bull" if action_fb == "BUY" else "bear",
            "momentum": momentum_state,
        }
        fb_exec_ctx = {
            "structure": ctx["structure_shifts"],
            "sweeps": sweeps_ctx,
            "wick": {},
            "poi_touch": {},
            "structure_tag": fb_context["structure_tag"],
            "sweep_tag": fb_context["sweep_tag"],
            "poi_tag": fb_context["poi_tag"],
            "breakout_hh": breakout_filter_active,
        }
        return fb_signal, fb_exec_ctx, fb_context
