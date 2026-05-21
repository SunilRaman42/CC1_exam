"""
02_fetch_opri.py
================
Streams the UNESCO UIS OPRI bulk CSV and filters to target countries
and education indicators. No API key required.

Output: data/raw/opri/opri_{ISO3}.csv per country
"""

import io, os, zipfile, requests, pandas as pd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_COUNTRIES = ["BFA"]   # ISO3 list
START_YEAR       = 2000
END_YEAR         = 2023

# Key education indicators from OPRI
INDICATORS = [
    "NERT.1",        # Net enrolment rate, primary
    "NERT.2",        # Net enrolment rate, secondary
    "ROFST.1.cp",    # Out-of-school rate, primary
    "ROFST.2",       # Out-of-school rate, lower secondary
    "SURVCOMP.PT4",  # Survival rate to last grade, primary
    "SURVCOMP.PT4.F",# Survival rate, female
    "SURVCOMP.PT4.M",# Survival rate, male
    "GER.1",         # Gross enrolment ratio, primary
    "GER.2",         # Gross enrolment ratio, secondary
]

OPRI_ZIP_URL = (
    "https://download.uis.unesco.org/bdds/202509/OPRI.zip"
)
TARGET_CSV = "OPRI_DATA_NATIONAL.csv"
CHUNK_SIZE = 50_000

OUT_DIR = Path("data/raw/opri")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "education-risk-research/1.0"}


def stream_and_filter() -> pd.DataFrame:
    print(f"Streaming OPRI bulk CSV...")
    r = requests.get(OPRI_ZIP_URL, stream=True, headers=HEADERS, timeout=300)
    r.raise_for_status()

    buf = io.BytesIO()
    done = 0
    for chunk in r.iter_content(1 << 20):
        buf.write(chunk)
        done += len(chunk)
        print(f"  {done/1e6:.0f} MB", end="\r")
    print(f"\n  Downloaded {done/1e6:.1f} MB")
    buf.seek(0)

    kept = []
    total = 0
    with zipfile.ZipFile(buf) as zf:
        with zf.open(TARGET_CSV) as f:
            for chunk in pd.read_csv(f, chunksize=CHUNK_SIZE, low_memory=False):
                total += len(chunk)
                mask = (
                    chunk["COUNTRY_ID"].isin(TARGET_COUNTRIES) &
                    chunk["INDICATOR_ID"].isin(INDICATORS) &
                    chunk["YEAR"].between(START_YEAR, END_YEAR)
                )
                filtered = chunk[mask]
                if not filtered.empty:
                    kept.append(filtered)
                print(f"  Read {total:>8,} rows | kept {sum(len(k) for k in kept):>6,}", end="\r")

    print()
    return pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()


if __name__ == "__main__":
    df = stream_and_filter()

    if df.empty:
        print("⚠ No data matched filters")
    else:
        for iso3 in TARGET_COUNTRIES:
            subset = df[df["COUNTRY_ID"] == iso3]
            out = OUT_DIR / f"opri_{iso3}.csv"
            subset.to_csv(out, index=False)
            print(f"✓ {iso3}: {len(subset):,} rows → {out}")
