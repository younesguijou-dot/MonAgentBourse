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

def read_masi_rows(path="masi.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows

def pick_col(rows, candidates):
    """Retourne le premier nom de colonne présent dans le CSV."""
    if not rows:
        return None
    cols = set(rows[0].keys())
    for c in candidates:
        if c in cols:
            return c
    # fallback: match insensible à la casse
    lower_map = {k.lower(): k for k in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None

def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

if __name__ == "__main__":
    rows = read_masi_rows("masi.csv")
    if not rows:
        envoyer_telegram("⚠️ MASI: masi.csv vide ou non généré.")
        raise SystemExit(1)

    # Colonnes probables (sans supposer)
    date_col = pick_col(rows, ["Date", "date", "DATE"])
    value_col = pick_col(rows, ["MASI", "Close", "close", "Value", "value", "Index", "index"])
    var_col = pick_col(rows, ["Variation", "variation", "Var", "var", "Change", "change", "Pct", "pct", "Percent", "percent"])

    last = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None

    date = last.get(date_col) if date_col else None
    value = _to_float(last.get(value_col)) if value_col else None

    # Variation: si elle existe en colonne, on l'utilise, sinon on la calcule.
    variation = _to_float(last.get(var_col)) if var_col else None
    if variation is None and value is not None and prev and value_col:
        prev_value = _to_float(prev.get(value_col))
        if prev_value:
            variation = (value - prev_value) / prev_value * 100

    # Tendance 20j (si possible)
    values = []
    if value_col:
        for r in rows[-20:]:
            values.append(_to_float(r.get(value_col)))
    ma20 = mean(values) if len([v for v in values if v is not None]) >= 10 else None

    # Signal simple
    signal = "🟡 Neutre"
    if value is not None and ma20 is not None:
        if value > ma20:
            signal = "🟢 Risk-On (au-dessus MA20)"
        elif value < ma20:
            signal = "🔴 Risk-Off (sous MA20)"

    # Message propre
    lines = []
    lines.append("📈 Rapport MASI (Auto)")
    if date:
        lines.append(f"Date: {date}")
    if value is not None:
        lines.append(f"MASI: {value:,.2f}".replace(",", " "))
    if variation is not None:
        lines.append(f"Variation J: {variation:+.2f}%")
    if ma20 is not None and value is not None:
        lines.append(f"MA20: {ma20:,.2f}".replace(",", " "))
    lines.append(f"Signal: {signal}")

    envoyer_telegram("\n".join(lines))
