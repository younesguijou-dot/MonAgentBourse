import os
import csv
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BRANCH = os.getenv("GITHUB_REF_NAME", "unknown")

WATCHLIST = {
    "SNEP": {"type": "Pivot", "achat": 495.0, "sortie": 610.0},
    "HPS":  {"type": "Pivot", "achat": 556.0, "sortie": 675.0},
    "IAM":  {"type": "Dividende", "achat": 109.0, "sortie": 130.0},
    "TGCC": {"type": "Growth", "achat": 900.0, "sortie": 980.0},
}

CSV_PATH = "watchlist_prices.csv"


def _to_float(x):
    if x is None:
        return None
    s = str(x).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_price(x):
    if x is None:
        return "n/a"
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_pct(p):
    if p is None:
        return "(n/a)"
    return f"({p:+.1f}%)"


def potentiel(last, sortie):
    if last is None or sortie is None or last <= 0:
        return None
    return (sortie - last) / last * 100


def decision(last, achat, sortie):
    if last is None:
        return "NA", "⚪"
    if last <= achat:
        return "Achat", "🟢"
    if last >= sortie:
        return "Vente", "🔴"
    return "Attente", "🟡"


def read_prices_csv(path):
    """
    Attend un CSV:
    symbol,last,pct
    SNEP,492,3
    """
    prices = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return prices
        for r in reader:
            sym = (r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            prices[sym] = {
                "last": _to_float(r.get("last")),
                "pct": _to_float(r.get("pct")),
            }
    return prices


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)

    # Force visible debug
    print("Telegram status:", r.status_code)
    print("Telegram body:", r.text)

    if r.status_code != 200:
        raise RuntimeError("Telegram send failed")


def build_message(prices):
    prefix = "[TEST] " if BRANCH != "main" else ""

    items = []
    for sym, cfg in WATCHLIST.items():
        q = prices.get(sym, {})
        last = q.get("last")
        pct = q.get("pct")

        pot = potentiel(last, cfg["sortie"])
        lab, icon = decision(last, cfg["achat"], cfg["sortie"])

        items.append({
            "sym": sym,
            "type": cfg["type"],
            "achat": cfg["achat"],
            "sortie": cfg["sortie"],
            "last": last,
            "pct": pct,
            "pot": pot,
            "label": lab,
            "icon": icon,
        })

    # tri: potentiel desc, None à la fin
    items.sort(key=lambda x: (x["pot"] is None, -(x["pot"] or -10**9)))

    lines = []
    lines.append(prefix + "📈 Bourse Casa (Auto)")
    lines.append("Signal: 🟡 Neutre")
    lines.append("")
    lines.append("🧾 WATCHLIST (triée par potentiel)")

    for it in items:
        if it["last"] is None:
            lines.append(
                f"⚪ {it['sym']}_NA : n/a (n/a) [{fmt_price(it['achat'])} - {fmt_price(it['sortie'])}] • "
                f"{it['type']} / pot n/a"
            )
            continue

        lines.append(
            f"{it['icon']} {it['sym']}_{it['label']} : {fmt_price(it['last'])} {fmt_pct(it['pct'])} "
            f"[{fmt_price(it['achat'])} - {fmt_price(it['sortie'])}] • {it['type']} / pot {it['pot']:+.1f}%"
        )

    # Message non vide garanti
    return "\n".join(lines)


def main():
    # Toujours envoyer quelque chose
    if not os.path.exists(CSV_PATH):
        msg = f"⚠️ watchlist_prices.csv introuvable. Scraper KO ou fichier non généré.\nBranch: {BRANCH}"
        print(msg)
        send_telegram(msg)
        return

    prices = read_prices_csv(CSV_PATH)

    msg = build_message(prices)

    print("=== MESSAGE TELEGRAM ===")
    print(msg)

    send_telegram(msg)


if __name__ == "__main__":
    main()
