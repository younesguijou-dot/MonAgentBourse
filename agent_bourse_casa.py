import os
import csv
import re
import requests
from bs4 import BeautifulSoup

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BRANCH = os.getenv("GITHUB_REF_NAME", "unknown")

# Watchlist + seuils
# bvc_codes: codes tels qu'affichés dans la table "marché actions" du site casablanca-bourse.com
WATCHLIST = {
    "SNEP": {"type": "Pivot", "achat": 495.0, "sortie": 610.0, "bvc_codes": ["SNP"]},
    "HPS":  {"type": "Pivot", "achat": 556.0, "sortie": 675.0, "bvc_codes": ["HPS"]},
    "IAM":  {"type": "Dividende", "achat": 109.0, "sortie": 130.0, "bvc_codes": ["IAM"]},
    # Si TGCC n'apparaît pas sous "TGCC" sur la table, tu ajusteras bvc_codes après un premier run.
    "TGCC": {"type": "Growth", "achat": 900.0, "sortie": 980.0, "bvc_codes": ["TGCC"]},
}

URL_MARCHE_ACTIONS = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"


# -------------------- Telegram --------------------
def envoyer_telegram(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant.")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=20)
    print("Telegram:", r.status_code, r.text)


# -------------------- Helpers --------------------
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

def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

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

def fmt_price(x):
    if x is None:
        return "n/a"
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s

def fmt_pct(p):
    if p is None:
        return "(n/a)"
    sign = "+" if p >= 0 else ""
    return f"({sign}{p:.1f}%)"


# -------------------- MASI (depuis masi.csv) --------------------
def read_masi_summary():
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

    return {"date": date, "value": value, "variation": variation, "ma20": ma20, "signal": signal}


# -------------------- Quotes actions (depuis table Live Market) --------------------
def fetch_market_table_html():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL_MARCHE_ACTIONS, headers=headers, timeout=25)
    r.raise_for_status()
    return r.text

def parse_quote_from_row_text(row_text: str):
    """
    Heuristique:
    - last: premier nombre positif "type prix"
    - pct: premier nombre dans [-50, +50] différent de last
    """
    # Attrape des nombres style "1 234,50" ou "12,3" ou "12.3"
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
    """
    Retourne dict code -> {"last": float|None, "pct": float|None}
    """
    html = fetch_market_table_html()
    soup = BeautifulSoup(html, "html.parser")

    target = {c.upper() for c in codes}
    found = {}

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue

        # Est-ce que la ligne contient un des codes?
        up_cells = [c.upper() for c in cells]
        match = None
        for code in target:
            if code in up_cells or any(code == c for c in up_cells):
                match = code
                break
        if not match:
            continue

        row_text = " ".join(cells)
        last, pct = parse_quote_from_row_text(row_text)
        found[match] = {"last": last, "pct": pct}

    return found


# -------------------- Reco + Potentiel + Message --------------------
def compute_potentiel(last, sortie):
    if last is None or sortie is None or last <= 0:
        return None
    return (sortie - last) / last * 100

def compute_reco(last, achat, sortie):
    if last is None:
        return ("⚪", "Donnée manquante")
    if last <= achat:
        return ("🟢", "Achat")
    if sortie is not None and last >= sortie:
        return ("🔴", "Vente")
    return ("🟡", "Attente")

def build_watchlist_lines(quotes_by_code):
    items = []
    for label, cfg in WATCHLIST.items():
        # on prend le 1er code qui a une quote
        last = None
        pct = None
        used_code = None
        for code in cfg.get("bvc_codes", []):
            q = quotes_by_code.get(code.upper())
            if q and q.get("last") is not None:
                last = q.get("last")
                pct = q.get("pct")
                used_code = code.upper()
                break

        achat = cfg["achat"]
        sortie = cfg.get("sortie")
        typ = cfg.get("type", "")

        pot = compute_potentiel(last, sortie)
        icon, reco = compute_reco(last, achat, sortie)

        items.append({
            "label": label,
            "type": typ,
            "code": used_code,
            "last": last,
            "pct": pct,
            "achat": achat,
            "sortie": sortie,
            "pot": pot,
            "icon": icon,
            "reco": reco,
        })

    # Tri par potentiel décroissant, None à la fin
    def sort_key(it):
        return (1, 0) if it["pot"] is None else (0, -it["pot"])
    items.sort(key=sort_key)

    lines = []
    lines.append("🧾 WATCHLIST (triée par potentiel)")
    for it in items:
        sym_type = f"{it['label']}_{it['type']}".strip("_")
        last_s = fmt_price(it["last"])
        pct_s = fmt_pct(it["pct"])
        achat_s = fmt_price(it["achat"])
        sortie_s = "n/a" if it["sortie"] is None else fmt_price(it["sortie"])

        # “achat en vert – vente en rouge”
        bracket = f"[🟢{achat_s} - 🔴{sortie_s}]"

        pot_txt = ""
        if it["pot"] is not None:
            pot_txt = f" ({it['pot']:+.1f}% pot.)"

        # Exemple demandé:
        # - SNEP_Pivot : 492 (+3%) [495 - 610] • Achat (xx)
        lines.append(
            f"- {sym_type} : {last_s} {pct_s} {bracket} • {it['icon']} {it['reco']}{pot_txt}"
        )

    return "\n".join(lines)

def main():
    prefix = "[TEST] " if BRANCH != "main" else ""

    masi = read_masi_summary()

    # construire la liste de codes à récupérer
    all_codes = []
    for cfg in WATCHLIST.values():
        all_codes.extend(cfg.get("bvc_codes", []))

    quotes = {}
    try:
        quotes = get_quotes_for_codes(all_codes)
    except Exception as e:
        print("Erreur récupération quotes:", e)

    lines = []
    lines.append(prefix + "📊 Bourse Casa (Auto)")

    if masi:
        if masi["date"]:
            lines.append(f"Date: {masi['date']}")
        if masi["value"] is not None:
            lines.append(f"MASI: {masi['value']:,.2f}".replace(",", " "))
        if masi["variation"] is not None:
            lines.append(f"MASI Var J: {masi['variation']:+.2f}%")
        if masi["ma20"] is not None and masi["value"] is not None:
            lines.append(f"MA20: {masi['ma20']:,.2f}".replace(",", " "))
        lines.append(f"Signal: {masi['signal']}")
    else:
        lines.append("⚠️ MASI: non disponible (masi.csv manquant ou vide)")

    lines.append("")
    lines.append(build_watchlist_lines(quotes))

    # Si une ligne est ⚪, c’est souvent un code bvc_codes incorrect → on l’indique
    lines.append("")
    lines.append("ℹ️ Si une valeur affiche ⚪, ajuste son bvc_codes (code table Live Market).")

    envoyer_telegram("\n".join(lines))

if __name__ == "__main__":
    main()
