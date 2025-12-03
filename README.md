# XAUUSD Trading Signal Tool 🚀

## 📋 Overview
Automated trading signals for XAUUSD (Gold) using multi-timeframe technical analysis. Get **accurate signals from the FIRST call** - no waiting for data accumulation!

## ✨ Key Features
- ✅ **Instant Analysis**: Works from the first API call using historical data
- 📊 **Multi-timeframe**: Analyzes 5m, 15m, 1h, and 4h simultaneously
- 🎯 **Smart Entry**: Only signals when all timeframes align
- 💰 **Auto Risk Management**: SL (1.5x ATR) and TP (3x ATR)
- 📱 **Telegram Alerts**: Beautiful formatted notifications
- ⚡ **Fast & Cached**: 5-minute data caching for performance

### Technical Indicators Used:
- **EMA 50 & 200** - Trend identification
- **RSI** - Momentum
- **Stochastic Oscillator** - Overbought/Oversold
- **MACD** - Trend confirmation
- **ADX** - Trend strength
- **ATR** - Volatility & risk calculation
- **Donchian Channels** - Breakout detection

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables (Optional for Telegram)
```bash
# Windows PowerShell
$env:TG_TOKEN="8512147987:AAEhK8u7a_apAENZgo4V5rP6x9vcm_OClHk"
$env:TG_CHAT="5326666507"

# Linux/Mac
export TG_TOKEN="your_telegram_bot_token"
export TG_CHAT="your_chat_id"
```

**Note:** Telegram is OPTIONAL. The tool works without it and returns signals via API.

