import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def envoyer_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=15)
    print("Telegram status:", r.status_code)
    print("Telegram response:", r.text)

if __name__ == "__main__":
    envoyer_telegram("✅ Test OK : GitHub Actions -> Telegram fonctionne.")
