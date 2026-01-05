import os
import csv
import re
import requests
import certifi
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BRANCH = os.getenv("GITHUB_REF_NAME", "unknown")

# Codes BVC (pas ISIN)
WATCHLIST = {
    "SNEP": {"type": "Pivot", "achat": 495.0, "sortie": 610.0, "bvc_codes": ["SNP"]},
    "IAM":  {"type": "Dividende", "achat": 109.0, "sortie": 130.0, "bvc_codes": ["IAM"]},
    "HPS":  {"type": "Pivot", "achat": 556.0, "sortie": 675.0, "bvc_codes": ["HPS"]},
    "TGCC": {"type": "Growth", "achat": 900.0, "sortie": 980.0, "bvc_codes": ["TGC"]},
}

URL_MARCHE_ACTIONS = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"

def envoyer_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=20)
    print("Telegram:", r.status_code, r.text)

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

def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def pick_col(rows, candidates):
    if not rows:
        return None
    cols = set(rows[0].keys())
    for c in candidates:
        if c in cols:
            return c
    lower_map = {k.lower(): k for k in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None

def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

# ---------- MASI (optionnel, si masi.csv existe) ----------
def read_masi_signal():
    try:
        rows = read_csv_rows("masi.csv")
    except FileNotFoundError:
        return None
    if not rows:
        return None

    date_col = pick_col(rows, ["Date", "date", "DATE"])
    value_col = pick_col(rows, ["MASI", "Close", "close", "Value", "value", "Index", "index"])
    var_col = pick_col(rows, ["Variation", "variation", "Var", "var", "Change", "change", "Pct", "pct", "Percent", "percent"])

    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None

    date = last.get(date_col) if date_col else None
    value = _to_float(last.get(value_col)) if value_col else None

    variation = _to_float(last.get(var_col)) if var_col else None
    if variation is None and value is not None and prev and value_col:
        prev_value = _to_float(prev.get(value_col))
        if prev_value:
            variation = (value - prev_value) / prev_value * 100

    values_20 = []
    if value_col:
        for r in rows[-20:]:
            values_20.append(_to_float(r.get(value_col)))
    ma20 = mean(values_20) if len([v for v in values_20 if v is not None]) >= 10 else None

    signal = "🟡 Neutre"
    if value is not None and ma20 is not None:
        signal = "🟢 Risk-On" if value > ma20 else "🔴 Risk-Off"

    return {"date": date, "signal": signal, "value": value, "variation": variation}

# ---------- LIVE MARKET: quotes ----------
def fetch_market_html():
    r = requests.get(
        URL_MARCHE_ACTIONS,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=25,
        verify=certifi.where(),
    )
    r.raise_for_status()
    return r.text

def parse_quote_from_row_text(row_text: str):
    nums = re.findall(r"[-+]?\d[\d\s]*,\d+|[-+]?\d+(?:\.\d+)?", row_text)
    vals = []
    for n in nums:
        v = _to_float(n)
        if v is not None:
            vals.append(v)

    last = None
    pct = None

    for v in vals:
        if v > 0:
            last = v
            break

    for v in vals:
        if -50 <= v <= 50 and (last is None or v != last):
            pct = v
            break

    return last, pct

def get_quotes_for_codes(codes):
    html = fetch_market_html()
    soup = BeautifulSoup(html, "html.parser")

    target = {c.upper() for c in codes}
    found = {}

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue

        up_cells = [c.upper() for c in cells]
        match = None
        for code in target:
            if code in up_cells:
                match = code
                break
        if not match:
            continue

        row_text = " ".join(cells)
        last, pct = parse_quote_from_row_text(row_text)
        found[match] = {"last": last, "pct": pct}

    return found

# ---------- Reco / Potentiel / Format ----------
def compute_potentiel(last, sortie):
    if last is None or sortie is None or last <= 0:
        return None
    return (sortie - last) / last * 100

def compute_icon_and_label(last, achat, sortie):
    if last is None:
        return "⚪", "NA"
    if last <= achat:
        return "🟢", "Achat"
    if sortie is not None and last >= sortie:
        return "🔴", "Vente"
    return "🟡", "Attente"

def build_lines(quotes_by_code):
    items = []
    for name, cfg in WATCHLIST.items():
        # pick first available code
        last = None
        pct = None
        for code in cfg["bvc_codes"]:
            q = quotes_by_code.get(code.upper())
            if q and q.get("last") is not None:
                last = q.get("last")
                pct = q.get("pct")
                break

        pot = compute_potentiel(last, cfg["sortie"])
        icon, label = compute_icon_and_label(last, cfg["achat"], cfg["sortie"])

        items.append({
            "name": name,
            "type": cfg["type"],
            "achat": cfg["achat"],
            "sortie": cfg["sortie"],
            "last": last,
            "pct": pct,
            "pot": pot,
            "icon": icon,
            "label": label,
        })

    # sort by potential desc (None at end)
    def sk(x):
        return (1, 0) if x["pot"] is None else (0, -x["pot"])
    items.sort(key=sk)

    lines = []
    for it in items:
        if it["last"] is None:
            lines.append(
                f"⚪ {it['name']}_NA : n/a (n/a) [{fmt_price(it['achat'])} - {fmt_price(it['sortie'])}] • {it['type']} / pot n/a"
            )
            continue

        lines.append(
            f"{it['icon']} {it['name']}_{it['label']} : {fmt_price(it['last'])} {fmt_pct(it['pct'])} "
            f"[{fmt_price(it['achat'])} - {fmt_price(it['sortie'])}] • {it['type']} / pot {it['pot']:+.1f}%"
        )
    return lines

def main():
    prefix = "[TEST] " if BRANCH != "main" else ""

    masi = read_masi_signal()

    all_codes = []
    for cfg in WATCHLIST.values():
        all_codes.extend(cfg["bvc_codes"])

    # fetch quotes (si SSL échoue encore, on enverra quand même MASI + alerte)
    quotes = {}
    quotes_error = None
    try:
        quotes = get_quotes_for_codes(all_codes)
    except Exception as e:
        quotes_error = str(e)
        print("Quotes error:", quotes_error)

    msg_lines = []
    msg_lines.append(prefix + "📈 Bourse Casa (Auto)")

    if masi and masi.get("signal"):
        msg_lines.append(f"Signal: {masi['signal']}")
    else:
        msg_lines.append("Signal: 🟡 Neutre")

    msg_lines.append("")
    msg_lines.append("🧾 WATCHLIST (triée par potentiel)")

    if quotes:
        msg_lines.extend(build_lines(quotes))
    else:
        msg_lines.append("⚠️ Quotes actions indisponibles (site/SSL).")
        if quotes_error:
            msg_lines.append(f"Détail: {quotes_error[:120]}...")

    envoyer_telegram("\n".join(msg_lines))

if __name__ == "__main__":
    main()