### 3. Required Firestore Environment Variables (storage backend)
The collector now writes/reads 1m candles from Firestore instead of local CSV. Configure:
```bash
# Windows PowerShell
$env:GOOGLE_CREDENTIALS_JSON='{
  "type": "service_account",
  "project_id": "kamel-xau",
  "private_key_id": "22819792e04a67c05566826db9fc4ce3e9e0446f",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQDbQIKZ2vDc0gSV\n7+ncze2JIykDHp+E7HqzXOxgqH83tF2VgBwqyeWfItXHtYmtCV2I1TM1GbQST/r4\nCZ3kF4we8W5JW94fbKxFw88PHF+W6kUHopHjrTh2SYxWVxtpM0H+REMMdvYl0jsO\n0qL/kfh2iNcqO5Y9wXedPGjJj7VxBG0J/o8fCnzegdIBuqhW+H9eIqBjQuBwiulZ\nAo7jhPgHsE3DfDwKhoVdgbWXA+FMTxGoYsyMD0azoC5vp9DgimqgtMsjB0DecLLD\nZeO7q5hKLZ6UUAkKNWosKSlwqey1KS1VvrcD2Fvbwjf1vygMiiAX0wKMWFvY8UsJ\nFlU8+sWxAgMBAAECggEAaX4fmMGkdMtEU5RM9OXMbdiSCiM4468Y1qZWQaexFm9d\nO+qZIulj527OZ7nsVWqVK5pRejI01z7OZXvTEYVW8Sh/RSLDvGEAfszZGs8vGyD7\nN9I72c1lxlxa/swIr1RvY1Ua4at3gfkmW1pz/P4SC46J4JMtFee5ktkXHixcQ9TV\n1Y7mzP4DOriPvw1dM6EuUebQk6D9DicMLEep1yDCJdCGcLmTm0a241ozvt2x+fSE\nK2Wxr742395G2u2FzB1SVfWskGdqcDZkF+we9koTYPcBNG/CB3hIDJkTliXQuK1E\ncCZYNhpKzBbGqqhix7x9Hi5kRYHC4rAUH69rzJ96VQKBgQD9aalWC7IlWE52i0I6\nt7VaEeYGKRkcBCjUuT9FX+PXlwa5cF7dLzcJVqkGsUwwxpgi9+xCAzzF8tjHbYfM\nRo9AxGEqfnPSsPYckHiCGJ7A87/7AuZh1ze5/ONV934cbIMJbMBjaMpgOnS9KmK4\nF7+NmbDaZa9xXUVmWHBEpLu4FwKBgQDdfZBIL1bQVmSAtJNtn0aB1OC0m9DU97pV\net2dSltWiXePMysatAfakvI/W2QtEAiBfxh++nMGTSVsuuxF5KuO5JEc1KMwi5C3\nF6v62HQFiAuZS2hJElonSrZShIBT+k5F5hjQcrGOCzQchOJXCA/4XbZS0pOT0I7+\nOX1GDfZFdwKBgQDZMnXT7SRcQ8rEaelzAD/smgioYRNHYv1IDhp/sIdNIgG+cOSt\n+SjX1TH8LXwbFiwRVKNnlPTCyLkqfON2n0drAKYzULye6dOXee//uXBf+ssiLkMd\nuuPlgi2rYfvyCsNpEY/35DoIrjGebLS+CoTArejZ12u+4213Ifffrb3DMwKBgQCI\nJ6rtJOSqF6GamObUCYhPQWyMuggrEsohx/C5wz7YuJKdnefOd4MocxKlremr5eJE\nsLt/OzhAVGZAK7wYzxRDN/CYl4Jl0jW4x71561uPFu2CY5+M49I1uzDPExLMDN/X\nCjaQ1SCe3/Y93dZBh/xBQmJVEYuU3y03zGFdEjIkywKBgQCWkVL1GLNjr0JYVyds\nQodeFItiiH75PPsiGp+hgsZhp8Blzejz+kGl7Fp29jFm8Kth/Pkp9W83KB7kKZqS\nxCDR+Ev4h/Dar1D/cRWAyFI0iGJrOkxJdrIGnNArhjbfk0r7o0rONuimMbxgN4EX\nceqbQxL5+H/MeK1CLXeOoIsZRQ==\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@kamel-xau.iam.gserviceaccount.com",
  "client_id": "108264481792120676498",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40kamel-xau.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}'
$env:FIRESTORE_PROJECT_ID='kamel-xau'

# Linux/Mac
export GOOGLE_CREDENTIALS_JSON='{
  "type": "service_account",
  "project_id": "kamel-xau",
  "private_key_id": "22819792e04a67c05566826db9fc4ce3e9e0446f",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQDbQIKZ2vDc0gSV\n7+ncze2JIykDHp+E7HqzXOxgqH83tF2VgBwqyeWfItXHtYmtCV2I1TM1GbQST/r4\nCZ3kF4we8W5JW94fbKxFw88PHF+W6kUHopHjrTh2SYxWVxtpM0H+REMMdvYl0jsO\n0qL/kfh2iNcqO5Y9wXedPGjJj7VxBG0J/o8fCnzegdIBuqhW+H9eIqBjQuBwiulZ\nAo7jhPgHsE3DfDwKhoVdgbWXA+FMTxGoYsyMD0azoC5vp9DgimqgtMsjB0DecLLD\nZeO7q5hKLZ6UUAkKNWosKSlwqey1KS1VvrcD2Fvbwjf1vygMiiAX0wKMWFvY8UsJ\nFlU8+sWxAgMBAAECggEAaX4fmMGkdMtEU5RM9OXMbdiSCiM4468Y1qZWQaexFm9d\nO+qZIulj527OZ7nsVWqVK5pRejI01z7OZXvTEYVW8Sh/RSLDvGEAfszZGs8vGyD7\nN9I72c1lxlxa/swIr1RvY1Ua4at3gfkmW1pz/P4SC46J4JMtFee5ktkXHixcQ9TV\n1Y7mzP4DOriPvw1dM6EuUebQk6D9DicMLEep1yDCJdCGcLmTm0a241ozvt2x+fSE\nK2Wxr742395G2u2FzB1SVfWskGdqcDZkF+we9koTYPcBNG/CB3hIDJkTliXQuK1E\ncCZYNhpKzBbGqqhix7x9Hi5kRYHC4rAUH69rzJ96VQKBgQD9aalWC7IlWE52i0I6\nt7VaEeYGKRkcBCjUuT9FX+PXlwa5cF7dLzcJVqkGsUwwxpgi9+xCAzzF8tjHbYfM\nRo9AxGEqfnPSsPYckHiCGJ7A87/7AuZh1ze5/ONV934cbIMJbMBjaMpgOnS9KmK4\nF7+NmbDaZa9xXUVmWHBEpLu4FwKBgQDdfZBIL1bQVmSAtJNtn0aB1OC0m9DU97pV\net2dSltWiXePMysatAfakvI/W2QtEAiBfxh++nMGTSVsuuxF5KuO5JEc1KMwi5C3\nF6v62HQFiAuZS2hJElonSrZShIBT+k5F5hjQcrGOCzQchOJXCA/4XbZS0pOT0I7+\nOX1GDfZFdwKBgQDZMnXT7SRcQ8rEaelzAD/smgioYRNHYv1IDhp/sIdNIgG+cOSt\n+SjX1TH8LXwbFiwRVKNnlPTCyLkqfON2n0drAKYzULye6dOXee//uXBf+ssiLkMd\nuuPlgi2rYfvyCsNpEY/35DoIrjGebLS+CoTArejZ12u+4213Ifffrb3DMwKBgQCI\nJ6rtJOSqF6GamObUCYhPQWyMuggrEsohx/C5wz7YuJKdnefOd4MocxKlremr5eJE\nsLt/OzhAVGZAK7wYzxRDN/CYl4Jl0jW4x71561uPFu2CY5+M49I1uzDPExLMDN/X\nCjaQ1SCe3/Y93dZBh/xBQmJVEYuU3y03zGFdEjIkywKBgQCWkVL1GLNjr0JYVyds\nQodeFItiiH75PPsiGp+hgsZhp8Blzejz+kGl7Fp29jFm8Kth/Pkp9W83KB7kKZqS\nxCDR+Ev4h/Dar1D/cRWAyFI0iGJrOkxJdrIGnNArhjbfk0r7o0rONuimMbxgN4EX\nceqbQxL5+H/MeK1CLXeOoIsZRQ==\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@kamel-xau.iam.gserviceaccount.com",
  "client_id": "108264481792120676498",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40kamel-xau.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}'
export FIRESTORE_PROJECT_ID='kamel-xau'
```
Tips:
- استخدم Service Account مع صلاحية Firestore (Owner/Editor على الأقل للمشروع أو دور مخصص).
- الصق JSON كاملًا في المتغير (لا مسار ملف).
- مجموعة التخزين الافتراضية: `live_candles`، كل وثيقة اسمها timestamp بالدقيقة.

