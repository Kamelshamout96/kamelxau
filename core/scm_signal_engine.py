"""
SCM_SIGNAL_ENGINE: Smart-money style multi-layer evaluator (independent BUY/SELL systems).

Consumes 5m/15m/1h/4h DataFrames with indicator columns, and returns a decision JSON
matching the requested schema. Focus is on 15m→5m structure/liquidity while keeping
HTF context informational (not suppressive).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import math

from . import signal_engine as se


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        f = float(val)
        if math.isnan(f):
            return default
        return f
    except Exception:
        return default


def _structure_bias(struct: Dict[str, Any]) -> str:
    if struct.get("label") == "HH-HL":
        return "bullish"
    if struct.get("label") == "LH-LL":
        return "bearish"
    return "mixed"


def _htf_trend(df_4h, df_1h) -> Tuple[str, str]:
    return se._trend(df_4h.iloc[-1]), se._trend(df_1h.iloc[-1])


def _ltf_structures(df_15m, df_5m) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    struct15 = se._detect_structure(df_15m, lookback=120, window=2)
    struct5 = se._detect_structure(df_5m, lookback=80, window=2)
    return struct15, struct5


def _trend_label(struct: Dict[str, Any]) -> str:
    return struct.get("bias", "mixed")


def _bos_choch(df, tf_label: str) -> Dict[str, Any]:
    return se._detect_bos_choch(df, tf_label)


def _liquidity(df_15m, df_5m) -> Dict[str, Any]:
    return {"15m": se._liquidity_sweep(df_15m, lookback=30), "5m": se._liquidity_sweep(df_5m, lookback=20)}


def _zones(df_1h) -> Dict[str, Any]:
    return se._detect_zones(df_1h)


def _channels(df_1h, price: float) -> Dict[str, Any]:
    return se._detect_channel_context(df_1h, price)


def _momentum(last5, last15) -> Tuple[str, str, str]:
    adx_conf, tier5, tier15, tier1h, tier4h = se._compute_adx_conf(
        _safe_float(last5.get("adx"), 0), _safe_float(last15.get("adx"), 0), None, None
    )
    return adx_conf, tier5, tier15


def _premium_discount(price: float, bounds: Dict[str, Any]) -> str:
    if not bounds:
        return "unknown"
    upper = bounds.get("upper")
    lower = bounds.get("lower")
    if upper is None or lower is None:
        return "unknown"
    mid = (upper + lower) / 2
    if price >= mid:
        return "premium"
    return "discount"


def _score_layers(layers: Dict[str, bool]) -> Tuple[int, Dict[str, int]]:
    # Simple weights aligned to requested breakdown keys.
    weights = {
        "structure": 25,
        "liquidity": 20,
        "zones": 20,
        "momentum": 15,
        "channels": 10,
        "htf_context": 10,
    }
    breakdown = {k: (weights[k] if v else 0) for k, v in layers.items()}
    return sum(breakdown.values()), breakdown


def _pick_direction(bull_layers: Dict[str, bool], bear_layers: Dict[str, bool]) -> str:
    bull_count = sum(1 for v in bull_layers.values() if v)
    bear_count = sum(1 for v in bear_layers.values() if v)
    if bull_count >= 3 and bull_count > bear_count:
        return "BUY"
    if bear_count >= 3 and bear_count > bull_count:
        return "SELL"
    return "NO_TRADE"


def evaluate(df_5m, df_15m, df_1h, df_4h) -> Dict[str, Any]:
    """
    Evaluate signals using the 10-layer rule-set; returns structured JSON.
    """
    last5 = df_5m.iloc[-1]
    last15 = df_15m.iloc[-1]
    price = float(last5["close"])

    trend4h, trend1h = _htf_trend(df_4h, df_1h)
    struct15, struct5 = _ltf_structures(df_15m, df_5m)
    trend15 = _trend_label(struct15)
    trend5 = _trend_label(struct5)

    bos15 = _bos_choch(df_15m, "15m")
    bos5 = _bos_choch(df_5m, "5m")
    sweeps = _liquidity(df_15m, df_5m)
    zones = _zones(df_1h)
    channels = _channels(df_1h, price)
    imbalances = se._detect_imbalance(df_15m)
    wick_bull, wick_bear = se._wick_rejection(last5)
    adx_conf, tier5, tier15 = _momentum(last5, last15)

    premium_state = _premium_discount(price, channels.get("bounds", {}))

    bull_layers = {
        "structure": bos15.get("direction") == "bullish" or bos5.get("direction") == "bullish" or trend15 == "bullish",
        "liquidity": sweeps["15m"].get("type") == "below" or sweeps["5m"].get("type") == "below",
        "zones": zones.get("demand", {}).get("confidence", 0) >= 50,
        "momentum": adx_conf in ("HIGH", "MEDIUM") and tier5 != "blocked",
        "channels": channels.get("tap") == "support",
        "htf_context": trend4h == "bullish" or trend1h == "bullish",
    }
    bear_layers = {
        "structure": bos15.get("direction") == "bearish" or bos5.get("direction") == "bearish" or trend15 == "bearish",
        "liquidity": sweeps["15m"].get("type") == "above" or sweeps["5m"].get("type") == "above",
        "zones": zones.get("supply", {}).get("confidence", 0) >= 50,
        "momentum": adx_conf in ("HIGH", "MEDIUM") and tier5 != "blocked",
        "channels": channels.get("tap") == "resistance",
        "htf_context": trend4h == "bearish" or trend1h == "bearish",
    }

    # Premium/discount filter: BUY prefers discount, SELL prefers premium; do not block but inform.
    if premium_state == "premium":
        bull_layers["structure"] = False
    if premium_state == "discount":
        bear_layers["structure"] = False

    action = _pick_direction(bull_layers, bear_layers)

    # Build levels via existing helper to keep geometry consistent.
    sl, tp1, tp2, tp3 = se._build_levels(
        action if action in ("BUY", "SELL") else "BUY", price, df_5m, df_15m, df_1h, zones, channels, _safe_float(last5.get("atr"), price * 0.003) or price * 0.003, _safe_float(last15.get("atr"), price * 0.003) or price * 0.003
    )

    total_score, score_breakdown = _score_layers(bull_layers if action == "BUY" else bear_layers)
    confidence = min(100, max(0, total_score))

    reasoning: List[str] = []
    reasoning.append(f"HTF: 4H {trend4h}, 1H {trend1h}; LTF: 15m {trend15}, 5m {trend5}")
    if bull_layers["structure"] or bear_layers["structure"]:
        reasoning.append(f"Structure: 15m BOS/CHOCH {bos15.get('direction')} | 5m {bos5.get('direction')}")
    if sweeps["15m"].get("type"):
        reasoning.append(f"15m liquidity sweep {sweeps['15m']['type']}")
    if sweeps["5m"].get("type"):
        reasoning.append(f"5m liquidity sweep {sweeps['5m']['type']}")
    if channels.get("tap"):
        reasoning.append(f"Channel tap at {channels['tap']} ({channels.get('type')})")
    if zones.get("demand", {}).get("zone"):
        reasoning.append(f"Demand conf {zones['demand']['confidence']:.0f}%")
    if zones.get("supply", {}).get("zone"):
        reasoning.append(f"Supply conf {zones['supply']['confidence']:.0f}%")
    if imbalances.get("bullish") or imbalances.get("bearish"):
        reasoning.append(f"Imbalance: {'bullish' if imbalances.get('bullish') else 'bearish'}")
    if wick_bull or wick_bear:
        reasoning.append(f"Wick rejection: {'bullish' if wick_bull else 'bearish'}")
    reasoning.append(f"Momentum ADX: {adx_conf} (5m {tier5}, 15m {tier15})")

    return {
        "action": action,
        "entry": round(price, 2),
        "sl": sl if action in ("BUY", "SELL") else None,
        "tp1": tp1 if action in ("BUY", "SELL") else None,
        "tp2": tp2 if action in ("BUY", "SELL") else None,
        "tp3": tp3 if action in ("BUY", "SELL") else None,
        "confidence": confidence,
        "trend": {"4h": trend4h, "1h": trend1h, "15m": trend15, "5m": trend5},
        "structure": {"bos": bos15.get("direction") or bos5.get("direction"), "choch": None, "pattern": struct15.get("label")},
        "liquidity": {
            "sweep": sweeps["15m"].get("type") or sweeps["5m"].get("type") or "none",
            "levels": [lvl for lvl in (sweeps["15m"].get("level"), sweeps["5m"].get("level")) if lvl],
        },
        "zones": zones,
        "momentum": adx_conf,
        "channels": channels,
        "reasoning": reasoning,
        "score_breakdown": score_breakdown,
    }
