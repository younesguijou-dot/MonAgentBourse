import re
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = "https://www.casablanca-bourse.com/fr/live-market/marche-actions-groupement"

# Codes BVC (table) -> labels de ton bot
MAP = {
    "SNP": "SNEP",
    "IAM": "IAM",
    "HPS": "HPS",
    "TGC": "TGCC",
}

OUT = "watchlist_prices.csv"


def fr_to_float(s: str):
    """Convertit '1 234,50' -> 1234.5 ; '2,3%' -> 2.3 ; sinon None"""
    if s is None:
        return None
    s = str(s).strip().replace("\xa0", " ")
    if s in ("", "—", "-", "NA", "N/A"):
        return None
    s = s.replace("%", "")
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def guess_last_and_pct(row_text: str):
    """Heuristique: last = 1er nombre >0 ; pct = 1er nombre [-50,50] != last"""
    nums = re.findall(r"[-+]?\d[\d\s]*,\d+|[-+]?\d+(?:\.\d+)?", row_text or "")
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

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

            # FIX: passer l'argument via keyword 'arg='
            page.wait_for_function(
                """(codes) => document.body && codes.some(c => document.body.innerText.includes(c))""",
                arg=list(MAP.keys()),
                timeout=60_000,
            )

            trs = page.locator("tr")
            n = trs.count()

            for i in range(n):
                t = trs.nth(i).inner_text().strip()
                if not t:
                    continue

                tokens = [x.strip().upper() for x in re.split(r"\s+", t) if x.strip()]
                code = None

                if tokens and tokens[0] in MAP:
                    code = tokens[0]
                else:
                    for tk in tokens[:6]:
                        if tk in MAP:
                            code = tk
                            break

                if not code:
                    continue

                last, pct = guess_last_and_pct(t)
                rows_out.append({"symbol": MAP[code], "last": last, "pct": pct})

        except PlaywrightTimeout:
            page.screenshot(path="debug_timeout.png", full_page=True)
            raise RuntimeError("Timeout loading page. See debug_timeout.png")
        finally:
            browser.close()

    df = pd.DataFrame(rows_out).drop_duplicates(subset=["symbol"], keep="first")

    # garantir toutes les lignes même si manquantes
    for lbl in MAP.values():
        if lbl not in set(df["symbol"].tolist()):
            df = pd.concat([df, pd.DataFrame([{"symbol": lbl, "last": None, "pct": None}])], ignore_index=True)

    df = df.sort_values("symbol")
    df.to_csv(OUT, index=False)
    print(df)
    print(f"OK: wrote {OUT}")


if __name__ == "__main__":
    scrape_watchlist()
