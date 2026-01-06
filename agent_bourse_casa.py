import re
import os
import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"

# mapping tickers BVC -> labels dans ton système
WATCH_TICKERS = {
    "SNP": "SNEP",
    "IAM": "IAM",
    "HPS": "HPS",
    "TGC": "TGCC",
}

OUT_CSV = "watchlist_prices.csv"


def fr_to_float(s: str):
    """
    Convertit "744,90" ou "1 234,50" -> 1234.50
    Retourne None si impossible.
    """
    if s is None:
        return None
    s = str(s).strip().replace("\xa0", " ")
    if s == "":
        return None
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_numbers(text: str):
    """
    Extrait une liste de nombres (style FR) d'un texte de ligne.
    """
    if not text:
        return []
    nums = re.findall(r"[-+]?\d[\d\s]*,\d+|[-+]?\d+(?:\.\d+)?", text)
    return nums


def guess_last_and_pct(row_text: str):
    """
    Heuristique:
    - last = premier nombre > 0
    - pct = premier nombre dans [-50, 50] différent de last
    """
    nums = extract_numbers(row_text)
    vals = [fr_to_float(n) for n in nums]
    vals = [v for v in vals if v is not None]

    last = next((v for v in vals if v > 0), None)
    pct = next((v for v in vals if -50 <= v <= 50 and (last is None or v != last)), None)
    return last, pct


def scrape_watchlist():
    rows_out = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR")

        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # Attendre qu'une table existe (sélecteur générique)
        page.wait_for_timeout(2000)

        # Récupérer toutes les lignes visibles de table
        # On prend tous les <tr> et on récupère le texte.
        trs = page.locator("tr")
        count = trs.count()

        for i in range(count):
            t = trs.nth(i).inner_text().strip()
            if not t:
                continue

            # Cherche un ticker exact en début de ligne ou dans les tokens
            tokens = [x.strip().upper() for x in re.split(r"\s+", t) if x.strip()]
            if not tokens:
                continue

            # La première cellule est souvent le code; sinon on cherche dans la ligne
            code = None
            if tokens[0] in WATCH_TICKERS:
                code = tokens[0]
            else:
                for tk in tokens[:6]:
                    if tk in WATCH_TICKERS:
                        code = tk
                        break

            if not code:
                continue

            last, pct = guess_last_and_pct(t)
            rows_out.append({
                "symbol": WATCH_TICKERS[code],  # label (SNEP/IAM/HPS/TGCC)
                "last": last,
                "pct": pct
            })

        browser.close()

    df = pd.DataFrame(rows_out).drop_duplicates(subset=["symbol"], keep="last")

    # Assure que toutes les valeurs attendues existent (même si manquantes)
    for lbl in WATCH_TICKERS.values():
        if lbl not in set(df["symbol"].tolist()):
            df = pd.concat([df, pd.DataFrame([{"symbol": lbl, "last": None, "pct": None}])], ignore_index=True)

    df = df.sort_values("symbol")
    df.to_csv(OUT_CSV, index=False)
    print(f"OK: wrote {OUT_CSV}")
    print(df)


if __name__ == "__main__":
    scrape_watchlist()