### 3. Run the Server
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Get Your First Signal!
```bash
# Open browser or use curl
curl http://localhost:8000/run-signal
```

## 📡 API Usage

### Endpoint: `/run-signal`
**Method:** GET  
**URL:** `http://localhost:8000/run-signal`

### Response Examples

#### ✅ BUY Signal
```json
{
  "action": "BUY",
  "entry": 2650.50,
  "sl": 2645.30,
  "tp": 2660.90,
  "timeframe": "5m"
}
```

#### ✅ SELL Signal
```json
{
  "action": "SELL",
  "entry": 2650.50,
  "sl": 2655.70,
  "tp": 2639.90,
  "timeframe": "5m"
}
```

#### ℹ️ No Trade
```json
{
  "action": "NO_TRADE",
  "reason": "HTF mismatch or neutral"
}
```

Possible reasons:
- `"HTF mismatch or neutral"` - Higher timeframes don't agree or are neutral
- `"15m disagrees with HTF"` - 15-minute timeframe doesn't confirm
- `"No confluence on 5m"` - All conditions not met for entry

## 📱 Telegram Setup (Optional)

### Get Telegram Bot Token
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow instructions
3. Copy the token (format: `123456789:ABCdef...`)

### Get Your Chat ID
1. Send any message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the response
4. Use that number as your `TG_CHAT`

### Telegram Message Format
```
═══════════════════
🟢 BUY XAUUSD Signal
═══════════════════

📊 Timeframe: 5m
💰 Entry Price: 2650.50
🛑 Stop Loss (SL): 2645.30
🎯 Take Profit (TP): 2660.90

═══════════════════
```

## 🎯 Trading Logic

### Multi-Timeframe Alignment
The tool requires ALL timeframes to agree before generating a signal:

1. **4H + 1H** must show the same trend (bullish or bearish)
2. **15M** must confirm the higher timeframe trend
3. **5M** provides the precise entry when all indicators align

### BUY Signal Requirements (All must be true)
- ✅ 1H & 4H both bullish (Price > EMA200, EMA50 > EMA200)
- ✅ 15M confirms bullish trend
- ✅ RSI > 55
- ✅ MACD > MACD Signal
- ✅ Stochastic K > Stochastic D
- ✅ ADX > 20 (strong trend)
- ✅ Price breaks above Donchian High

