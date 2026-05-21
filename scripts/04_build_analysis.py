"""
04_build_analysis.py
====================
Merges ACLED conflict data with OPRI education indicators and computes
a composite vulnerability score per admin1 region per year.

The vulnerability score combines:
  1. Conflict intensity  — normalised event count per admin1 per year
  2. Conflict severity   — normalised fatality count per admin1 per year
  3. Survival rate gap   — inverse of primary survival rate (lower = more vulnerable)
  4. OOS rate            — out-of-school rate (higher = more vulnerable)

Each indicator is min-max normalised to [0,1].
Score = mean of available indicators (skipna — honest about missing data).
Admin1s are flagged with how many indicators contributed to their score.

Generic — change ISO3 at the top to run on any country.

Output:
  data/clean/{ISO3}_vulnerability.csv    — per admin1 per year scores
  data/clean/{ISO3}_national_trends.csv  — national-level year-on-year trends
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ISO3       = "BFA"
START_YEAR = 2015
END_YEAR   = 2024

# Proximity threshold for "schools near conflict" (km)
# Used for flagging in the output — not a filter
PROXIMITY_KM = 10

IN_ACLED = Path(f"data/raw/acled/acled_{ISO3}.csv")
IN_OPRI  = Path(f"data/raw/opri/opri_{ISO3}.csv")
OUT_DIR  = Path("data/clean")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def minmax(series: pd.Series) -> pd.Series:
    """Min-max normalise a series to [0, 1]. Returns NaN for constant series."""
    rng = series.max() - series.min()
    if rng == 0:
        return pd.Series(np.nan, index=series.index)
    return (series - series.min()) / rng


def load_acled(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["year"]       = pd.to_numeric(df["year"],       errors="coerce")
    df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0)
    df["latitude"]   = pd.to_numeric(df["latitude"],   errors="coerce")
    df["longitude"]  = pd.to_numeric(df["longitude"],  errors="coerce")
    # Standardise admin1 column name
    df = df.rename(columns={"admin1": "region"})
    df["region"] = df["region"].str.strip().str.title()
    return df[df["year"].between(START_YEAR, END_YEAR)]


def load_opri(path: Path) -> dict[str, pd.DataFrame]:
    """Load OPRI data and pivot to one DataFrame per indicator."""
    df = pd.read_csv(path, low_memory=False)
    df["YEAR"]  = pd.to_numeric(df["YEAR"],  errors="coerce")
    df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    df = df[df["YEAR"].between(START_YEAR, END_YEAR)]
    return {ind: grp[["YEAR", "VALUE"]].rename(columns={"VALUE": ind})
            for ind, grp in df.groupby("INDICATOR_ID")}


# ── Step 1: ACLED — compute per admin1 per year conflict metrics ───────────────

def build_conflict_metrics(acled: pd.DataFrame) -> pd.DataFrame:
    grp = acled.groupby(["region", "year"]).agg(
        events     = ("event_id_cnty", "count"),
        fatalities = ("fatalities",    "sum"),
    ).reset_index()

    # Normalise within each year so regions are comparable year-on-year
    for year, g in grp.groupby("year"):
        grp.loc[g.index, "events_norm"]     = minmax(g["events"])
        grp.loc[g.index, "fatalities_norm"] = minmax(g["fatalities"])

    return grp


# ── Step 2: OPRI — national survival rate and OOS rate ────────────────────────

def build_education_metrics(opri_dict: dict) -> pd.DataFrame:
    """
    Returns a year-indexed DataFrame of key education indicators.
    National-level only (OPRI doesn't have admin1 disaggregation).
    We join these onto the admin1 table so every region in a given year
    shares the same national education score — a known limitation,
    flagged in docs/methodology.md.
    """
    frames = []

    # Survival rate to last grade of primary (both sexes)
    if "SURVCOMP.PT4" in opri_dict:
        df = opri_dict["SURVCOMP.PT4"].copy()
        df["survival_norm"] = 1 - minmax(df["SURVCOMP.PT4"])  # inverse: lower survival = higher vulnerability
        frames.append(df[["YEAR", "survival_norm"]])

    # Out-of-school rate, primary
    if "ROFST.1.cp" in opri_dict:
        df = opri_dict["ROFST.1.cp"].copy()
        df["oos_norm"] = minmax(df["ROFST.1.cp"])
        frames.append(df[["YEAR", "oos_norm"]])

    if not frames:
        return pd.DataFrame(columns=["YEAR"])

    result = frames[0]
    for f in frames[1:]:
        result = result.merge(f, on="YEAR", how="outer")
    return result.rename(columns={"YEAR": "year"})


# ── Step 3: Merge and compute composite score ──────────────────────────────────

def compute_vulnerability(conflict: pd.DataFrame, edu: pd.DataFrame) -> pd.DataFrame:
    df = conflict.merge(edu, on="year", how="left")

    score_cols = ["events_norm", "fatalities_norm", "survival_norm", "oos_norm"]
    available  = [c for c in score_cols if c in df.columns]

    df["score"]        = df[available].mean(axis=1, skipna=True)
    df["score_basis"]  = df[available].notna().sum(axis=1).astype(str) + f"/{len(available)}_indicators"
    df["score_tercile"] = pd.qcut(
        df["score"].rank(method="first"),
        q=3,
        labels=["lower_priority", "medium_priority", "high_priority"]
    )

    return df.sort_values(["year", "score"], ascending=[True, False])


# ── Step 4: National trends (for the time-series chart) ───────────────────────

def build_national_trends(acled: pd.DataFrame, opri_dict: dict) -> pd.DataFrame:
    national_conflict = acled.groupby("year").agg(
        total_events     = ("event_id_cnty", "count"),
        total_fatalities = ("fatalities",    "sum"),
    ).reset_index()

    edu_frames = {}
    for ind in ["SURVCOMP.PT4", "SURVCOMP.PT4.F", "SURVCOMP.PT4.M",
                "ROFST.1.cp", "GER.1", "NERT.1"]:
        if ind in opri_dict:
            edu_frames[ind] = opri_dict[ind].rename(columns={ind: ind, "YEAR": "year"})

    result = national_conflict
    for ind, df in edu_frames.items():
        result = result.merge(df, on="year", how="left")

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Building analysis for {ISO3}...")

    # Load
    acled = load_acled(IN_ACLED)
    print(f"  ACLED: {len(acled):,} events, {acled['region'].nunique()} admin1 regions")

    opri_dict = load_opri(IN_OPRI)
    print(f"  OPRI:  {list(opri_dict.keys())}")

    # Build components
    conflict = build_conflict_metrics(acled)
    edu      = build_education_metrics(opri_dict)
    vuln     = compute_vulnerability(conflict, edu)
    trends   = build_national_trends(acled, opri_dict)

    # Save
    vuln_path   = OUT_DIR / f"{ISO3}_vulnerability.csv"
    trends_path = OUT_DIR / f"{ISO3}_national_trends.csv"

    vuln.to_csv(vuln_path, index=False)
    trends.to_csv(trends_path, index=False)

    print(f"\n✓ Vulnerability scores → {vuln_path}")
    print(f"✓ National trends      → {trends_path}")
    print(f"\nScore summary ({ISO3}):")
    print(vuln.groupby("score_tercile")["region"].nunique().rename("admin1_regions").to_string())
