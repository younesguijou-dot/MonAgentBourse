import os, csv, json
import requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CSV_PATH = "watchlist_prices.csv"
WATCHLIST_PATH = "watchlist.json"


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


def fmt_pct(pct_raw):
    if pct_raw is None:
        return "n/a"
    s = str(pct_raw).strip()
    if s == "" or s.lower() == "nan":
        return "n/a"
    return s


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram send failed: {r.status_code} {r.text}")


def read_watchlist():
    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_prices():
    prices = {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sym = (r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            prices[sym] = {"last": r.get("last"), "pct": r.get("pct")}
    return prices


def decision_icon(last, achat, sortie):
    if last is None:
        return "⚪", "NA"
    if last <= achat:
        return "🟢", "Achat"
    if last >= sortie:
        return "🔴", "Vente"
    return "🟡", "Attente"


def main():
    if not os.path.exists(CSV_PATH):
        send_telegram("⚠️ Données indisponibles (watchlist_prices.csv introuvable).")
        return

    if not os.path.exists(WATCHLIST_PATH):
        send_telegram("⚠️ watchlist.json introuvable. Ajoute le fichier de configuration.")
        return

    wl = read_watchlist()
    px = read_prices()

    items = []
    for sym, cfg in wl.items():
        q = px.get(sym, {})
        last = fr_to_float(q.get("last"))
        pct_raw = q.get("pct")

        achat = float(cfg["achat"])
        sortie = float(cfg["sortie"])
        cat = cfg.get("categorie", "NA")

        pot = None if (last is None or last <= 0) else (sortie - last) / last * 100
        dist_achat = None if last is None else (last - achat) / achat * 100  # >0 au-dessus achat

        icon, label = decision_icon(last, achat, sortie)

        # score opportunité (simple, lisible)
        # +potentiel, +proximité achat (plus proche = meilleur), pénalité si très loin
        score = 0
        if pot is not None:
            score += pot
        if dist_achat is not None:
            score += max(0, 8 - abs(dist_achat))  # bonus si proche (±8%)
        items.append({
            "sym": sym,
            "cat": cat,
            "achat": achat,
            "sortie": sortie,
            "last": last,
            "pct_raw": pct_raw,
            "pot": pot,
            "dist_achat": dist_achat,
            "icon": icon,
            "label": label,
            "score": score
        })

    items.sort(key=lambda x: x["score"], reverse=True)

    now = datetime.now().strftime("%d/%m %H:%M")
    header = f"📈 Bourse Casa (Auto) — 🟡 Neutre\n{now}"

    # Top opportunité (celle la plus proche zone achat ou meilleur score)
    top = items[0] if items else None
    top_line = ""
    if top and top["last"] is not None and top["dist_achat"] is not None:
        top_line = f"\nTop: {top['icon']} {top['sym']} ({top['label']}) | pot {top['pot']:+.1f}% | Δachat {top['dist_achat']:+.1f}%"

    lines = [header + top_line, ""]
    for it in items:
        if it["last"] is None:
            lines.append(f"⚪ {it['sym']}_NA : n/a (n/a) [{it['achat']:.0f}→{it['sortie']:.0f}] • {it['cat']} • pot n/a")
            continue

        lines.append(
            f"{it['icon']} {it['sym']}_{it['label']} : {fmt_price(it['last'])} ({fmt_pct(it['pct_raw'])}) "
            f"[{it['achat']:.0f}→{it['sortie']:.0f}] • {it['cat']} • pot {it['pot']:+.1f}% • Δachat {it['dist_achat']:+.1f}%"
        )

    msg = "\n".join(lines).strip()
    send_telegram(msg)


if __name__ == "__main__":
    main()
