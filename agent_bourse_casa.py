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


def fr_to_float(x):
    if x is None:
        return None
    s = str(x).strip().replace("\xa0", " ")
    if s == "" or s.lower() == "nan":
        return None
    s = s.replace("%", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt_price(x):
    v = fr_to_float(x)
    if v is None:
        return "n/a"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fmt_pct_str(pct_raw):
    if pct_raw is None:
        return "(n/a)"
    s = str(pct_raw).strip()
    if s == "" or s.lower() == "nan":
        return "(n/a)"
    return f"({s})"


def potentiel(last_raw, sortie):
    last = fr_to_float(last_raw)
    if last is None or sortie is None or last <= 0:
        return None
    return (sortie - last) / last * 100


def decision(last_raw, achat, sortie):
    last = fr_to_float(last_raw)
    if last is None:
        return "NA", "⚪"
    if last <= achat:
        return "Achat", "🟢"
    if last >= sortie:
        return "Vente", "🔴"
    return "Attente", "🟡"


def read_prices_csv(path):
    prices = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        print("CSV columns:", reader.fieldnames)

        for r in reader:
            sym = (r.get("symbol") or "").strip().upper()
            if not sym:
                continue

            prices[sym] = {
                "last": r.get("last") or r.get("Dernier cours"),
                "pct": r.get("pct") or r.get("Variation en %"),
            }
    return prices


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)
    print("Telegram:", r.status_code, r.text)
    if r.status_code != 200:
        raise RuntimeError("Telegram send failed")


def main():
    prefix = "[TEST] " if BRANCH != "main" else ""

    if not os.path.exists(CSV_PATH):
        msg = prefix + "⚠️ watchlist_prices.csv introuvable (scraper KO)."
        print(msg)
        send_telegram(msg)
        return

    prices = read_prices_csv(CSV_PATH)

    items = []
    for sym, cfg in WATCHLIST.items():
        q = prices.get(sym, {})
        last_raw = q.get("last")
        pct_raw = q.get("pct")

        pot = potentiel(last_raw, cfg["sortie"])
        lab, icon = decision(last_raw, cfg["achat"], cfg["sortie"])

        items.append({
            "sym": sym,
            "type": cfg["type"],
            "achat": cfg["achat"],
            "sortie": cfg["sortie"],
            "last_raw": last_raw,
            "pct_raw": pct_raw,
            "pot": pot,
            "label": lab,
            "icon": icon,
        })

    # tri par potentiel décroissant (None à la fin)
    items.sort(key=lambda x: (x["pot"] is None, -(x["pot"] or -10**9)))

    lines = []
    lines.append(prefix + "📈 Bourse Casa (Auto)")
    lines.append("Signal: 🟡 Neutre")
    lines.append("")
    lines.append("🧾 WATCHLIST (triée par potentiel)")

    for it in items:
        if fr_to_float(it["last_raw"]) is None:
            lines.append(
                f"⚪ {it['sym']}_NA : n/a (n/a) [{it['achat']} - {it['sortie']}] • {it['type']} / pot n/a"
            )
            continue

        lines.append(
            f"{it['icon']} {it['sym']}_{it['label']} : {fmt_price(it['last_raw'])} {fmt_pct_str(it['pct_raw'])} "
            f"[{it['achat']} - {it['sortie']}] • {it['type']} / pot {it['pot']:+.1f}%"
        )

    msg = "\n".join(lines)
    print("=== MESSAGE ===")
    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    main()
