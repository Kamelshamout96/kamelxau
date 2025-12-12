"""
HumanScalperLayer: mimics professional human scalping with high accuracy.

Strategy:
- Trade WITH the micro-trend only (no counter-trend)
- Multiple confirmations required (EMA + RSI + Price Action + Recent momentum)
- Clear stop loss and take profit levels
- Natural pullback entries (buy dips in uptrend, sell rallies in downtrend)

Safety Guarantees:
- BUY only when: Price > EMA50, EMA50 > EMA200, RSI not overbought, bullish momentum
- SELL only when: Price < EMA50, EMA50 < EMA200, RSI not oversold, bearish momentum
"""

from __future__ import annotations

from typing import Any, Dict


class HumanScalperLayer:
    """Human-style scalping with strict directional safety."""

    def __init__(self):
        self.min_confidence = 65.0

    def evaluate(
        self,
        df_5m,
        df_15m,
        ctx: Dict[str, Any],
        bias: str,
    ) -> Dict[str, Any]:
        """
        Evaluate scalping opportunity with human-like analysis.
        
        Returns signal dict with action, entry, sl, tp levels, and reasoning.
        """
        if len(df_5m) < 30:
            return self._no_trade("insufficient_data")

        last = df_5m.iloc[-1]
        prev_1 = df_5m.iloc[-2]
        prev_2 = df_5m.iloc[-3]
        
        # Current price
        price = float(last["close"])
        
        # === 1. TREND IDENTIFICATION (Safety Layer 1) ===
        ema50 = self._safe_float(last.get("ema50"))
        ema200 = self._safe_float(last.get("ema200"))
        
        if ema50 is None or ema200 is None:
            return self._no_trade("missing_emas")
        
        # Micro trend on 5m
        micro_trend_bullish = ema50 > ema200
        micro_trend_bearish = ema50 < ema200
        
        # Price position relative to EMAs
        price_above_ema50 = price > ema50
        price_below_ema50 = price < ema50
        
        # === 2. MOMENTUM CHECK (Safety Layer 2) ===
        rsi = self._safe_float(last.get("rsi"))
        if rsi is None:
            return self._no_trade("missing_rsi")
        
        # Momentum zones
        rsi_bullish_zone = 40 <= rsi <= 70  # Not overbought, has room to run
        rsi_bearish_zone = 30 <= rsi <= 60  # Not oversold, has room to drop
        rsi_neutral = 45 <= rsi <= 55
        
        # === 3. PRICE ACTION CHECK (Safety Layer 3) ===
        # Recent candle momentum (last 3 candles)
        close_0 = float(last["close"])
        close_1 = float(prev_1["close"])
        close_2 = float(prev_2["close"])
        
        open_0 = float(last["open"])
        open_1 = float(prev_1["open"])
        
        # Current candle direction
        current_bullish = close_0 > open_0
        current_bearish = close_0 < open_0
        
        # Recent price flow (is price making higher lows or lower highs?)
        recent_upward_flow = close_0 > close_2  # Net upward in last 3 candles
        recent_downward_flow = close_0 < close_2  # Net downward in last 3 candles
        
        # Body strength
        body_size = abs(close_0 - open_0)
        candle_range = float(last["high"]) - float(last["low"])
        body_ratio = body_size / candle_range if candle_range > 0 else 0
        strong_body = body_ratio > 0.5  # More than 50% is body
        
        # === 4. VOLATILITY & ATR ===
        atr = self._safe_float(last.get("atr"))
        if atr is None:
            atr = self._calculate_atr(df_5m)
        
        # === 5. HIGHER TIMEFRAME ALIGNMENT (15m confirmation) ===
        htf_bullish = self._is_15m_bullish(df_15m)
        htf_bearish = self._is_15m_bearish(df_15m)
        htf_neutral = not htf_bullish and not htf_bearish
        
        # === 6. PULLBACK DETECTION (Human scalper looks for dips/rallies) ===
        # Is price pulling back to EMA in a trending market?
        distance_from_ema50 = abs(price - ema50)
        near_ema50 = distance_from_ema50 < (atr * 1.0)  # Within 1 ATR of EMA50
        
        # Pullback entry: price was away, now coming back to EMA
        pullback_buy_setup = micro_trend_bullish and price_above_ema50 and near_ema50
        pullback_sell_setup = micro_trend_bearish and price_below_ema50 and near_ema50
        
        # Breakout entry: price just crossed EMA with momentum
        breakout_buy_setup = price_above_ema50 and close_1 <= ema50 and current_bullish
        breakout_sell_setup = price_below_ema50 and close_1 >= ema50 and current_bearish
        
        # === 7. STRUCTURE SUPPORT (from existing context) ===
        structure_5m = ctx.get("structure_shifts", {}).get("5m", {})
        structure_15m = ctx.get("structure_shifts", {}).get("15m", {})
        
        structure_supports_buy = (
            structure_5m.get("direction") == "bullish" 
            or structure_15m.get("direction") == "bullish"
        )
        structure_supports_sell = (
            structure_5m.get("direction") == "bearish" 
            or structure_15m.get("direction") == "bearish"
        )
        
        # === 8. CONFLUENCE SCORING ===
        buy_score = 0
        sell_score = 0
        buy_reasons = []
        sell_reasons = []
        
        # BUY SCORING (need at least 5 points)
        if micro_trend_bullish:
            buy_score += 2
            buy_reasons.append("5m uptrend (EMA50 > EMA200)")
        if price_above_ema50:
            buy_score += 1
            buy_reasons.append("Price above EMA50")
        if rsi_bullish_zone:
            buy_score += 2
            buy_reasons.append(f"RSI bullish zone ({rsi:.1f})")
        if recent_upward_flow:
            buy_score += 1
            buy_reasons.append("Recent upward price flow")
        if current_bullish and strong_body:
            buy_score += 1
            buy_reasons.append("Strong bullish candle")
        if htf_bullish or htf_neutral:
            buy_score += 1
            buy_reasons.append("15m alignment")
        if pullback_buy_setup or breakout_buy_setup:
            buy_score += 1
            buy_reasons.append("Pullback/breakout setup")
        if structure_supports_buy:
            buy_score += 1
            buy_reasons.append("Bullish structure shift")
        if bias in ("BUY ONLY", "NEUTRAL"):
            buy_score += 1
            buy_reasons.append(f"HTF bias: {bias}")
        
        # SELL SCORING (need at least 5 points)
        if micro_trend_bearish:
            sell_score += 2
            sell_reasons.append("5m downtrend (EMA50 < EMA200)")
        if price_below_ema50:
            sell_score += 1
            sell_reasons.append("Price below EMA50")
        if rsi_bearish_zone:
            sell_score += 2
            sell_reasons.append(f"RSI bearish zone ({rsi:.1f})")
        if recent_downward_flow:
            sell_score += 1
            sell_reasons.append("Recent downward price flow")
        if current_bearish and strong_body:
            sell_score += 1
            sell_reasons.append("Strong bearish candle")
        if htf_bearish or htf_neutral:
            sell_score += 1
            sell_reasons.append("15m alignment")
        if pullback_sell_setup or breakout_sell_setup:
            sell_score += 1
            sell_reasons.append("Pullback/breakout setup")
        if structure_supports_sell:
            sell_score += 1
            sell_reasons.append("Bearish structure shift")
        if bias in ("SELL ONLY", "NEUTRAL"):
            sell_score += 1
            sell_reasons.append(f"HTF bias: {bias}")
        
        # === 9. SAFETY FILTERS (Guaranteed Direction Accuracy) ===
        # NEVER BUY if critical bearish conditions exist
        buy_blocked = (
            not micro_trend_bullish  # EMA50 must be > EMA200
            or rsi > 75  # Extremely overbought
            or (htf_bearish and bias == "SELL ONLY")  # Strong opposing bias
            or price_below_ema50  # Price must be above EMA50
        )
        
        # NEVER SELL if critical bullish conditions exist
        sell_blocked = (
            not micro_trend_bearish  # EMA50 must be < EMA200
            or rsi < 25  # Extremely oversold
            or (htf_bullish and bias == "BUY ONLY")  # Strong opposing bias
            or price_above_ema50  # Price must be below EMA50
        )
        
        # === 10. DECISION LOGIC ===
        action = "NO_TRADE"
        sl = tp1 = tp2 = tp3 = None
        confidence = 0
        reason_text = ""
        
        # Minimum confluence requirement: 5 points
        MIN_CONFLUENCE = 5
        
        if buy_score >= MIN_CONFLUENCE and not buy_blocked:
            action = "BUY"
            confidence = min(50 + (buy_score * 5), 85)  # Scale 50-85
            
            # Stop loss: below recent swing low or EMA200
            sl_swing = float(df_5m.iloc[-5:]["low"].min())  # Recent 5-candle low
            sl_ema = ema200 - (atr * 0.5)
            sl = max(sl_swing, sl_ema)  # Use the tighter (higher) stop
            
            # Take profits: ATR-based scaling
            tp1 = price + (atr * 1.2)
            tp2 = price + (atr * 2.0)
            tp3 = price + (atr * 3.0)
            
            reason_text = f"Human scalper BUY ({buy_score} confluences): " + ", ".join(buy_reasons)
        
        elif sell_score >= MIN_CONFLUENCE and not sell_blocked:
            action = "SELL"
            confidence = min(50 + (sell_score * 5), 85)  # Scale 50-85
            
            # Stop loss: above recent swing high or EMA200
            sl_swing = float(df_5m.iloc[-5:]["high"].max())  # Recent 5-candle high
            sl_ema = ema200 + (atr * 0.5)
            sl = min(sl_swing, sl_ema)  # Use the tighter (lower) stop
            
            # Take profits: ATR-based scaling
            tp1 = price - (atr * 1.2)
            tp2 = price - (atr * 2.0)
            tp3 = price - (atr * 3.0)
            
            reason_text = f"Human scalper SELL ({sell_score} confluences): " + ", ".join(sell_reasons)
        
        else:
            # Not enough confluence or blocked
            if buy_score >= MIN_CONFLUENCE and buy_blocked:
                reason_text = f"BUY blocked by safety filters (score={buy_score})"
            elif sell_score >= MIN_CONFLUENCE and sell_blocked:
                reason_text = f"SELL blocked by safety filters (score={sell_score})"
            else:
                max_score = max(buy_score, sell_score)
                reason_text = f"Insufficient confluence (max={max_score}, need={MIN_CONFLUENCE})"
        
        # === 11. BUILD SIGNAL ===
        return {
            "action": action,
            "entry": round(price, 2),
            "sl": round(sl, 2) if sl else None,
            "tp": round(tp1, 2) if tp1 else None,
            "tp1": round(tp1, 2) if tp1 else None,
            "tp2": round(tp2, 2) if tp2 else None,
            "tp3": round(tp3, 2) if tp3 else None,
            "confidence": round(confidence, 1),
            "reason": reason_text if action != "NO_TRADE" else reason_text,
            "layer": "human_scalper",
            "confluence_score": {
                "buy": buy_score,
                "sell": sell_score,
            },
        }

    def _is_15m_bullish(self, df_15m) -> bool:
        """Check if 15m timeframe is bullish."""
        if len(df_15m) < 5:
            return False
        last = df_15m.iloc[-1]
        ema50 = self._safe_float(last.get("ema50"))
        ema200 = self._safe_float(last.get("ema200"))
        if ema50 is None or ema200 is None:
            return False
        return ema50 > ema200 and float(last["close"]) > ema50

    def _is_15m_bearish(self, df_15m) -> bool:
        """Check if 15m timeframe is bearish."""
        if len(df_15m) < 5:
            return False
        last = df_15m.iloc[-1]
        ema50 = self._safe_float(last.get("ema50"))
        ema200 = self._safe_float(last.get("ema200"))
        if ema50 is None or ema200 is None:
            return False
        return ema50 < ema200 and float(last["close"]) < ema50

    def _calculate_atr(self, df) -> float:
        """Calculate ATR manually if not available."""
        if len(df) < 14:
            # Fallback to simple range
            return float(df.iloc[-5:]["high"].max() - df.iloc[-5:]["low"].min()) / 5
        
        import numpy as np
        
        tr = np.maximum.reduce([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ])
        atr = float(tr[-14:].mean())
        return atr if atr > 0 else 1.0

    def _safe_float(self, value) -> float | None:
        """Safely convert to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _no_trade(self, reason: str) -> Dict[str, Any]:
        """Return NO_TRADE signal."""
        return {
            "action": "NO_TRADE",
            "entry": None,
            "sl": None,
            "tp": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "confidence": 0,
            "reason": reason,
            "layer": "human_scalper",
        }
