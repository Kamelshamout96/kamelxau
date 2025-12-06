"""
HUMAN-LIKE TECHNICAL ANALYSIS ENGINE - PRODUCTION GRADE
========================================================
Deterministic, stable, and bulletproof professional trader analysis:
- Support & Resistance with strength scoring
- Trendlines & Channels with parallel detection
- Chart Patterns with confidence scoring
- Supply & Demand Zones
- Multi-TP targets (tp1, tp2, tp3)
- Structural SL placement
- Visual story generation (ALWAYS)
- Market structure (HH/HL/LH/LL)
- Liquidity sweeps detection
- Next move prediction (ALWAYS, even market closed)
- Zero division errors
- Zero index errors
- Deterministic results
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SupportResistance:
    """Support or Resistance level"""
    price: float
    strength: int
    level_type: str
    first_touch: datetime
    last_touch: datetime
    touches: List[datetime]
    

@dataclass
class Trendline:
    """Trendline connecting swing points"""
    start_price: float
    end_price: float
    start_time: datetime
    end_time: datetime
    slope: float
    touches: int
    line_type: str
    strength: float


@dataclass
class ChartPattern:
    """Chart pattern detection"""
    pattern_type: str
    start_time: datetime
    end_time: datetime
    upper_line: Optional[Trendline]
    lower_line: Optional[Trendline]
    confidence: float
    expected_breakout: str
    target_price: Optional[float]


@dataclass
class SwingPoint:
    """Swing high or low point"""
    price: float
    time: datetime
    swing_type: str
    strength: int


@dataclass
class Zone:
    """Supply or Demand zone"""
    upper_price: float
    lower_price: float
    zone_type: str
    strength: int
    time_created: datetime
    touches: int
    fresh: bool


@dataclass
class TradeSetup:
    """Complete trade setup with visual analysis"""
    action: str
    entry_price: float
    sl_price: float
    tp_price: float
    confidence: float
    reasoning: List[str]
    key_levels: Dict[str, float]
    patterns_detected: List[str]
    timeframe: str
    risk_reward: float
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    visual_story: str = ""
    structure_labels: List[str] = field(default_factory=list)
    next_move: str = ""
    visual_prediction: bool = False


class HumanLikeAnalyzer:
    """
    Deterministic professional trader analysis engine
    ALWAYS returns actionable insights
    """
    
    def __init__(self, lookback_candles: int = 300):
        self.lookback = lookback_candles
        self.min_touches = 2
        self.price_tolerance = 0.0015
        
    
    def find_swing_points(self, df: pd.DataFrame, window: int = 5) -> List[SwingPoint]:
        """Identify swing highs and lows - DETERMINISTIC"""
        swings = []
        
        if df is None or len(df) < window * 2 + 1:
            return swings
        
        try:
            for i in range(window, len(df) - window):
                high = df['high'].iloc[i]
                
                is_swing_high = all(df['high'].iloc[j] < high for j in range(i - window, i + window + 1) if j != i)
                
                if is_swing_high:
                    strength = self._calculate_swing_strength(df, i, 'high', window)
                    swings.append(SwingPoint(
                        price=float(high),
                        time=df.index[i],
                        swing_type='high',
                        strength=strength
                    ))
            
            for i in range(window, len(df) - window):
                low = df['low'].iloc[i]
                
                is_swing_low = all(df['low'].iloc[j] > low for j in range(i - window, i + window + 1) if j != i)
                
                if is_swing_low:
                    strength = self._calculate_swing_strength(df, i, 'low', window)
                    swings.append(SwingPoint(
                        price=float(low),
                        time=df.index[i],
                        swing_type='low',
                        strength=strength
                    ))
            
            swings.sort(key=lambda x: (x.time, x.swing_type))
        except Exception as e:
            print(f"[WARN] find_swing_points: {e}")
        
        return swings
    
    
    def _calculate_swing_strength(self, df: pd.DataFrame, idx: int, 
                                  swing_type: str, window: int) -> int:
        """Calculate swing strength - DETERMINISTIC (1-5)"""
        try:
            lookback_range = min(window * 5, idx)
            if lookback_range == 0:
                return 2
            
            if swing_type == 'high':
                price = float(df['high'].iloc[idx])
                highs_before = df['high'].iloc[max(0, idx - lookback_range):idx]
                if len(highs_before) == 0:
                    return 2
                max_before = float(highs_before.max())
                if price >= max_before:
                    return 5
                q90 = float(highs_before.quantile(0.9))
                q80 = float(highs_before.quantile(0.8))
                if price >= q90:
                    return 4
                elif price >= q80:
                    return 3
                else:
                    return 2
            else:
                price = float(df['low'].iloc[idx])
                lows_before = df['low'].iloc[max(0, idx - lookback_range):idx]
                if len(lows_before) == 0:
                    return 2
                min_before = float(lows_before.min())
                if price <= min_before:
                    return 5
                q10 = float(lows_before.quantile(0.1))
                q20 = float(lows_before.quantile(0.2))
                if price <= q10:
                    return 4
                elif price <= q20:
                    return 3
                else:
                    return 2
        except Exception:
            return 2
    
    
    def detect_market_structure(self, swings: List[SwingPoint]) -> List[str]:
        """Detect HH/HL/LH/LL - DETERMINISTIC & ALWAYS RETURNS RESULT"""
        if not swings or len(swings) < 4:
            return ["Neutral - Insufficient swings"]
        
        try:
            swings_sorted = sorted(swings, key=lambda x: x.time)
            highs = [s for s in swings_sorted if s.swing_type == 'high']
            lows = [s for s in swings_sorted if s.swing_type == 'low']
            
            structure = []
            
            if len(highs) >= 2:
                last_high = float(highs[-1].price)
                prev_high = float(highs[-2].price)
                if last_high > prev_high * 1.001:
                    structure.append("HH (Higher High)")
                elif last_high < prev_high * 0.999:
                    structure.append("LH (Lower High)")
                else:
                    structure.append("EH (Equal High)")
            
            if len(lows) >= 2:
                last_low = float(lows[-1].price)
                prev_low = float(lows[-2].price)
                if last_low > prev_low * 1.001:
                    structure.append("HL (Higher Low)")
                elif last_low < prev_low * 0.999:
                    structure.append("LL (Lower Low)")
                else:
                    structure.append("EL (Equal Low)")
            
            if len(structure) >= 2:
                if "HH" in structure[0] and "HL" in structure[1]:
                    structure.append("✓ Bullish Structure")
                elif "LH" in structure[0] and "LL" in structure[1]:
                    structure.append("✓ Bearish Structure")
                else:
                    structure.append("→ Ranging/Transitioning")
            
            return structure if structure else ["Neutral"]
        except Exception as e:
            print(f"[WARN] detect_market_structure: {e}")
            return ["Neutral - Error"]
    
    
    def detect_liquidity_sweeps(self, df: pd.DataFrame, swings: List[SwingPoint]) -> List[str]:
        """Detect liquidity sweeps - STABLE"""
        sweeps = []
        
        if df is None or len(df) < 10 or not swings:
            return sweeps
        
        try:
            recent_high = float(df['high'].iloc[-10:].max())
            recent_low = float(df['low'].iloc[-10:].min())
            
            swing_highs = sorted([s for s in swings if s.swing_type == 'high'], 
                                key=lambda x: x.time, reverse=True)[:3]
            swing_lows = sorted([s for s in swings if s.swing_type == 'low'], 
                               key=lambda x: x.time, reverse=True)[:3]
            
            for swing in swing_highs:
                if swing.price > 0 and recent_high > swing.price * 1.001:
                    sweeps.append(f"↑ Liquidity swept above ${swing.price:.2f}")
                    break
            
            for swing in swing_lows:
                if swing.price > 0 and recent_low < swing.price * 0.999:
                    sweeps.append(f"↓ Liquidity swept below ${swing.price:.2f}")
                    break
        except Exception as e:
            print(f"[WARN] detect_liquidity_sweeps: {e}")
        
        return sweeps
    
    
    def find_support_resistance(self, df: pd.DataFrame, 
                               swings: List[SwingPoint]) -> List[SupportResistance]:
        """Find S/R levels - DETERMINISTIC clustering"""
        if not swings or df is None or len(df) == 0:
            return []
        
        levels = []
        
        try:
            swings_sorted = sorted(swings, key=lambda x: x.price)
            price_groups = []
            
            for swing in swings_sorted:
                added = False
                for group in price_groups:
                    avg_price = np.mean([s.price for s in group])
                    if avg_price > 0 and abs(swing.price - avg_price) / avg_price < self.price_tolerance:
                        group.append(swing)
                        added = True
                        break
                
                if not added:
                    price_groups.append([swing])
            
            current_price = float(df['close'].iloc[-1]) if len(df) > 0 else 0
            
            for group in price_groups:
                if len(group) >= self.min_touches:
                    avg_price = float(np.mean([s.price for s in group]))
                    
                    highs = [s for s in group if s.swing_type == 'high']
                    lows = [s for s in group if s.swing_type == 'low']
                    
                    if len(lows) > len(highs):
                        level_type = 'support'
                    elif len(highs) > len(lows):
                        level_type = 'resistance'
                    else:
                        level_type = 'support' if avg_price < current_price else 'resistance'
                    
                    times = [s.time for s in group]
                    levels.append(SupportResistance(
                        price=avg_price,
                        strength=len(group),
                        level_type=level_type,
                        first_touch=min(times),
                        last_touch=max(times),
                        touches=times
                    ))
            
            levels.sort(key=lambda x: (x.strength, x.price), reverse=True)
        except Exception as e:
            print(f"[WARN] find_support_resistance: {e}")
        
        return levels
    
    
    def find_trendlines(self, df: pd.DataFrame, 
                       swings: List[SwingPoint]) -> List[Trendline]:
        """Find trendlines - DETERMINISTIC"""
        trendlines = []
        
        if not swings or df is None or len(df) == 0:
            return trendlines
        
        try:
            swing_lows = sorted([s for s in swings if s.swing_type == 'low'], key=lambda x: x.time)
            swing_highs = sorted([s for s in swings if s.swing_type == 'high'], key=lambda x: x.time)
            
            for i in range(len(swing_lows) - 1):
                for j in range(i + 1, min(i + 6, len(swing_lows))):
                    start = swing_lows[i]
                    end = swing_lows[j]
                    
                    time_diff = (end.time - start.time).total_seconds()
                    if time_diff <= 0:
                        continue
                        
                    slope = (end.price - start.price) / time_diff
                    
                    touches = self._count_trendline_touches(
                        df, start.price, start.time, slope, 'support_trend'
                    )
                    
                    if touches >= 2 and start.price > 0:
                        strength = float(touches * 25 + min(abs(slope) * 10000, 50))
                        
                        trendlines.append(Trendline(
                            start_price=float(start.price),
                            end_price=float(end.price),
                            start_time=start.time,
                            end_time=end.time,
                            slope=slope,
                            touches=touches,
                            line_type='support_trend',
                            strength=strength
                        ))
            
            for i in range(len(swing_highs) - 1):
                for j in range(i + 1, min(i + 6, len(swing_highs))):
                    start = swing_highs[i]
                    end = swing_highs[j]
                    
                    time_diff = (end.time - start.time).total_seconds()
                    if time_diff <= 0:
                        continue
                        
                    slope = (end.price - start.price) / time_diff
                    
                    touches = self._count_trendline_touches(
                        df, start.price, start.time, slope, 'resistance_trend'
                    )
                    
                    if touches >= 2 and start.price > 0:
                        strength = float(touches * 25 + min(abs(slope) * 10000, 50))
                        
                        trendlines.append(Trendline(
                            start_price=float(start.price),
                            end_price=float(end.price),
                            start_time=start.time,
                            end_time=end.time,
                            slope=slope,
                            touches=touches,
                            line_type='resistance_trend',
                            strength=strength
                        ))
            
            trendlines.sort(key=lambda x: (x.strength, x.touches), reverse=True)
        except Exception as e:
            print(f"[WARN] find_trendlines: {e}")
        
        return trendlines[:10]
    
    
    def _count_trendline_touches(self, df: pd.DataFrame, start_price: float,
                                 start_time: datetime, slope: float,
                                 line_type: str) -> int:
        """Count trendline touches - SAFE"""
        touches = 0
        
        if start_price == 0 or df is None or len(df) == 0:
            return touches
        
        try:
            tolerance = abs(start_price * 0.0025)
            df_subset = df[df.index >= start_time]
            
            for idx, row in df_subset.iterrows():
                time_diff = (idx - start_time).total_seconds()
                expected_price = start_price + (slope * time_diff)
                
                if line_type == 'support_trend':
                    if abs(float(row['low']) - expected_price) < tolerance:
                        touches += 1
                else:
                    if abs(float(row['high']) - expected_price) < tolerance:
                        touches += 1
        except Exception as e:
            print(f"[WARN] _count_trendline_touches: {e}")
        
        return touches
    
    
    def detect_channel(self, trendlines: List[Trendline]) -> Optional[ChartPattern]:
        """Detect parallel channels - DETERMINISTIC"""
        if len(trendlines) < 2:
            return None
        
        try:
            support_lines = [t for t in trendlines if t.line_type == 'support_trend']
            resistance_lines = [t for t in trendlines if t.line_type == 'resistance_trend']
            
            for lower_line in support_lines:
                for upper_line in resistance_lines:
                    slope_diff = abs(lower_line.slope - upper_line.slope)
                    avg_slope = (abs(lower_line.slope) + abs(upper_line.slope)) / 2
                    
                    if avg_slope > 0 and slope_diff / avg_slope < 0.25:
                        
                        if lower_line.slope > 0 and upper_line.slope > 0:
                            direction = 'up'
                            confidence = 85.0
                        elif lower_line.slope < 0 and upper_line.slope < 0:
                            direction = 'down'
                            confidence = 85.0
                        else:
                            direction = 'sideways'
                            confidence = 70.0
                        
                        channel_height = abs(upper_line.start_price - lower_line.start_price)
                        
                        if direction == 'up':
                            target = float(upper_line.end_price + channel_height)
                        elif direction == 'down':
                            target = float(lower_line.end_price - channel_height)
                        else:
                            target = None
                        
                        return ChartPattern(
                            pattern_type=f'{direction}_channel',
                            start_time=min(lower_line.start_time, upper_line.start_time),
                            end_time=max(lower_line.end_time, upper_line.end_time),
                            upper_line=upper_line,
                            lower_line=lower_line,
                            confidence=confidence,
                            expected_breakout=direction,
                            target_price=target
                        )
        except Exception as e:
            print(f"[WARN] detect_channel: {e}")
        
        return None
    
    
    def find_supply_demand_zones(self, df: pd.DataFrame, 
                                 swings: List[SwingPoint]) -> List[Zone]:
        """Find supply/demand zones - STABLE"""
        zones = []
        
        if df is None or len(df) < 10 or not swings:
            return zones
        
        try:
            strong_swings = sorted([s for s in swings if s.strength >= 3], 
                                  key=lambda x: x.time, reverse=True)[:10]
            
            for swing in strong_swings:
                try:
                    candle_idx = df.index.get_loc(swing.time)
                except KeyError:
                    continue
                
                if candle_idx < 5 or candle_idx >= len(df) - 1:
                    continue
                
                candles_before = df.iloc[max(0, candle_idx - 10):candle_idx]
                
                if len(candles_before) < 3:
                    continue
                
                if swing.swing_type == 'low':
                    price_range = float(candles_before['high'].max() - candles_before['low'].min())
                    zone_bottom = float(candles_before['low'].min())
                    zone_top = zone_bottom + (price_range * 0.25)
                    
                    candles_after = df.iloc[candle_idx:min(len(df), candle_idx + 5)]
                    if len(candles_after) > 0 and swing.price > 0:
                        bounce = (float(candles_after['high'].max()) - swing.price) / swing.price
                        
                        if bounce > 0.004:
                            zones.append(Zone(
                                upper_price=zone_top,
                                lower_price=zone_bottom,
                                zone_type='demand',
                                strength=swing.strength,
                                time_created=swing.time,
                                touches=1,
                                fresh=True
                            ))
                
                else:
                    price_range = float(candles_before['high'].max() - candles_before['low'].min())
                    zone_top = float(candles_before['high'].max())
                    zone_bottom = zone_top - (price_range * 0.25)
                    
                    candles_after = df.iloc[candle_idx:min(len(df), candle_idx + 5)]
                    if len(candles_after) > 0 and swing.price > 0:
                        drop = (swing.price - float(candles_after['low'].min())) / swing.price
                        
                        if drop > 0.004:
                            zones.append(Zone(
                                upper_price=zone_top,
                                lower_price=zone_bottom,
                                zone_type='supply',
                                strength=swing.strength,
                                time_created=swing.time,
                                touches=1,
                                fresh=True
                            ))
        except Exception as e:
            print(f"[WARN] find_supply_demand_zones: {e}")
        
        return zones
    
    
    def calculate_multi_tp(self, action: str, entry: float, nearest_resistance: Optional[SupportResistance],
                          nearest_support: Optional[SupportResistance], channel: Optional[ChartPattern],
                          atr: float) -> Tuple[float, float, float]:
        """Calculate multi-TP - DETERMINISTIC"""
        try:
            atr = max(atr, entry * 0.005)
            
            if action == 'BUY':
                tp1 = float(nearest_resistance.price if nearest_resistance else entry + (atr * 1.5))
                tp2 = float(channel.upper_line.end_price if (channel and channel.upper_line) else tp1 + (atr * 1.5))
                tp3 = float(channel.target_price if (channel and channel.target_price) else tp2 + (atr * 2.0))
            else:
                tp1 = float(nearest_support.price if nearest_support else entry - (atr * 1.5))
                tp2 = float(channel.lower_line.end_price if (channel and channel.lower_line) else tp1 - (atr * 1.5))
                tp3 = float(channel.target_price if (channel and channel.target_price) else tp2 - (atr * 2.0))
            
            return round(tp1, 2), round(tp2, 2), round(tp3, 2)
        except Exception:
            return round(entry, 2), round(entry, 2), round(entry, 2)
    
    
    def calculate_structural_sl(self, action: str, entry: float, nearest_support: Optional[SupportResistance],
                               nearest_resistance: Optional[SupportResistance], zones: List[Zone],
                               channel: Optional[ChartPattern], atr: float) -> float:
        """Calculate structural SL - DETERMINISTIC"""
        try:
            atr = max(atr, entry * 0.005)
            
            if action == 'BUY':
                sl_options = []
                
                if nearest_support:
                    sl_options.append(float(nearest_support.price - (atr * 0.2)))
                
                demand_zones = [z for z in zones if z.zone_type == 'demand' and z.lower_price < entry]
                if demand_zones:
                    strongest_zone = max(demand_zones, key=lambda z: z.strength)
                    sl_options.append(float(strongest_zone.lower_price - (atr * 0.15)))
                
                if channel and channel.lower_line:
                    sl_options.append(float(channel.lower_line.end_price - (atr * 0.3)))
                
                sl = float(max(sl_options)) if sl_options else float(entry - (atr * 1.0))
            else:
                sl_options = []
                
                if nearest_resistance:
                    sl_options.append(float(nearest_resistance.price + (atr * 0.2)))
                
                supply_zones = [z for z in zones if z.zone_type == 'supply' and z.upper_price > entry]
                if supply_zones:
                    strongest_zone = max(supply_zones, key=lambda z: z.strength)
                    sl_options.append(float(strongest_zone.upper_price + (atr * 0.15)))
                
                if channel and channel.upper_line:
                    sl_options.append(float(channel.upper_line.end_price + (atr * 0.3)))
                
                sl = float(min(sl_options)) if sl_options else float(entry + (atr * 1.0))
            
            return round(sl, 2)
        except Exception:
            return round(entry - atr if action == 'BUY' else entry + atr, 2)
    
    
    def generate_visual_story(self, current_price: float, channel: Optional[ChartPattern],
                             structure: List[str], sweeps: List[str], nearest_support: Optional[SupportResistance],
                             nearest_resistance: Optional[SupportResistance], zones: List[Zone]) -> str:
        """Generate visual story - ALWAYS RETURNS INSIGHT"""
        try:
            story_parts = []
            
            story_parts.append(f"💰 Price: ${current_price:.2f}")
            
            if channel:
                pattern_name = channel.pattern_type.replace('_', ' ').title()
                story_parts.append(f"📊 {pattern_name} detected")
                
                if channel.lower_line and channel.upper_line:
                    lower = float(channel.lower_line.end_price)
                    upper = float(channel.upper_line.end_price)
                    if upper > lower and lower > 0:
                        position = ((current_price - lower) / (upper - lower)) * 100
                        position = max(0, min(100, position))
                        
                        if position < 25:
                            story_parts.append(f"📍 Near channel support ({position:.0f}% in channel)")
                        elif position > 75:
                            story_parts.append(f"📍 Near channel resistance ({position:.0f}% in channel)")
                        else:
                            story_parts.append(f"📍 Mid-channel ({position:.0f}%)")
            
            if structure and len(structure) > 0:
                story_parts.append(f"📈 {structure[0]}")
            
            if nearest_support and current_price > 0:
                dist = ((current_price - nearest_support.price) / current_price) * 100
                if dist < 2:
                    story_parts.append(f"🛡️ At support ${nearest_support.price:.2f}")
                else:
                    story_parts.append(f"🛡️ Support ${nearest_support.price:.2f} ({dist:.1f}% below)")
            
            if nearest_resistance and current_price > 0:
                dist = ((nearest_resistance.price - current_price) / current_price) * 100
                if dist < 2:
                    story_parts.append(f"🚧 At resistance ${nearest_resistance.price:.2f}")
                else:
                    story_parts.append(f"🚧 Resistance ${nearest_resistance.price:.2f} ({dist:.1f}% above)")
            
            if sweeps:
                story_parts.append(sweeps[0])
            
            demand_zones = [z for z in zones if z.zone_type == 'demand' and z.lower_price <= current_price <= z.upper_price]
            supply_zones = [z for z in zones if z.zone_type == 'supply' and z.lower_price <= current_price <= z.upper_price]
            
            if demand_zones:
                story_parts.append(f"🟢 In demand zone")
            if supply_zones:
                story_parts.append(f"🔴 In supply zone")
            
            return " | ".join(story_parts)
        except Exception as e:
            print(f"[WARN] generate_visual_story: {e}")
            return f"💰 Price: ${current_price:.2f} | Analyzing..."
    
    
    def generate_next_move(self, action: str, tp1: float, tp2: float, tp3: float, 
                          channel: Optional[ChartPattern], structure: List[str],
                          nearest_support: Optional[SupportResistance],
                          nearest_resistance: Optional[SupportResistance]) -> str:
        """Generate next move prediction - ALWAYS RETURNS ACTIONABLE INSIGHT"""
        try:
            if action == 'BUY':
                move = f"📈 BUY Setup: Watch for move to TP1 ${tp1:.2f}"
                if tp2 > tp1:
                    move += f", then TP2 ${tp2:.2f}"
                if channel and 'up' in channel.pattern_type:
                    move += f" (following {channel.pattern_type.replace('_', ' ')})"
                if structure and "Bullish" in str(structure):
                    move += ". Structure supports upside."
                return move
            
            elif action == 'SELL':
                move = f"📉 SELL Setup: Watch for move to TP1 ${tp1:.2f}"
                if tp2 < tp1:
                    move += f", then TP2 ${tp2:.2f}"
                if channel and 'down' in channel.pattern_type:
                    move += f" (following {channel.pattern_type.replace('_', ' ')})"
                if structure and "Bearish" in str(structure):
                    move += ". Structure supports downside."
                return move
            
            else:
                if channel:
                    if 'up' in channel.pattern_type:
                        return f"⏳ Wait for pullback to channel support ~${channel.lower_line.end_price if channel.lower_line else 'TBD':.2f} for BUY"
                    elif 'down' in channel.pattern_type:
                        return f"⏳ Wait for rally to channel resistance ~${channel.upper_line.end_price if channel.upper_line else 'TBD':.2f} for SELL"
                
                if nearest_support and nearest_resistance:
                    mid = (nearest_support.price + nearest_resistance.price) / 2
                    return f"⏳ Monitor: Support ${nearest_support.price:.2f} | Resistance ${nearest_resistance.price:.2f}"
                
                return "⏳ No clear setup. Monitor for structure development."
        except Exception as e:
            print(f"[WARN] generate_next_move: {e}")
            return "⏳ Monitoring market for opportunities..."
    
    
    def generate_trade_setup(self, df: pd.DataFrame, timeframe: str = '1H') -> TradeSetup:
        """Generate trade setup - FULLY DETERMINISTIC & STABLE"""
        try:
            if df is None or len(df) == 0:
                return self._empty_setup(timeframe, "No data available")
            
            current_price = float(df['close'].iloc[-1])
            atr = float(df['atr'].iloc[-1]) if 'atr' in df.columns else current_price * 0.01
            atr = max(atr, current_price * 0.005)
            
            swings = self.find_swing_points(df)
            sr_levels = self.find_support_resistance(df, swings)
            trendlines = self.find_trendlines(df, swings)
            channel = self.detect_channel(trendlines)
            zones = self.find_supply_demand_zones(df, swings)
            structure = self.detect_market_structure(swings)
            sweeps = self.detect_liquidity_sweeps(df, swings)
            
            reasoning = []
            patterns = []
            key_levels = {}
            confidence = 50.0
            
            if channel:
                patterns.append(channel.pattern_type)
                reasoning.append(f"✓ {channel.pattern_type.replace('_', ' ').title()} (confidence {channel.confidence:.0f}%)")
                confidence += 15
                
                if channel.lower_line:
                    key_levels['channel_support'] = float(channel.lower_line.end_price)
                if channel.upper_line:
                    key_levels['channel_resistance'] = float(channel.upper_line.end_price)
            
            nearest_support = None
            nearest_resistance = None
            
            for level in sr_levels[:5]:
                if level.level_type == 'support' and level.price < current_price:
                    if nearest_support is None or level.price > nearest_support.price:
                        nearest_support = level
                elif level.level_type == 'resistance' and level.price > current_price:
                    if nearest_resistance is None or level.price < nearest_resistance.price:
                        nearest_resistance = level
            
            if nearest_support and current_price > 0:
                key_levels['support'] = float(nearest_support.price)
                distance = (current_price - nearest_support.price) / current_price
                
                if distance < 0.005:
                    reasoning.append(f"✓ At major support (${nearest_support.price:.2f}, {nearest_support.strength} touches)")
                    confidence += 12
                elif distance < 0.015:
                    reasoning.append(f"→ Near support (${nearest_support.price:.2f}, {nearest_support.strength} touches)")
                    confidence += 6
            
            if nearest_resistance and current_price > 0:
                key_levels['resistance'] = float(nearest_resistance.price)
                distance = (nearest_resistance.price - current_price) / current_price
                
                if distance < 0.005:
                    reasoning.append(f"✓ At major resistance (${nearest_resistance.price:.2f}, {nearest_resistance.strength} touches)")
                    confidence += 12
                elif distance < 0.015:
                    reasoning.append(f"→ Near resistance (${nearest_resistance.price:.2f}, {nearest_resistance.strength} touches)")
                    confidence += 6
            
            active_demand = [z for z in zones if z.zone_type == 'demand' and z.lower_price <= current_price <= z.upper_price]
            active_supply = [z for z in zones if z.zone_type == 'supply' and z.lower_price <= current_price <= z.upper_price]
            
            if structure and len(structure) > 0:
                if "Bullish" in str(structure):
                    reasoning.append(f"✓ {structure[0]} - {structure[1] if len(structure) > 1 else ''}")
                    confidence += 8
                elif "Bearish" in str(structure):
                    reasoning.append(f"✓ {structure[0]} - {structure[1] if len(structure) > 1 else ''}")
                    confidence += 8
            
            if sweeps:
                reasoning.append(f"⚡ {sweeps[0]}")
                confidence += 5
            
            action = 'NO_TRADE'
            entry = current_price
            
            visual_prediction = len(df) < 20
            
            # PRIORITY 1: Channel patterns (highest priority)
            if channel and 'up' in channel.pattern_type:
                if nearest_support and current_price > 0:
                    distance = (current_price - nearest_support.price) / current_price
                    if distance < 0.01:
                        action = 'BUY'
                        reasoning.append("✓✓ BUY at ascending channel support")
                        confidence += 20
            
            elif channel and 'down' in channel.pattern_type:
                if nearest_resistance and current_price > 0:
                    distance = (nearest_resistance.price - current_price) / current_price
                    if distance < 0.01:
                        action = 'SELL'
                        reasoning.append("✓✓ SELL at descending channel resistance")
                        confidence += 20
            
            # PRIORITY 2: Supply/Demand zones (only if no channel or channel neutral)
            if action == 'NO_TRADE':
                if active_demand:
                    # Only BUY from demand if NOT in bearish channel
                    if not (channel and 'down' in channel.pattern_type):
                        strongest = max(active_demand, key=lambda z: z.strength)
                        action = 'BUY'
                        reasoning.append(f"✓✓ BUY from demand zone (strength {strongest.strength}/5)")
                        confidence += 18
                
                elif active_supply:
                    # Only SELL from supply if NOT in bullish channel
                    if not (channel and 'up' in channel.pattern_type):
                        strongest = max(active_supply, key=lambda z: z.strength)
                        action = 'SELL'
                        reasoning.append(f"✓✓ SELL from supply zone (strength {strongest.strength}/5)")
                        confidence += 18
            
            # PRIORITY 3: Visual prediction mode
            if action == 'NO_TRADE' and visual_prediction:
                if channel:
                    if 'up' in channel.pattern_type:
                        action = 'BUY'
                        reasoning.append("📊 Visual: Ascending channel suggests bounce")
                        confidence = 60
                    elif 'down' in channel.pattern_type:
                        action = 'SELL'
                        reasoning.append("📊 Visual: Descending channel suggests rejection")
                        confidence = 60
            
            sl = self.calculate_structural_sl(action, entry, nearest_support, nearest_resistance, zones, channel, atr)
            tp1, tp2, tp3 = self.calculate_multi_tp(action, entry, nearest_resistance, nearest_support, channel, atr)
            tp = tp1
            
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr = round(reward / risk, 2) if risk > 0 else 0.0
            
            visual_story = self.generate_visual_story(current_price, channel, structure, sweeps, 
                                                     nearest_support, nearest_resistance, zones)
            next_move = self.generate_next_move(action, tp1, tp2, tp3, channel, structure, 
                                                nearest_support, nearest_resistance)
            
            if not reasoning:
                reasoning = ["No clear setup - awaiting structure development"]
            
            confidence = min(100.0, max(0.0, confidence))
            
            return TradeSetup(
                action=action,
                entry_price=round(entry, 2),
                sl_price=sl,
                tp_price=tp,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confidence=float(confidence),
                reasoning=reasoning,
                key_levels=key_levels,
                patterns_detected=patterns if patterns else ["No patterns"],
                timeframe=timeframe,
                risk_reward=rr,
                visual_story=visual_story,
                structure_labels=structure,
                next_move=next_move,
                visual_prediction=visual_prediction
            )
        except Exception as e:
            print(f"[ERROR] generate_trade_setup: {e}")
            return self._empty_setup(timeframe, f"Error: {str(e)}")
    
    
    def _empty_setup(self, timeframe: str, reason: str) -> TradeSetup:
        """Generate safe empty setup - DETERMINISTIC fallback"""
        return TradeSetup(
            action='NO_TRADE',
            entry_price=0.0,
            sl_price=0.0,
            tp_price=0.0,
            tp1=0.0,
            tp2=0.0,
            tp3=0.0,
            confidence=0.0,
            reasoning=[reason],
            key_levels={},
            patterns_detected=[],
            timeframe=timeframe,
            risk_reward=0.0,
            visual_story=reason,
            structure_labels=["No data"],
            next_move="⏳ Waiting for data...",
            visual_prediction=False
        )


def analyze_like_human(df_5m: pd.DataFrame, df_15m: pd.DataFrame,
                       df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> Dict:
    """
    Main analysis function - DETERMINISTIC & STABLE
    ALWAYS returns actionable insights
    """
    try:
        analyzer_4h = HumanLikeAnalyzer(lookback_candles=200)
        analyzer_1h = HumanLikeAnalyzer(lookback_candles=300)
        
        setup_4h = analyzer_4h.generate_trade_setup(df_4h, '4H')
        setup_1h = analyzer_1h.generate_trade_setup(df_1h, '1H')
        
        struct_bonus = 0.0
        if setup_4h.structure_labels and setup_1h.structure_labels:
            if any("Bullish" in s for s in setup_4h.structure_labels) and any("Bullish" in s for s in setup_1h.structure_labels):
                struct_bonus = 10.0
            elif any("Bearish" in s for s in setup_4h.structure_labels) and any("Bearish" in s for s in setup_1h.structure_labels):
                struct_bonus = 10.0
        
        pattern_bonus = 0.0
        if setup_4h.patterns_detected and setup_1h.patterns_detected:
            if any("channel" in p for p in setup_4h.patterns_detected) and any("channel" in p for p in setup_1h.patterns_detected):
                pattern_bonus = 8.0
        
        combined_conf = float(setup_4h.confidence * 0.35 + setup_1h.confidence * 0.65 + 
                             struct_bonus + pattern_bonus)
        
        if setup_1h.action == setup_4h.action and setup_1h.action != 'NO_TRADE':
            final_action = setup_1h.action
            final_conf = combined_conf + 12.0
        elif setup_1h.action != 'NO_TRADE':
            final_action = setup_1h.action
            final_conf = float(setup_1h.confidence)
        elif setup_4h.action != 'NO_TRADE':
            final_action = setup_4h.action
            final_conf = float(setup_4h.confidence * 0.8)
        else:
            final_action = 'NO_TRADE'
            final_conf = 0.0
        
        return {
            'action': final_action,
            'confidence': round(min(100.0, max(0.0, final_conf)), 1),
            'timeframe_analysis': {
                '4H': {
                    'action': setup_4h.action,
                    'confidence': round(setup_4h.confidence, 1),
                    'entry': setup_4h.entry_price,
                    'sl': setup_4h.sl_price,
                    'tp': setup_4h.tp_price,
                    'tp1': setup_4h.tp1,
                    'tp2': setup_4h.tp2,
                    'tp3': setup_4h.tp3,
                    'reasoning': setup_4h.reasoning,
                    'patterns': setup_4h.patterns_detected,
                    'key_levels': setup_4h.key_levels,
                    'risk_reward': setup_4h.risk_reward,
                    'visual_story': setup_4h.visual_story,
                    'structure': setup_4h.structure_labels,
                    'next_move': setup_4h.next_move
                },
                '1H': {
                    'action': setup_1h.action,
                    'confidence': round(setup_1h.confidence, 1),
                    'entry': setup_1h.entry_price,
                    'sl': setup_1h.sl_price,
                    'tp': setup_1h.tp_price,
                    'tp1': setup_1h.tp1,
                    'tp2': setup_1h.tp2,
                    'tp3': setup_1h.tp3,
                    'reasoning': setup_1h.reasoning,
                    'patterns': setup_1h.patterns_detected,
                    'key_levels': setup_1h.key_levels,
                    'risk_reward': setup_1h.risk_reward,
                    'visual_story': setup_1h.visual_story,
                    'structure': setup_1h.structure_labels,
                    'next_move': setup_1h.next_move
                }
            },
            'recommendation': {
                'action': final_action,
                'entry': setup_1h.entry_price if final_action != 'NO_TRADE' else 0.0,
                'sl': setup_1h.sl_price if final_action != 'NO_TRADE' else 0.0,
                'tp': setup_1h.tp_price if final_action != 'NO_TRADE' else 0.0,
                'tp1': setup_1h.tp1 if final_action != 'NO_TRADE' else 0.0,
                'tp2': setup_1h.tp2 if final_action != 'NO_TRADE' else 0.0,
                'tp3': setup_1h.tp3 if final_action != 'NO_TRADE' else 0.0,
                'reasoning': setup_1h.reasoning + setup_4h.reasoning,
                'visual_story': setup_1h.visual_story,
                'next_move': setup_1h.next_move
            }
        }
    except Exception as e:
        print(f"[ERROR] analyze_like_human: {e}")
        return {
            'action': 'NO_TRADE',
            'confidence': 0.0,
            'timeframe_analysis': {
                '4H': {'action': 'NO_TRADE', 'confidence': 0.0, 'reasoning': [f"Error: {str(e)}"], 'next_move': '⏳ System error'},
                '1H': {'action': 'NO_TRADE', 'confidence': 0.0, 'reasoning': [f"Error: {str(e)}"], 'next_move': '⏳ System error'}
            },
            'recommendation': {
                'action': 'NO_TRADE',
                'entry': 0.0,
                'sl': 0.0,
                'tp': 0.0,
                'reasoning': [f"Critical error: {str(e)}"],
                'next_move': '⏳ Please check system logs'
            }
        }
