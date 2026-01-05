import os
import csv
import re
import requests
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BRANCH = os.getenv("GITHUB_REF_NAME", "unknown")

# ================= WATCHLIST (codes BVC OFFICIELS) =================
WATCHLIST = {
    "SNEP": {
        "type": "Pivot",
        "achat": 495.0,
        "sortie": 610.0,
        "bvc_codes": ["SNP"]
    },
    "IAM": {
        "type": "Dividende",
        "achat": 109.0,
        "sortie": 130.0,
        "bvc_codes": ["IAM"]
    },
    "HPS": {
        "type": "Pivot",
        "achat": 556.0,
        "sortie": 675.0,
        "bvc_codes": ["HPS"]
    },
    "TGCC": {
        "type": "Growth",
        "achat": 900.0,
        "sortie": 980.0,
        "bvc_codes": ["TGC"]
    }
}

URL_MARCHE_ACTIONS = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"

# ================= TELEGRAM =================
def envoyer_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=20)

# ================= UTILS =================
def to_float(txt):
    if txt is None:
        return None
    try:
        return float(txt.replace(" ", "").replace(",", "."))
    except:
        return None

def fmt_price(v):
    return "n/a" if v is None else f"{v:.2f}".rstrip("0").rstrip(".")

def fmt_pct(p):
    if p is None:
        return "(n/a)"
    return f"({p:+.1f}%)"

# ================= SCRAPER LIVE MARKET =================
def fetch_quotes():
    html = requests.get(URL_MARCHE_ACTIONS, headers={"User-Agent": "Mozilla/5.0"}).text
    soup = BeautifulSoup(html, "html.parser")

    found = {}

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue

        code = cells[0].upper()
        if code in ["SNP", "IAM", "HPS", "TGC"]:
            row = " ".join(cells)
            nums = re.findall(r"[-+]?\d[\d\s]*,\d+|[-+]?\d+", row)
            vals = [to_float(n) for n in nums if to_float(n) is not None]

            last = next((v for v in vals if v > 0), None)
            pct = next((v for v in vals if -50 < v < 50 and v != last), None)

            found[code] = {"last": last, "pct": pct}

    return found

# ================= LOGIQUE METIER =================
def reco(last, achat, sortie):
    if last is None:
        return "⚪", "Donnée manquante"
    if last <= achat:
        return "🟢", "Achat"
    if last >= sortie:
        return "🔴", "Vente"
    return "🟡", "Attente"

def potentiel(last, sortie):
    if last is None or sortie is None:
        return None
    return (sortie - last) / last * 100

# ================= MAIN =================
def main():
    prefix = "[TEST] " if BRANCH != "main" else ""
    quotes = fetch_quotes()

    lines = [prefix + "📊 Bourse Casa (Auto)", "", "🧾 WATCHLIST (triée par potentiel)"]

    rows = []
    for name, cfg in WATCHLIST.items():
        code = cfg["bvc_codes"][0]
        q = quotes.get(code, {})
        last = q.get("last")
        pct = q.get("pct")

        pot = potentiel(last, cfg["sortie"])
        icon, rec = reco(last, cfg["achat"], cfg["sortie"])

        rows.append((pot if pot else -999, name, cfg, last, pct, icon, rec))

    rows.sort(reverse=True)

    for _, name, cfg, last, pct, icon, rec in rows:
        lines.append(
            f"- {name}_{cfg['type']} : {fmt_price(last)} {fmt_pct(pct)} "
            f"[🟢{fmt_price(cfg['achat'])} - 🔴{fmt_price(cfg['sortie'])}] • "
            f"{icon} {rec}" +
            (f" ({potentiel(last, cfg['sortie']):+.1f}% pot.)" if last else "")
        )

    envoyer_telegram("\n".join(lines))

if __name__ == "__main__":
    main()
