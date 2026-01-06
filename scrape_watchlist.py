import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"

WATCH_KEYWORDS = {
    "SNEP": "SNEP",
    "ITISSALAT": "IAM",
    "AL-MAGHRIB": "IAM",
    "TGCC": "TGCC",
    "HPS": "HPS",
}

OUT_FULL = "watchlist_full.csv"
OUT_MINI = "watchlist_prices.csv"


def map_symbol(instrument_text: str):
    up = (instrument_text or "").upper()
    for k, sym in WATCH_KEYWORDS.items():
        if k in up:
            return sym
    return None


def clean_cell_text(s: str):
    if s is None:
        return ""
    return str(s).replace("\xa0", " ").strip()


def scrape_tables_dom():
    """
    Retourne une liste de DataFrames extraits des tables pertinentes,
    en lisant directement le DOM (sans pandas.read_html).
    """
    dfs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR")

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(
                "() => document.body && document.body.innerText.includes('Instrument')",
                timeout=60_000,
            )

            tables = page.locator("table")
            n_tables = tables.count()

            for ti in range(n_tables):
                table = tables.nth(ti)

                # headers
                ths = table.locator("thead tr th")
                if ths.count() == 0:
                    ths = table.locator("tr th")  # fallback

                headers = []
                for i in range(ths.count()):
                    headers.append(clean_cell_text(ths.nth(i).inner_text()))

                headers_norm = [h.lower() for h in headers]
                if "instrument" not in headers_norm or "dernier cours" not in headers_norm:
                    continue  # pas la bonne table

                # rows
                rows = table.locator("tbody tr")
                data_rows = []
                for ri in range(rows.count()):
                    tds = rows.nth(ri).locator("td")
                    if tds.count() == 0:
                        continue
                    row = [clean_cell_text(tds.nth(ci).inner_text()) for ci in range(tds.count())]

                    # ajuster longueur si mismatch
                    if len(row) < len(headers):
                        row += [""] * (len(headers) - len(row))
                    if len(row) > len(headers):
                        row = row[: len(headers)]

                    data_rows.append(row)

                if data_rows:
                    df = pd.DataFrame(data_rows, columns=headers)
                    dfs.append(df)

        except PlaywrightTimeout:
            page.screenshot(path="debug_timeout.png", full_page=True)
            raise RuntimeError("Timeout page (voir debug_timeout.png)")
        finally:
            browser.close()

    return dfs


def main():
    dfs = scrape_tables_dom()
    if not dfs:
        raise RuntimeError("Aucune table (Instrument + Dernier cours) détectée. Site changé ou blocage.")

    # concat toutes les tables pertinentes
    full = pd.concat(dfs, ignore_index=True)

    # colonnes attendues (du site)
    if "Instrument" not in full.columns or "Dernier cours" not in full.columns:
        raise RuntimeError(f"Colonnes manquantes. Colonnes disponibles: {list(full.columns)}")

    # ajouter symbol + filtrer watchlist
    full["symbol"] = full["Instrument"].apply(map_symbol)
    watch_full = full[full["symbol"].notna()].copy()

    # Export full (toutes colonnes du site + symbol)
    watch_full.to_csv(OUT_FULL, index=False)

    # Export mini garanti
    mini = pd.DataFrame()
    mini["symbol"] = watch_full["symbol"]
    mini["last"] = watch_full["Dernier cours"]

    # Variation en % si dispo
    if "Variation en %" in watch_full.columns:
        mini["pct"] = watch_full["Variation en %"]
    else:
        mini["pct"] = ""

    mini = mini.drop_duplicates(subset=["symbol"], keep="first").sort_values("symbol")
    mini.to_csv(OUT_MINI, index=False)

    print("OK:", OUT_FULL, OUT_MINI)
    print(mini)


if __name__ == "__main__":
    main()
