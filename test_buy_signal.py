"""
Test file to demonstrate BUY signal with mock data
"""
import os
from signal_engine import check_entry
import pandas as pd
import numpy as np

# Telegram settings (optional - will send if configured)
TG_TOKEN = "8512147987:AAEhK8u7a_apAENZgo4V5rP6x9vcm_OClHk"
TG_CHAT = "5326666507"

def create_bullish_signal(price=4236.70):
    """Create mock data that triggers a BUY signal"""
    
    # 4H timeframe - Bullish
    df_4h = pd.DataFrame(index=[0])
    df_4h["close"] = price
    df_4h["ema50"] = price - 20
    df_4h["ema200"] = price - 40
    df_4h["rsi"] = 60
    df_4h["macd"] = 5
    df_4h["macd_signal"] = 3
    df_4h["stoch_k"] = 65
    df_4h["stoch_d"] = 60
    df_4h["adx"] = 28
    df_4h["don_high"] = price + 5
    df_4h["don_low"] = price - 10
    df_4h["atr"] = 3.5
    
    # 1H timeframe - Bullish
    df_1h = df_4h.copy()
    df_1h["close"] = price
    df_1h["ema50"] = price - 15
    df_1h["ema200"] = price - 30
    
    # 15M timeframe - Bullish
    df_15m = df_4h.copy()
    df_15m["close"] = price
    df_15m["ema50"] = price - 10
    df_15m["ema200"] = price - 20
    
    # 5M timeframe - Strong BUY signals on all indicators
    df_5m = pd.DataFrame(index=[0])
    df_5m["close"] = price
    df_5m["ema50"] = price - 5
    df_5m["ema200"] = price - 10
    df_5m["rsi"] = 62  # > 55 ✓
    df_5m["macd"] = 8  # > signal ✓
    df_5m["macd_signal"] = 5
    df_5m["stoch_k"] = 70  # > D ✓
    df_5m["stoch_d"] = 65
    df_5m["adx"] = 26  # > 20 ✓
    df_5m["don_high"] = price - 2  # Price > don_high ✓
    df_5m["don_low"] = price - 15
    df_5m["atr"] = 3.5
    
    return df_5m, df_15m, df_1h, df_4h


def create_bearish_signal(price=4236.70):
    """Create mock data that triggers a SELL signal"""
    
    # 4H timeframe - Bearish
    df_4h = pd.DataFrame(index=[0])
    df_4h["close"] = price
    df_4h["ema50"] = price + 20
    df_4h["ema200"] = price + 40
    df_4h["rsi"] = 38
    df_4h["macd"] = -5
    df_4h["macd_signal"] = -3
    df_4h["stoch_k"] = 35
    df_4h["stoch_d"] = 40
    df_4h["adx"] = 28
    df_4h["don_high"] = price + 10
    df_4h["don_low"] = price - 5
    df_4h["atr"] = 3.5
    
    # 1H timeframe - Bearish
    df_1h = df_4h.copy()
    df_1h["close"] = price
    df_1h["ema50"] = price + 15
    df_1h["ema200"] = price + 30
    
    # 15M timeframe - Bearish
    df_15m = df_4h.copy()
    df_15m["close"] = price
    df_15m["ema50"] = price + 10
    df_15m["ema200"] = price + 20
    
    # 5M timeframe - Strong SELL signals
    df_5m = pd.DataFrame(index=[0])
    df_5m["close"] = price
    df_5m["ema50"] = price + 5
    df_5m["ema200"] = price + 10
    df_5m["rsi"] = 38  # < 45 ✓
    df_5m["macd"] = -8  # < signal ✓
    df_5m["macd_signal"] = -5
    df_5m["stoch_k"] = 30  # < D ✓
    df_5m["stoch_d"] = 35
    df_5m["adx"] = 26  # > 20 ✓
    df_5m["don_high"] = price + 15
    df_5m["don_low"] = price + 2  # Price < don_low ✓
    df_5m["atr"] = 3.5
    
    return df_5m, df_15m, df_1h, df_4h


def send_telegram_test(signal):
    """Send test signal to Telegram"""
    if not TG_TOKEN or not TG_CHAT:
        print("\n⚠️  Telegram not configured, skipping notification")
        return
    
    try:
        import requests
        
        action = signal["action"]
        if action == "NO_TRADE":
            print("\n⚠️  No trade signal, skipping Telegram")
            return
        
        # Format message
        emoji = "🟢" if action == "BUY" else "🔴"
        confidence = signal.get("confidence", "UNKNOWN")
        confidence_emoji = signal.get("confidence_emoji", "")
        
        msg = (
            f"═══════════════════\n"
            f"{emoji} <b>{action} XAUUSD Signal (TEST)</b>\n"
            f"═══════════════════\n\n"
            f"🎯 <b>Confidence:</b> {confidence} {confidence_emoji}\n"
            f"📊 Timeframe: {signal['timeframe']}\n"
            f"💰 Entry Price: {signal['entry']:.2f}\n"
            f"🛑 Stop Loss (SL): {signal['sl']:.2f}\n"
            f"🎯 Take Profit (TP): {signal['tp']:.2f}\n\n"
            f"<i>{'⭐⭐⭐ Most Accurate' if confidence == 'HIGH' else '⭐⭐ Less Accurate'}</i>\n"
            f"⚠️ <i>This is a TEST signal with mock data</i>\n"
            f"═══════════════════"
        )
        
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {
            "chat_id": TG_CHAT,
            "text": msg,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"\n✅ Telegram notification sent successfully!")
        
    except Exception as e:
        print(f"\n❌ Failed to send Telegram: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING BUY SIGNAL (Mock Data)")
    print("=" * 60)
    
    # Test BUY signal
    df_5m, df_15m, df_1h, df_4h = create_bullish_signal(price=4236.70)
    buy_signal = check_entry(df_5m, df_15m, df_1h, df_4h)
    
    print("\n📊 BUY Signal Result:")
    print(buy_signal)
    
    if buy_signal["action"] == "BUY":
        print("\n✅ BUY Signal Generated Successfully!")
        send_telegram_test(buy_signal)
    else:
        print(f"\n❌ Expected BUY but got: {buy_signal}")
    
    print("\n" + "=" * 60)
    print("🧪 TESTING SELL SIGNAL (Mock Data)")
    print("=" * 60)
    
    # Test SELL signal
    df_5m, df_15m, df_1h, df_4h = create_bearish_signal(price=4236.70)
    sell_signal = check_entry(df_5m, df_15m, df_1h, df_4h)
    
    print("\n📊 SELL Signal Result:")
    print(sell_signal)
    
    if sell_signal["action"] == "SELL":
        print("\n✅ SELL Signal Generated Successfully!")
        send_telegram_test(sell_signal)
    else:
        print(f"\n❌ Expected SELL but got: {sell_signal}")
    
    print("\n" + "=" * 60)
    print("✅ Testing Complete!")
    print("=" * 60)
    print("\nNote: These are MOCK signals for testing purposes.")
    print("Real signals require actual market conditions to align.")
