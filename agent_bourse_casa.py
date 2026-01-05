import os
import csv
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BRANCH = os.getenv("GITHUB_REF_NAME", "unknown")

WATCHLIST = {
    "SNEP": {"achat": 495.0, "sortie": 610.0, "type": "Pivot"},
    "HPS": {"achat": 556.0, "sortie": 675.0, "type": "Pivot"},
    "IAM": {"achat": 109.0, "sortie": 130.0, "type": "Dividende"},
    "TGCC": {"achat": 900.0, "sortie": None, "type": "Growth"},
}

def envoyer_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=15)
    print("Telegram:", r.status_code, r.text)

def _to_float(x):
    if x is None:
        return None
    s = str(x).strip().replace(" ", "").replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None

def read_rows(path="masi.csv"):
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

def build_watchlist_intro():
    lines = []
    lines.append("🧾 WATCHLIST (seuils)")
    for sym, cfg in WATCHLIST.items():
        achat = cfg.get("achat")
        sortie = cfg.get("sortie")
        typ = cfg.get("type", "")
        if sortie is None:
            lines.append(f"- {sym} | achat ≤ {achat} | type: {typ}")
        else:
            lines.append(f"- {sym} | achat ≤ {achat} | sortie: {sortie} | type: {typ}")
    return "\n".join(lines)

if __name__ == "__main__":
    prefix = "[TEST] " if BRANCH != "main" else ""

    rows = read_rows("masi.csv")
    if not rows:
        envoyer_telegram(prefix + "⚠️ MASI: masi.csv vide ou non généré.")
        raise SystemExit(1)

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
        signal = "🟢 Risk-On (au-dessus MA20)" if value > ma20 else "🔴 Risk-Off (sous MA20)"

    lines = []
    lines.append(prefix + "📈 Rapport Bourse Casa (Auto)")
    if date:
        lines.append(f"Date: {date}")
    if value is not None:
        lines.append(f"MASI: {value:,.2f}".replace(",", " "))
    if variation is not None:
        lines.append(f"Variation J: {variation:+.2f}%")
    if ma20 is not None and value is not None:
        lines.append(f"MA20: {ma20:,.2f}".replace(",", " "))
    lines.append(f"Signal: {signal}")
    lines.append("")
    lines.append(build_watchlist_intro())

    envoyer_telegram("\n".join(lines))
