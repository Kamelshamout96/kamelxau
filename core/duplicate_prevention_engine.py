"""
DuplicatePreventionEngine: blocks repetitive signals in the same micro-context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
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
    min_time_delta: timedelta = timedelta(minutes=5)


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

        same_direction = s.last_action == action
        structure_changed = s.last_structure is not None and structure_tag is not None and s.last_structure != structure_tag
        min_delta = price_delta_override if price_delta_override is not None else self.cfg.min_price_delta
        time_window = self.cfg.min_time_delta.total_seconds() if self.cfg.min_time_delta else None

        price_close = s.last_price is not None and price is not None and abs(float(price) - float(s.last_price)) < min_delta
        time_close = False
        if s.last_time is not None and time_idx is not None and time_window is not None:
            try:
                delta_seconds = (time_idx - s.last_time).total_seconds()
                time_close = delta_seconds is not None and delta_seconds >= 0 and delta_seconds < time_window
            except Exception:
                time_close = False
        elif s.last_time == time_idx and time_idx is not None:
            time_close = True

        if same_direction and price_close and time_close and not structure_changed:
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
