# Quick Telegram Setup Guide 📱

## What You Need
1. A Telegram account
2. 5 minutes of your time

## Steps

### 1️⃣ Create Your Bot

1. Open Telegram on your phone or desktop
2. Search for: **@BotFather**
3. Start a chat and send: `/newbot`
4. Follow the prompts:
   - **Bot name**: "My XAUUSD Signal Bot" (or any name you like)
   - **Username**: Must be unique and end with "bot" (e.g., `my_xauusd_signal_bot`)
5. **@BotFather will reply with your token**:
   ```
   Done! Congratulations on your new bot...
   Use this token to access the HTTP API:
   6234567890:ABCdefGHIjkLMNopQRSTuvWXyz
   ```
6. **SAVE THIS TOKEN!** You'll need it.

### 2️⃣ Get Your Chat ID

**Method 1 - Using getUpdates:**
1. First, send a message to your new bot (send anything, like "Hello")
2. Open your browser and paste this URL (replace TOKEN with your actual token):
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Example:
   ```
   https://api.telegram.org/bot6234567890:ABCdefGHIjkLMNopQRSTuvWXyz/getUpdates
   ```
3. You'll see JSON response. Look for:
   ```json
   "chat":{"id":123456789,...
   ```
4. That number is your Chat ID!

**Method 2 - Using @userinfobot:**
1. Search for **@userinfobot** in Telegram
2. Send `/start`
3. It will show your User ID directly

### 3️⃣ Set Environment Variables

**Windows (PowerShell) - Temporary:**
```powershell
# Replace with YOUR actual token and chat ID
$env:TG_TOKEN="6234567890:ABCdefGHIjkLMNopQRSTuvWXyz"
$env:TG_CHAT="123456789"
```

**Windows (PowerShell) - Permanent:**
```powershell
# Run PowerShell as Administrator, then:
[System.Environment]::SetEnvironmentVariable('TG_TOKEN', '6234567890:ABCdefGHIjkLMNopQRSTuvWXyz', 'User')
[System.Environment]::SetEnvironmentVariable('TG_CHAT', '123456789', 'User')

# Then restart PowerShell/Terminal
```

**Linux/Mac:**
```bash
# Add to ~/.bashrc or ~/.zshrc
export TG_TOKEN="6234567890:ABCdefGHIjkLMNopQRSTuvWXyz"
export TG_CHAT="123456789"

# Then reload
source ~/.bashrc  # or source ~/.zshrc
```

### 4️⃣ Test Your Setup

Run the test script:
```bash
python test_telegram.py
```

You should see:
```
Token: 6234567890:ABCdefGH...
Chat ID: 123456789

✅ SUCCESS! Check your Telegram for the test message!
```

And receive this in Telegram:
```
🧪 Test Message from XAUUSD Signal Tool

If you see this, Telegram is working! ✅
```

## 🎉 Done!

Now when you run the trading signal tool, you'll receive alerts like:

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

## ⚠️ Troubleshooting

### "Token: NOT SET"
- You didn't set the environment variables
- Or you set them in a different terminal/PowerShell session
- Solution: Set them again in the current session

### "Unauthorized"
- Wrong token
- Check you copied the entire token from @BotFather

### "Chat not found"
- Wrong Chat ID
- Or you didn't send a message to your bot first
- Solution: Send a message to your bot, then get the Chat ID again

### "Failed to send"
- Check internet connection
- Telegram servers might be down (rare)
- Wait a minute and try again

## 📝 Notes

- **Telegram is OPTIONAL** - The tool works without it and returns signals via the API
- Your token is like a password - keep it secret!
- You can send messages to yourself OR to a group:
  - For yourself: Use your personal Chat ID
  - For a group: Add the bot to the group, then get the group's Chat ID

---

**Need help?** The tool will print helpful error messages if something goes wrong!
