import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise SystemExit("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": "✅ Test Telegram depuis GitHub Actions"}

r = requests.post(url, json=payload, timeout=20)
print("STATUS:", r.status_code)
print("BODY:", r.text)

# Force fail if not OK so you see it in Actions
if r.status_code != 200:
    raise SystemExit("Telegram send failed")
