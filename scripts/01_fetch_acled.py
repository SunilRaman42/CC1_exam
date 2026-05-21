"""
01_fetch_acled.py
=================
Fetches ACLED conflict events for one or more countries via OAuth.
Generic — change TARGET_COUNTRIES to run on any set of ISO3 codes.

Output: data/raw/acled/acled_{ISO3}.csv per country
"""

import os, time, json, requests, pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
ACLED_EMAIL    = os.environ.get("ACLED_EMAIL")
ACLED_PASSWORD = os.environ.get("ACLED_PASSWORD")

TARGET_COUNTRIES = ["BFA"]   # ISO3 list — add more: ["BFA", "MLI", "NER"]
START_DATE       = "2015-01-01"
END_DATE         = "2024-12-31"

# Armed conflict types only — remove entries to broaden
EVENT_TYPES = [
    "Battles",
    "Explosions/Remote violence",
    "Violence against civilians",
]

OUT_DIR = Path("data/raw/acled")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_URL = "https://acleddata.com/oauth/token"
API_URL   = "https://acleddata.com/api/acled/read"


def get_token() -> str:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "password",
        "username":   ACLED_EMAIL,
        "password":   ACLED_PASSWORD,
        "client_id":  "acled",
    }
    r = requests.post(TOKEN_URL, headers=headers, data=data)
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"Error: {e}")
        print(f"Response: {r.text}")
        raise
    print("✓ ACLED token obtained")
    return r.json()["access_token"]


def fetch_country(token: str, iso3: str) -> pd.DataFrame:
    headers  = {"Authorization": f"Bearer {token}"}
    all_rows = []
    page     = 1

    while True:
        params = {
            "_format":          "json",
            "iso":              iso3,
            "event_date":       f"{START_DATE}|{END_DATE}",
            "event_date_where": "BETWEEN",
            "event_type":       "|".join(EVENT_TYPES),
            "fields": "event_id_cnty|event_date|year|event_type|sub_event_type|"
                      "admin1|admin2|location|latitude|longitude|"
                      "actor1|actor2|fatalities|notes",
            "limit":  5000,
            "page":   page,
        }
        r = requests.get(API_URL, headers=headers, params=params)
        r.raise_for_status()
        batch = r.json().get("data", [])
        if not batch:
            break
        all_rows.extend(batch)
        print(f"  Page {page}: +{len(batch)} events (total: {len(all_rows)})")
        if len(batch) < 5000:
            break
        page += 1
        time.sleep(1.0)

    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    token = get_token()
    for iso3 in TARGET_COUNTRIES:
        print(f"\nFetching ACLED: {iso3}")
        df = fetch_country(token, iso3)
        out = OUT_DIR / f"acled_{iso3}.csv"
        df.to_csv(out, index=False)
        print(f"  ✓ {len(df):,} events → {out}")
