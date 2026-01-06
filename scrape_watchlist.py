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


def pick_main_table(tables):
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        if "instrument" in cols and "dernier cours" in cols and "variation en %" in cols:
            return df
    # fallback: instrument + dernier cours
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        if "instrument" in cols and "dernier cours" in cols:
            return df
    return None


def scrape_html():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(
                "() => document.body && document.body.innerText.includes('Instrument')",
                timeout=60_000,
            )
            return page.content()
        except PlaywrightTimeout:
            page.screenshot(path="debug_timeout.png", full_page=True)
            raise RuntimeError("Timeout: voir debug_timeout.png")
        finally:
            browser.close()


def filter_watchlist(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df["Instrument_str"] = df["Instrument"].astype(str).str.upper()

    def map_symbol(instr):
        for k, sym in WATCH_KEYWORDS.items():
            if k in instr:
                return sym
        return None

    df["symbol"] = df["Instrument_str"].map(map_symbol)
    df = df[df["symbol"].notna()].copy()
    return df


def main():
    html = scrape_html()

    tables = pd.read_html(html, decimal=",", thousands=" ")
    main_df = pick_main_table(tables)
    if main_df is None:
        raise RuntimeError("Table principale non trouvée (Instrument / Dernier cours).")

    watch_df = filter_watchlist(main_df)

    # Export complet (colonnes site)
    watch_df.drop(columns=["Instrument_str"], errors="ignore").to_csv(OUT_FULL, index=False)

    # Export mini: symbol, last, pct (pct = Variation en % telle quelle)
    mini = pd.DataFrame()
    mini["symbol"] = watch_df["symbol"]
    mini["last"] = watch_df["Dernier cours"]
    if "Variation en %" in watch_df.columns:
        mini["pct"] = watch_df["Variation en %"]
    else:
        mini["pct"] = None

    mini = mini.drop_duplicates(subset=["symbol"], keep="first").sort_values("symbol")
    mini.to_csv(OUT_MINI, index=False)

    print("OK:", OUT_FULL, OUT_MINI)
    print(mini)


if __name__ == "__main__":
    main()
