"""
ScalperExecutionEngine: executes 5m scalps aligned with the daily bias.
Requires only one confirmation (sweep or wick) plus POI touch and BOS/CHOCH.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .reversal_engine import ReversalEngine
from .structure_engine import StructureEngine
from .liquidity_engine import LiquidityEngine


@dataclass
class ScalperConfig:
    min_confidence: float = 60.0  # configurable floor for reporting


class ScalperExecutionEngine:
    def __init__(
        self,
        structure_engine: StructureEngine,
        liquidity_engine: LiquidityEngine,
        reversal_engine: ReversalEngine,
        config: ScalperConfig | None = None,
    ) -> None:
        self.struct_engine = structure_engine
        self.liq_engine = liquidity_engine
        self.rev_engine = reversal_engine
        self.cfg = config or ScalperConfig()

    def evaluate(
        self,
        bias: str,
        df_5m,
        df_15m,
        zones: Dict[str, Any],
        imbalances: Dict[str, Any],
        channel_ctx: Dict[str, Any],
        liquidity_pools: Dict[str, Any],
        breakout_hh: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        last5 = df_5m.iloc[-1]
        price = float(last5["close"])
        if breakout_hh:
            entry = round(price, 2)
            signal = {
                "action": "NO_TRADE",
                "reason": "blocked_breakout_up",
                "entry": entry,
                "sl": None,
                "tp": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
                "confidence": 0.0,
            }
            ctx = {
                "structure": {},
                "sweeps": {},
                "wick": {},
                "poi_touch": {},
                "structure_tag": None,
                "sweep_tag": None,
                "poi_tag": None,
                "breakout_hh": True,
            }
            return signal, ctx

        sweeps = self.liq_engine.detect_sweeps(df_15m, df_5m)
        structure = self.struct_engine.detect_structure_shifts(df_15m, df_5m)
        wick = self.rev_engine.wick_rejection(last5)
        poi_touch = self.rev_engine.poi_touch(price, zones, imbalances)

        structure_tag = f"15m:{structure['15m'].get('direction')}|5m:{structure['5m'].get('direction')}"
        sweep_tag = sweeps["15m"].get("type") or sweeps["5m"].get("type")
        poi_tag = "bull" if poi_touch["bullish_poi"] else ("bear" if poi_touch["bearish_poi"] else None)

        action = "NO_TRADE"
        sl = tp = tp1 = tp2 = tp3 = None

        if bias == "BUY ONLY":
            confirmed = poi_touch["bullish_poi"] and (
                sweeps["5m"].get("type") == "below"
                or sweeps["15m"].get("type") == "below"
                or wick["bullish"]
            )
            bos_ok = structure["5m"].get("direction") == "bullish" or structure["15m"].get("direction") == "bullish"
            if confirmed and bos_ok:
                action = "BUY"
        elif bias == "SELL ONLY":
            confirmed = poi_touch["bearish_poi"] and (
                sweeps["5m"].get("type") == "above"
                or sweeps["15m"].get("type") == "above"
                or wick["bearish"]
            )
            bos_ok = structure["5m"].get("direction") == "bearish" or structure["15m"].get("direction") == "bearish"
            if confirmed and bos_ok:
                action = "SELL"

        entry = float(df_5m["close"].iloc[-1])

        if action in ("BUY", "SELL"):
            atr = None
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

            if action == "BUY":
                sl_raw = entry - (atr * 2.5)
                sl_hard = entry - 10
                sl = min(sl_raw, sl_hard)
                tp1 = entry + (atr * 1.0)
                tp2 = entry + (atr * 1.6)
                tp3 = entry + (atr * 2.2)
                tp = tp1

            elif action == "SELL":
                sl_raw = entry + (atr * 2.5)
                sl_hard = entry + 10
                sl = max(sl_raw, sl_hard)
                tp1 = entry - (atr * 1.0)
                tp2 = entry - (atr * 1.6)
                tp3 = entry - (atr * 2.2)
                tp = tp1

        confidence = self.cfg.min_confidence if action in ("BUY", "SELL") else 0.0

        signal = {
            "action": action,
            "entry": round(entry, 2),
            "sl": round(sl, 2) if sl else None,
            "tp": round(tp, 2) if tp else None,
            "tp1": round(tp1, 2) if tp1 else None,
            "tp2": round(tp2, 2) if tp2 else None,
            "tp3": round(tp3, 2) if tp3 else None,
            "confidence": confidence,
        }

        ctx = {
            "structure": structure,
            "sweeps": sweeps,
            "wick": wick,
            "poi_touch": poi_touch,
            "structure_tag": structure_tag,
            "sweep_tag": sweep_tag,
            "poi_tag": poi_tag,
            "breakout_hh": breakout_hh,
        }

        return signal, ctx