### SELL Signal Requirements (All must be true)
- ✅ 1H & 4H both bearish (Price < EMA200, EMA50 < EMA200)
- ✅ 15M confirms bearish trend
- ✅ RSI < 45
- ✅ MACD < MACD Signal
- ✅ Stochastic K < Stochastic D
- ✅ ADX > 20 (strong trend)
- ✅ Price breaks below Donchian Low

## 🔧 How It Works

### Data Source
- Uses **Yahoo Finance** (Gold Futures: GC=F)
- Fetches 30 days of 1-minute historical data
- No API key required!
- Free and reliable

### Caching System
- Data is cached for **5 minutes**
- First call: Fetches fresh data (~30 seconds)
- Subsequent calls: Uses cache (instant response)
- Automatic refresh every 5 minutes

### File Structure
```
Tool/
├── app.py              # FastAPI server & main endpoint
├── signal_engine.py    # Trading signal logic
├── indicators.py       # Technical indicator calculations
├── utils.py            # Data fetching & Telegram
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── data/              # Auto-created cache directory
    └── xau_cache.csv  # Cached historical data
```

## 🛠️ Advanced Usage

### Custom Timeframes
You can modify timeframes in `app.py`:
```python
candles_5m = to_candles(hist, "5T")   # 5 minutes
candles_15m = to_candles(hist, "15T") # 15 minutes
candles_1h = to_candles(hist, "60T")  # 1 hour
candles_4h = to_candles(hist, "240T") # 4 hours
```

### Adjust Data Period
In `utils.py`, modify the fetch parameters:
```python
df = fetch_gold_historical_data(period="60d", interval="1m")
```

Options:
- **period**: 1d, 5d, 7d, 1mo, 3mo, 6mo, 1y, 2y, 5y
- **interval**: 1m, 2m, 5m, 15m, 30m, 60m, 1h, 1d

### Cache Duration
In `utils.py`, adjust cache freshness:
```python
CACHE_DURATION = timedelta(minutes=5)  # Change to your preference
```

## 📊 Testing

### Manual Test
```bash
# Start server
uvicorn app:app --reload

# In another terminal
curl http://localhost:8000/run-signal
```

### Continuous Monitoring
```bash
# Check every 5 minutes
while true; do
  curl http://localhost:8000/run-signal
  sleep 300
done
```

## ⚠️ Important Notes

### First Run
- First call takes ~30 seconds to fetch historical data
- Subsequent calls are instant (using cache)
- Data refreshes automatically every 5 minutes

### Market Hours
- Gold futures (GC=F) trade nearly 24/5
- Best signals during active market hours
- Reduced liquidity on weekends

### Risk Warning
⚠️ **This tool is for educational purposes only**
- Always do your own research
- Never risk more than you can afford to lose
- Past performance doesn't guarantee future results
- Test on demo account first

## 🐛 Troubleshooting

### "Not enough candles after resampling"
**Solution:** The 4-hour timeframe needs more data. Options:
1. Increase period: `fetch_gold_historical_data(period="60d", interval="1m")`
2. Or remove 4h timeframe from analysis

### "Failed to fetch gold data"
**Solution:**
- Check internet connection
- Yahoo Finance might be temporarily down
- Try again in a few minutes

### Telegram not working
**Solution:**
- Verify `TG_TOKEN` and `TG_CHAT` are set correctly
- Token format: `123456789:ABCdefGHIjklMNO...`
- Chat ID should be a number
- The tool works fine without Telegram!

### Cache issues
**Solution:** Delete cache file:
```bash
# Windows
del data\xau_cache.csv

# Linux/Mac
rm data/xau_cache.csv
```

## 🚀 Deployment

### Render.com
1. Push to GitHub
2. Connect repository to Render
3. Set environment variables in dashboard
4. Deploy!

The included `render.yaml` handles configuration.

### Other Platforms
Works on:
- Heroku
- Railway
- DigitalOcean
- AWS/GCP/Azure
- Any platform supporting Python + FastAPI

## 📝 License

This tool is provided as-is for educational purposes.

## 🤝 Contributing

Found a bug or have a feature request? Feel free to modify and improve!

---

**Made with ❤️ for traders**
