"""
BiasEngine: derives daily directional bias (BUY ONLY / SELL ONLY / NEUTRAL)
from HTF (4H, 1H) structure without suppressing LTF execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from . import pa_utils as se


@dataclass
class BiasConfig:
    neutral_bias_label: str = "NEUTRAL"
    buy_bias_label: str = "BUY ONLY"
    sell_bias_label: str = "SELL ONLY"


class BiasEngine:
    def __init__(self, config: BiasConfig | None = None) -> None:
        self.cfg = config or BiasConfig()

    def compute_bias(self, df_4h, df_1h) -> Tuple[str, Dict[str, Any]]:
        struct_4h = se._detect_structure(df_4h, lookback=140, window=3)
        struct_1h = se._detect_structure(df_1h, lookback=140, window=3)

        bias_4h = struct_4h.get("label")
        bias_1h = struct_1h.get("label")

        if bias_4h == "HH-HL" and bias_1h == "HH-HL":
            bias = self.cfg.buy_bias_label
        elif bias_4h == "LH-LL" and bias_1h == "LH-LL":
            bias = self.cfg.sell_bias_label
        else:
            bias = self.cfg.neutral_bias_label

        ctx = {
            "htf_structure": {"4h": struct_4h, "1h": struct_1h},
            "raw_bias": bias,
        }
        return bias, ctx
