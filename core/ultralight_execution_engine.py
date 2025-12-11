"""
UltraLightExecutionEngine: lightweight execution when Stage2 and fallback refuse,
leveraging discretionary conviction to still act.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd


class UltraLightExecutionEngine:
    def __init__(self) -> None:
        pass

    @staticmethod
    def _atr_14(df: pd.DataFrame) -> float:
        tr = np.maximum.reduce(
            [
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ]
        )
        return float(pd.Series(tr, index=df.index).rolling(14).mean().iloc[-1])

    def _get_atr(self, df_5m, ctx: Dict[str, Any]) -> float:
        indicators = ctx.get("indicators", {}) if ctx else {}
        atr = indicators.get("atr_5m")
        if atr:
            try:
                return float(atr)
            except Exception:
                atr = None

        for col in ("atr", "atr_14", "ATR", "ATR_14"):
            if col in df_5m.columns:
                try:
                    return float(df_5m[col].iloc[-1])
                except Exception:
                    continue

        return self._atr_14(df_5m)

    def _confidence(self, trend_direction: str, bias: str | None) -> int:
        strong_bull = trend_direction in ("bullish", "expanding")
        strong_bear = trend_direction in ("bearish", "compressing")
        if strong_bull and bias == "BUY ONLY":
            return 55
        if strong_bear and bias == "SELL ONLY":
            return 55
        return 40

    def _calc_levels(self, price: float, atr: float, side: str) -> Tuple[float, float, float, float]:
        if side == "BUY":
            sl = price - max(atr * 1.8, 10.0)
            tp1 = price + max(atr * 1.2, 8.0)
            tp2 = price + max(atr * 1.8, 12.0)
            tp3 = price + max(atr * 2.4, 16.0)
        else:
            sl = price + max(atr * 1.8, 10.0)
            tp1 = price - max(atr * 1.2, 8.0)
            tp2 = price - max(atr * 1.8, 12.0)
            tp3 = price - max(atr * 2.4, 16.0)
        return (
            round(sl, 2),
            round(tp1, 2),
            round(tp2, 2),
            round(tp3, 2),
        )

    def evaluate(
        self,
        df_5m,
        df_15m,
        ctx: Dict[str, Any],
        discretionary_ctx: Dict[str, Any],
        bias: str | None = None,
    ) -> Dict[str, Any]:
        action = "NO_TRADE"
        if df_5m is None or len(df_5m) == 0 or not ctx:
            return {"action": action, "reason": "invalid_context"}

        trend_direction = discretionary_ctx.get("trend_direction")
        zone_type = discretionary_ctx.get("zone_type")
        reaction = discretionary_ctx.get("reaction")
        momentum_bias = discretionary_ctx.get("momentum_bias", "weak")
        htf_bias = bias or ctx.get("bias_context", {}).get("raw_bias") or ctx.get("bias")

        price = float(df_5m.iloc[-1]["close"])
        zones = ctx.get("zones", {})
        demand_zone = zones.get("demand", {}).get("zone")
        supply_zone = zones.get("supply", {}).get("zone")

        def _inside(zone: Dict[str, Any] | None) -> bool:
            return bool(zone and zone.get("low") is not None and zone.get("high") is not None and zone["low"] <= price <= zone["high"])

        atr = self._get_atr(df_5m, ctx)
        bias_ok_buy = htf_bias in ("BUY ONLY", "NEUTRAL")
        bias_ok_sell = htf_bias in ("SELL ONLY", "NEUTRAL")

        if (
            trend_direction in ("bullish", "expanding")
            and zone_type == "demand"
            and reaction in ("rejection", "absorption")
            and _inside(demand_zone)
            and momentum_bias != "weak"
            and bias_ok_buy
        ):
            action = "BUY"
        elif (
            trend_direction in ("bearish", "compressing")
            and zone_type == "supply"
            and reaction in ("rejection", "absorption")
            and _inside(supply_zone)
            and momentum_bias != "weak"
            and bias_ok_sell
        ):
            action = "SELL"

        if action not in ("BUY", "SELL"):
            return {"action": "NO_TRADE", "reason": "ultralight_filters_not_met"}

        sl, tp1, tp2, tp3 = self._calc_levels(price, atr, action)
        confidence = self._confidence(trend_direction, htf_bias)

        return {
            "action": action,
            "entry": round(price, 2),
            "sl": sl,
            "tp": tp1,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "confidence": confidence,
            "reason": "ultralight_mode",
            "source": "UltraLightExecutionEngine",
        }
