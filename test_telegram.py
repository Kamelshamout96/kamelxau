import os
import requests

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

print(f"Token: {TG_TOKEN[:20]}..." if TG_TOKEN else "Token: NOT SET")
print(f"Chat ID: {TG_CHAT}")

if not TG_TOKEN or not TG_CHAT:
    print("\n❌ Please set TG_TOKEN and TG_CHAT environment variables!")
    print("\nPowerShell commands:")
    print('$env:TG_TOKEN="your_bot_token"')
    print('$env:TG_CHAT="your_chat_id"')
    exit(1)

# Test sending a message
url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
payload = {
    "chat_id": TG_CHAT,
    "text": "🧪 <b>Test Message from XAUUSD Signal Tool</b>\n\nIf you see this, Telegram is working! ✅",
    "parse_mode": "HTML"
}

try:
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    print("\n✅ SUCCESS! Check your Telegram for the test message!")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print(f"\nResponse: {response.text if 'response' in locals() else 'No response'}")
