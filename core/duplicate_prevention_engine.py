"""
DuplicatePreventionEngine: blocks repetitive signals in the same micro-context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DuplicateState:
    last_action: Optional[str] = None
    last_price: Optional[float] = None
    last_time: Optional[Any] = None
    last_structure: Optional[str] = None
    last_sweep: Optional[str] = None
    last_poi: Optional[str] = None
    last_momentum: Optional[str] = None


@dataclass
class DuplicateConfig:
    min_price_delta: float = 0.5  # default tolerance


class DuplicatePreventionEngine:
    def __init__(self, config: DuplicateConfig | None = None) -> None:
        self.cfg = config or DuplicateConfig()
        self.state = DuplicateState()

    def should_block(self, signal: Dict[str, Any], context: Dict[str, Any], price_delta_override: float | None = None) -> bool:
        action = signal.get("action")
        price = signal.get("entry")
        time_idx = context.get("time")
        structure_tag = context.get("structure_tag")
        sweep_tag = context.get("sweep_tag")
        poi_tag = context.get("poi_tag")
        momentum = context.get("momentum")

        s = self.state

        if action in (None, "NO_TRADE"):
            return False

        if s.last_time == time_idx:
            return True
        if s.last_action == action and s.last_structure == structure_tag:
            if s.last_sweep == sweep_tag or s.last_poi == poi_tag:
                return True
        if s.last_action == action and s.last_price is not None and price is not None:
            min_delta = price_delta_override if price_delta_override is not None else self.cfg.min_price_delta
            if abs(float(price) - float(s.last_price)) < min_delta:
                return True
        if s.last_momentum == momentum and s.last_action == action:
            return True

        self.state = DuplicateState(
            last_action=action,
            last_price=price,
            last_time=time_idx,
            last_structure=structure_tag,
            last_sweep=sweep_tag,
            last_poi=poi_tag,
            last_momentum=momentum,
        )
        return False
