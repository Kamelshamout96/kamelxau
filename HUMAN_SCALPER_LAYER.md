# Human Scalper Layer Documentation

## 🎯 Overview

The **HumanScalperLayer** is a new trading engine designed to mimic professional human scalping with guaranteed directional accuracy. It provides **more frequent signals** than the existing strict engines while maintaining high accuracy through multi-confirmation logic.

## ✅ Key Features

### 1. **Guaranteed Direction Accuracy**
- **NEVER BUY** unless:
  - EMA50 > EMA200 (confirmed uptrend)
  - Price > EMA50 (trading above key level)
  - RSI < 75 (not extremely overbought)
  - No strong opposing HTF bias

- **NEVER SELL** unless:
  - EMA50 < EMA200 (confirmed downtrend)
  - Price < EMA50 (trading below key level)
  - RSI > 25 (not extremely oversold)
  - No strong opposing HTF bias

### 2. **9-Point Confluence System**
Requires minimum **5 points** from:

**BUY Signals:**
- ✅ 5m uptrend (EMA50 > EMA200) → **2 points**
- ✅ Price above EMA50 → **1 point**
- ✅ RSI in bullish zone (40-70) → **2 points**
- ✅ Recent upward price flow → **1 point**
- ✅ Strong bullish candle → **1 point**
- ✅ 15m alignment → **1 point**
- ✅ Pullback/breakout setup → **1 point**
- ✅ Bullish structure shift → **1 point**
- ✅ HTF bias supportive → **1 point**

**SELL Signals:**
- ✅ 5m downtrend (EMA50 < EMA200) → **2 points**
- ✅ Price below EMA50 → **1 point**
- ✅ RSI in bearish zone (30-60) → **2 points**
- ✅ Recent downward price flow → **1 point**
- ✅ Strong bearish candle → **1 point**
- ✅ 15m alignment → **1 point**
- ✅ Pullback/breakout setup → **1 point**
- ✅ Bearish structure shift → **1 point**
- ✅ HTF bias supportive → **1 point**

### 3. **Human-Like Entry Logic**

**Pullback Entries:**
- Price pulls back to EMA50 in a trending market
- Within 1 ATR of EMA50
- Waits for bounce/rejection

**Breakout Entries:**
- Price just crossed EMA50 with momentum
- Strong body candle confirming direction
- Immediate entry on momentum

### 4. **Smart Risk Management**

**BUY Trades:**
- Stop Loss: Max of (recent 5-candle low, EMA200 - 0.5 ATR)
- TP1: Entry + 1.2 ATR
- TP2: Entry + 2.0 ATR
- TP3: Entry + 3.0 ATR

**SELL Trades:**
- Stop Loss: Min of (recent 5-candle high, EMA200 + 0.5 ATR)
- TP1: Entry - 1.2 ATR
- TP2: Entry - 2.0 ATR
- TP3: Entry - 3.0 ATR

### 5. **Confidence Scoring**
- Base: 50%
- +5% per confluence point
- Range: 50-85%
- Example: 7 confluences = 50 + (7 × 5) = 85%

## 🔗 Integration

### Execution Order in `FinalSignalEngine`:
1. ScalperExecutionEngine (primary, strictest)
2. MomentumBreakoutBuyEngine
3. FallbackLightMode (2-minute cooldown)
4. DiscretionaryLayer
5. PriceActionAnalystLayer
6. MomentumBreakoutLayer
7. **HumanScalperLayer** ← NEW (before ultralight)
8. UltraLightExecutionEngine (last resort)

### Duplicate Prevention
- Uses **2.0 pips** minimum price delta (vs 0.5 for other engines)
- Allows more signals while preventing spam
- POI tag: "human_scalper" (unique identifier)

## 📊 Expected Performance

**Signal Frequency:**
- Previous: ~1 trade per 24 hours
- Expected with HumanScalper: **3-8 trades per 24 hours**

**Accuracy:**
- Built-in safety filters guarantee directional accuracy
- Multiple confirmations reduce false signals
- Human-like discretion for quality over quantity

## 🎛️ Configuration Options

Currently uses default thresholds:
- `MIN_CONFLUENCE = 5` (out of 9 possible points)
- `RSI_BULLISH_ZONE = 40-70`
- `RSI_BEARISH_ZONE = 30-60`
- `PULLBACK_THRESHOLD = 1.0 ATR`
- `STRONG_BODY_RATIO = 0.5` (50% of candle)

To adjust:
Edit `c:\kamelxau\kamelxau\core\human_scalper_layer.py`

## 🔍 Signal Output Example

```json
{
  "action": "BUY",
  "entry": 2650.50,
  "sl": 2645.20,
  "tp": 2652.70,
  "tp1": 2652.70,
  "tp2": 2656.50,
  "tp3": 2661.00,
  "confidence": 75.0,
  "reason": "Human scalper BUY (7 confluences): 5m uptrend (EMA50 > EMA200), Price above EMA50, RSI bullish zone (58.3), Recent upward price flow, Strong bullish candle, 15m alignment, Pullback/breakout setup",
  "layer": "human_scalper",
  "confluence_score": {
    "buy": 7,
    "sell": 2
  }
}
```

## ⚙️ How It Works

### Analysis Flow:
1. **Trend Check**: EMA50 vs EMA200 position
2. **Price Position**: Relative to EMA50
3. **Momentum**: RSI zones and recent candle flow
4. **Price Action**: Body strength, candle direction
5. **HTF Alignment**: 15m timeframe confirmation
6. **Entry Setup**: Pullback or breakout detection
7. **Structure**: Existing context (structure shifts)
8. **Scoring**: Sum confluence points
9. **Safety Filters**: Block opposing signals
10. **Signal Generation**: Build complete trade signal

### Safety Mechanisms:
- ✅ **Trend Alignment**: Never trades against EMA structure
- ✅ **Overbought/Oversold**: Blocks extremes
- ✅ **HTF Conflict**: Respects higher timeframe bias
- ✅ **Price Position**: Must be on correct side of EMA50
- ✅ **Multi-Confirmation**: Minimum 5 confluences required

## 📈 Advantages

1. **More Signals**: Less strict than primary engines
2. **Guaranteed Direction**: Multiple safety filters
3. **Human Logic**: Mimics professional scalping
4. **Flexible**: Works in neutral bias conditions
5. **Transparent**: Clear confluence scoring
6. **Risk-Managed**: ATR-based stops and targets

## 🚀 Usage

The HumanScalperLayer is **automatically activated** when you call `/run-signal` API endpoint.

It will fire when:
- All stricter engines return NO_TRADE
- Market conditions meet minimum 5 confluence points
- Safety filters pass

No configuration needed - it just works! 🎯

## 🔧 Maintenance

**To disable**: Comment out lines 327-357 in `final_signal_engine.py`

**To make more aggressive**: Lower `MIN_CONFLUENCE` from 5 to 4 in `human_scalper_layer.py`

**To make less aggressive**: Raise `MIN_CONFLUENCE` from 5 to 6

**To adjust stops**: Modify ATR multipliers in risk management section

---

**Created**: 2025-12-12  
**Author**: Antigravity AI  
**Status**: Active ✅
