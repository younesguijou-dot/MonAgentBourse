import os
import csv
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def envoyer_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=15)
    print("Telegram:", r.status_code, r.text)

def lire_derniere_ligne_csv(path="masi.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    return rows[-1], rows[-2] if len(rows) >= 2 else None

if __name__ == "__main__":
    last, prev = lire_derniere_ligne_csv("masi.csv")

    if not last:
        envoyer_telegram("⚠️ MASI: fichier vide ou non généré.")
        raise SystemExit(1)

    # On ne devine pas les colonnes : on envoie la dernière ligne telle quelle (fiable).
    msg = "📈 MASI (dernière observation)\n\n"
    msg += "\n".join([f"{k}: {v}" for k, v in last.items()])

    envoyer_telegram(msg)
