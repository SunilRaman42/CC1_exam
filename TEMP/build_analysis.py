"""
04_build_analysis.py
====================
Builds the Education Vulnerability Index (EVI) — a multi-dimensional
composite score per admin district combining:

  Sub-index A: Conflict Pressure (from ACLED)
    A1  Event frequency with exponential time-decay (recent = higher weight)
    A2  Fatality count (log-scaled to prevent outlier dominance)
    A3  Event type severity (civilian targeting > explosions > battles)
    A4  Trend direction (escalating conflict = higher score)

  Sub-index B: System Fragility (from education + displacement data)
    B1  School closure rate           (Admin2, province-level)
    B2  School density gap            (schools per 1000 school-age children)
    B3  Out-of-school rate            (Admin1, region-level — noted in score_basis)
    B4  Survival rate inverse         (Admin1, region-level — noted in score_basis)
    B5  IDP presence                  (Admin2, province-level)

Methodology follows INFORM Risk Index structure:
  EVI = (Sub-index A ^ (1/3)) × (Sub-index B ^ (1/3))
  (geometric mean — same as INFORM — penalises extreme imbalance
   between pressure and fragility)

  Alternative: simple mean — controlled by SCORE_METHOD below.

Districts classified into 4 tiers: low / medium / high / critical
  using fixed thresholds (not quantile-based) so thresholds are
  stable across years and comparable across countries.

Sensitivity test: re-runs with alternate weightings and saves
  comparison CSV so the index is defensible under scrutiny.

METHODOLOGICAL PRECEDENTS
  - INFORM Risk Index (EC Joint Research Centre): same 3-dimension
    composite structure, geometric mean, 0-10 scale
  - UNDP Human Development Index: normalise → weight → aggregate
  - UNESCO IIEP Education Sector Analysis: fragility × pressure framing

Output:
  data/clean/{ISO3}_evi_scores.csv          full index, all districts, all years
  data/clean/{ISO3}_evi_sensitivity.csv     sensitivity test results
  data/clean/{ISO3}_national_trends.csv     national time-series for chart
  data/clean/{ISO3}_indicator_details.csv   un-normalised inputs (transparency)
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ISO3       = os.environ.get("PIPELINE_ISO3", "BFA")
ADMIN_LEVEL = 2          # 1 = region, 2 = province (recommended for BFA)
START_YEAR  = 2016       # ACLED BFA coverage improves significantly from 2016
END_YEAR    = 2024

# Scoring method: "geometric" (INFORM-style) or "mean" (simpler, more transparent)
SCORE_METHOD = "geometric"

# Conflict pressure time-decay parameter
# λ = 0.3 → events 1yr ago weighted at ~74%, 2yrs ago ~55%, 3yrs ago ~40%
DECAY_LAMBDA = 0.3

# Event type severity weights (A3)
# Based on GCPEA classification of impact on education access
EVENT_WEIGHTS = {
    "Violence against civilians": 1.0,
    "Explosions/Remote violence": 0.8,
    "Battles":                    0.5,
    "Riots":                      0.3,
    "Protests":                   0.1,
    "Strategic developments":     0.2,
}

# Sub-index weights (must sum to 1.0)
WEIGHT_A = 0.5   # conflict pressure
WEIGHT_B = 0.5   # system fragility

# Within sub-index A, indicator weights (must sum to 1.0)
W_A1 = 0.35   # event frequency (decay-weighted)
W_A2 = 0.30   # fatality count
W_A3 = 0.20   # event type severity
W_A4 = 0.15   # trend direction

# Within sub-index B, indicator weights (must sum to 1.0)
W_B1 = 0.30   # school closure rate
W_B2 = 0.20   # school density gap
W_B3 = 0.20   # out-of-school rate
W_B4 = 0.15   # survival rate (inverse)
W_B5 = 0.15   # IDP presence

# Fixed classification thresholds (0–1 scale)
# Using fixed thresholds (not quantile) for cross-year and cross-country comparability
THRESHOLDS = {
    "low":      0.25,
    "medium":   0.50,
    "high":     0.75,
    # above 0.75 = critical
}

# File paths
IN_ACLED       = Path(f"data/raw/acled/acled_{ISO3}.csv")
IN_DHS         = Path(f"data/raw/education/dhs_subnational_{ISO3}.csv")
IN_WORLDBANK   = Path(f"data/raw/education/worldbank_national_{ISO3}.csv")
IN_SCHOOLS     = Path(f"data/raw/schools_hdx/bfa_schools.geojson")   # BFA-specific
IN_CLOSURES    = Path(f"data/raw/bfa/school_closures_bfa.csv")       # BFA-specific
IN_IDP         = Path(f"data/raw/bfa/idp_bfa.csv")                   # BFA-specific
OUT_DIR        = Path("data/clean")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_COL = f"admin{ADMIN_LEVEL}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.0, index=s.index)
    return (s - lo) / (hi - lo)


def weighted_mean(df: pd.DataFrame, cols: list, weights: list) -> pd.Series:
    """Weighted mean across columns, skipping NaN (honest about missing data)."""
    total_w = pd.Series(0.0, index=df.index)
    total_v = pd.Series(0.0, index=df.index)
    for col, w in zip(cols, weights):
        if col in df.columns:
            valid = df[col].notna()
            total_v += df[col].fillna(0) * w * valid
            total_w += w * valid
    return total_v.div(total_w.replace(0, np.nan))


def classify(score: pd.Series) -> pd.Series:
    bins   = [0, THRESHOLDS["low"], THRESHOLDS["medium"],
              THRESHOLDS["high"], 1.01]
    labels = ["low", "medium", "high", "critical"]
    return pd.cut(score, bins=bins, labels=labels, include_lowest=True)


# ── Sub-index A: Conflict Pressure ───────────────────────────────────────────

def build_conflict_pressure(acled: pd.DataFrame, ref_year: int) -> pd.DataFrame:
    """
    Compute four conflict pressure indicators per district per year.
    ref_year: the year to compute scores relative to (for decay weighting).
    """
    df = acled.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0)
    df = df[df["year"] <= ref_year].copy()

    # A3: assign severity weight per event
    df["severity_w"] = df["event_type"].map(EVENT_WEIGHTS).fillna(0.3)

    # Time-decay weight: w = exp(-λ * (ref_year - year))
    df["decay_w"] = np.exp(-DECAY_LAMBDA * (ref_year - df["year"]))

    grp = df.groupby(ADMIN_COL)

    # A1: decay-weighted event count
    A1 = (df.assign(wt=df["decay_w"])
            .groupby(ADMIN_COL)["wt"].sum()
            .rename("A1_event_freq_decay"))

    # A2: log-scaled fatalities (use all years, not decayed — cumulative impact)
    A2 = (df[df["year"] == ref_year]
            .groupby(ADMIN_COL)["fatalities"].sum()
            .apply(lambda x: np.log1p(x))
            .rename("A2_fatalities_log"))

    # A3: decay-weighted severity score
    df["sev_decay"] = df["severity_w"] * df["decay_w"]
    A3 = (df.groupby(ADMIN_COL)["sev_decay"].sum()
            .rename("A3_severity_weighted"))

    # A4: trend direction — OLS slope of annual event count over last 3 years
    recent = df[df["year"].between(ref_year - 2, ref_year)]
    slopes = {}
    for dist, g in recent.groupby(ADMIN_COL):
        yr_counts = g.groupby("year").size().reset_index(name="n")
        if len(yr_counts) >= 2:
            x = yr_counts["year"].values - yr_counts["year"].min()
            y = yr_counts["n"].values
            slope = np.polyfit(x, y, 1)[0]
            slopes[dist] = slope
        else:
            slopes[dist] = 0.0
    A4 = pd.Series(slopes, name="A4_trend_slope")

    # Combine
    sub_a = pd.concat([A1, A2, A3, A4], axis=1).fillna(0)

    # Normalise each indicator to [0,1]
    for col in sub_a.columns:
        sub_a[col + "_norm"] = minmax(sub_a[col])

    # Weighted composite
    norm_cols = [c + "_norm" for c in ["A1_event_freq_decay", "A2_fatalities_log",
                                        "A3_severity_weighted", "A4_trend_slope"]]
    weights   = [W_A1, W_A2, W_A3, W_A4]
    sub_a["conflict_pressure"] = weighted_mean(sub_a, norm_cols, weights)
    sub_a["year"] = ref_year

    return sub_a.reset_index()


# ── Sub-index B: System Fragility ─────────────────────────────────────────────

def build_system_fragility(
    closures_df:  pd.DataFrame | None,
    schools_gdf:  object | None,   # GeoDataFrame or None
    dhs_df:       pd.DataFrame | None,
    wb_df:        pd.DataFrame | None,
    idp_df:       pd.DataFrame | None,
    admin_regions: list,
    ref_year: int,
) -> pd.DataFrame:
    """
    Assemble system fragility sub-index from available data sources.
    Gracefully handles missing sources — score_basis reflects what's available.
    """
    result = pd.DataFrame({ADMIN_COL: admin_regions})
    score_basis = pd.Series("", index=result.index)

    # B1: School closure rate
    if closures_df is not None and not closures_df.empty:
        cl_col = next((c for c in closures_df.columns
                       if "clos" in c.lower() or "ferm" in c.lower()), None)
        dist_col = next((c for c in closures_df.columns
                         if "admin2" in c.lower() or "province" in c.lower()), None)
        if cl_col and dist_col:
            closure_map = closures_df.set_index(dist_col)[cl_col].to_dict()
            result["B1_closure_rate"] = result[ADMIN_COL].map(closure_map)
            result["B1_closure_norm"] = minmax(result["B1_closure_rate"].fillna(0))
            score_basis += "B1 "

    # B2: School density gap (schools per 1000 school-age children)
    # Lower density = higher fragility (each closure hits more children)
    if schools_gdf is not None:
        import geopandas as gpd
        if isinstance(schools_gdf, gpd.GeoDataFrame):
            # Count schools per admin2 using spatial join with boundaries
            # (simplified here — actual spatial join in 05_export_map_data.py)
            if ADMIN_COL in schools_gdf.columns:
                school_counts = schools_gdf.groupby(ADMIN_COL).size()
                result["B2_school_count"] = result[ADMIN_COL].map(school_counts).fillna(0)
                # Invert: fewer schools = higher fragility
                result["B2_density_gap_norm"] = 1 - minmax(result["B2_school_count"])
                score_basis += "B2 "

    # B3: Out-of-school rate (from World Bank national — applied to all districts)
    # Note: national figure, flagged in score_basis as lower resolution
    if wb_df is not None and not wb_df.empty:
        oos_col = "SE.PRM.UNER"
        oos_rows = wb_df[(wb_df.get("indicator_code", "") == oos_col) &
                         (wb_df.get("year", 0) == ref_year)]
        if not oos_rows.empty:
            oos_val = float(oos_rows["value"].values[0])
            result["B3_oos_rate"] = oos_val
            # National value — all districts get same figure
            result["B3_oos_norm"] = minmax(
                pd.Series([oos_val] * len(result), index=result.index)
            ).fillna(0)
            score_basis += "B3(national) "

    # B4: Survival rate inverse (from DHS subnational if available)
    if dhs_df is not None and not dhs_df.empty:
        surv_id = "ED_EDUC_W_MYS"   # mean years schooling as proxy
        surv_rows = dhs_df[dhs_df.get("IndicatorId", "") == surv_id] if "IndicatorId" in dhs_df.columns else pd.DataFrame()
        if not surv_rows.empty and "CharacteristicLabel" in surv_rows.columns:
            # DHS is at Admin1 — map to Admin2 by region membership
            # (simplified: use province-to-region lookup if available)
            region_map = surv_rows.set_index("CharacteristicLabel")["Value"].to_dict()
            # Inverse: lower years of schooling = higher fragility
            result["B4_survival_inv_norm"] = result[ADMIN_COL].map(
                lambda x: 1 - minmax(pd.Series(list(region_map.values()))).mean()
            )
            score_basis += "B4(admin1) "

    # B5: IDP presence
    if idp_df is not None and not idp_df.empty:
        idp_col  = next((c for c in idp_df.columns if "idp" in c.lower() or "deplace" in c.lower()), None)
        dist_col = next((c for c in idp_df.columns if "admin2" in c.lower() or "province" in c.lower()), None)
        if idp_col and dist_col:
            idp_map = idp_df.set_index(dist_col)[idp_col].to_dict()
            result["B5_idp_count"] = result[ADMIN_COL].map(idp_map).fillna(0)
            result["B5_idp_norm"]  = minmax(result["B5_idp_count"])
            score_basis += "B5 "

    # Weighted composite fragility
    norm_cols = [c for c in ["B1_closure_norm", "B2_density_gap_norm",
                              "B3_oos_norm", "B4_survival_inv_norm", "B5_idp_norm"]
                 if c in result.columns]
    w_map = {"B1_closure_norm": W_B1, "B2_density_gap_norm": W_B2,
             "B3_oos_norm": W_B3, "B4_survival_inv_norm": W_B4,
             "B5_idp_norm":  W_B5}
    weights = [w_map[c] for c in norm_cols]

    result["system_fragility"] = weighted_mean(result, norm_cols, weights)
    result["score_basis"]      = score_basis.str.strip()
    result["year"]             = ref_year

    return result


# ── Combine sub-indices into EVI ──────────────────────────────────────────────

def combine_indices(
    sub_a: pd.DataFrame,
    sub_b: pd.DataFrame,
    method: str = "geometric",
) -> pd.DataFrame:
    """
    Combine conflict pressure and system fragility into EVI.

    Geometric mean (INFORM-style): EVI = (A^w_A) × (B^w_B)
      Penalises extreme imbalance — a district with zero fragility
      or zero pressure scores low even if the other is high.

    Simple mean: EVI = w_A × A + w_B × B
      More transparent, rewards partial vulnerability.
    """
    merged = sub_a.merge(sub_b, on=[ADMIN_COL, "year"], how="outer")
    a = merged["conflict_pressure"].fillna(0)
    b = merged["system_fragility"].fillna(0)

    if method == "geometric":
        # Add small epsilon to avoid log(0)
        eps = 0.001
        merged["evi_score"] = (
            (a + eps) ** WEIGHT_A * (b + eps) ** WEIGHT_B
        )
        # Rescale to [0,1]
        merged["evi_score"] = minmax(merged["evi_score"])
    else:
        merged["evi_score"] = WEIGHT_A * a + WEIGHT_B * b

    merged["evi_tier"] = classify(merged["evi_score"])
    return merged


# ── Sensitivity test ──────────────────────────────────────────────────────────

def sensitivity_test(sub_a: pd.DataFrame, sub_b: pd.DataFrame) -> pd.DataFrame:
    """
    Re-run with three alternate weightings to test index robustness.
    If tier classifications are stable, the index is defensible.
    """
    scenarios = {
        "equal_weight":       (0.50, 0.50),
        "conflict_dominant":  (0.70, 0.30),
        "fragility_dominant": (0.30, 0.70),
    }
    results = []
    for name, (wa, wb) in scenarios.items():
        a = sub_a["conflict_pressure"].fillna(0)
        b = sub_b["system_fragility"].fillna(0)
        score = wa * a.values + wb * b.values
        tier  = classify(pd.Series(minmax(pd.Series(score))))
        df    = sub_a[[ADMIN_COL]].copy()
        df["scenario"]  = name
        df["evi_score"] = minmax(pd.Series(score)).values
        df["evi_tier"]  = tier.values
        results.append(df)
    return pd.concat(results, ignore_index=True)


# ── National trends ───────────────────────────────────────────────────────────

def build_national_trends(acled: pd.DataFrame, wb_df: pd.DataFrame | None) -> pd.DataFrame:
    acled["year"] = pd.to_numeric(acled["year"], errors="coerce")
    acled["fatalities"] = pd.to_numeric(acled["fatalities"], errors="coerce").fillna(0)

    conflict = (acled.groupby("year")
                      .agg(total_events=("event_id_cnty","count"),
                           total_fatalities=("fatalities","sum"))
                      .reset_index())

    if wb_df is not None and not wb_df.empty:
        for ind in ["SE.PRM.NENR", "SE.PRM.CMPT.ZS", "SE.PRM.UNER"]:
            sub = wb_df[wb_df.get("indicator_code","") == ind][["year","value"]].rename(columns={"value": ind})
            conflict = conflict.merge(sub, on="year", how="left")

    return conflict.sort_values("year")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Building Education Vulnerability Index for {ISO3}...\n")

    # Load ACLED
    acled = pd.read_csv(IN_ACLED, low_memory=False)
    acled = acled.rename(columns={"admin1": "admin1", "admin2": "admin2"})
    for c in ["admin1","admin2"]:
        if c in acled.columns:
            acled[c] = acled[c].str.strip().str.title()
    print(f"  ACLED: {len(acled):,} events")

    # Load education data
    dhs_df = pd.read_csv(IN_DHS) if IN_DHS.exists() else None
    wb_df  = pd.read_csv(IN_WORLDBANK) if IN_WORLDBANK.exists() else None
    print(f"  DHS:   {'loaded' if dhs_df is not None else 'not found — skipping B4'}")
    print(f"  WB:    {'loaded' if wb_df is not None else 'not found — skipping B3'}")

    # Load BFA-specific inputs
    closures_df = pd.read_csv(IN_CLOSURES) if IN_CLOSURES.exists() else None
    idp_df      = pd.read_csv(IN_IDP)      if IN_IDP.exists()      else None
    print(f"  Closures: {'loaded' if closures_df is not None else 'not found — skipping B1'}")
    print(f"  IDP:      {'loaded' if idp_df is not None else 'not found — skipping B5'}")

    # School locations
    schools_gdf = None
    if IN_SCHOOLS.exists():
        try:
            import geopandas as gpd
            schools_gdf = gpd.read_file(IN_SCHOOLS)
            print(f"  Schools: {len(schools_gdf):,} locations loaded")
        except Exception as e:
            print(f"  Schools: could not load ({e})")

    # Get district list from ACLED
    admin_regions = sorted(acled[ADMIN_COL].dropna().unique().tolist())
    print(f"\n  Districts ({ADMIN_COL}): {len(admin_regions)}")

    # Build indices per year
    all_evi = []
    for year in range(START_YEAR, END_YEAR + 1):
        sub_a = build_conflict_pressure(acled, year)
        sub_b = build_system_fragility(
            closures_df, schools_gdf, dhs_df, wb_df, idp_df,
            admin_regions, year
        )
        evi = combine_indices(sub_a, sub_b, SCORE_METHOD)
        all_evi.append(evi)
        n_critical = (evi["evi_tier"] == "critical").sum()
        n_high     = (evi["evi_tier"] == "high").sum()
        print(f"  {year}: {n_critical} critical, {n_high} high / {len(evi)} districts")

    # Save main output
    full_evi = pd.concat(all_evi, ignore_index=True)
    evi_path = OUT_DIR / f"{ISO3}_evi_scores.csv"
    full_evi.to_csv(evi_path, index=False)
    print(f"\n✓ EVI scores → {evi_path}")

    # Sensitivity test (latest year)
    latest_a = build_conflict_pressure(acled, END_YEAR)
    latest_b = build_system_fragility(
        closures_df, schools_gdf, dhs_df, wb_df, idp_df,
        admin_regions, END_YEAR
    )
    sens = sensitivity_test(latest_a, latest_b)
    sens_path = OUT_DIR / f"{ISO3}_evi_sensitivity.csv"
    sens.to_csv(sens_path, index=False)
    print(f"✓ Sensitivity test → {sens_path}")

    # Tier stability across scenarios
    pivot = sens.pivot(index=ADMIN_COL, columns="scenario", values="evi_tier")
    stable = (pivot.nunique(axis=1) == 1).sum()
    print(f"\n  Tier stability: {stable}/{len(pivot)} districts "
          f"({stable/len(pivot)*100:.0f}%) classified identically across all weightings")

    # National trends
    trends = build_national_trends(acled, wb_df)
    trends_path = OUT_DIR / f"{ISO3}_national_trends.csv"
    trends.to_csv(trends_path, index=False)
    print(f"✓ National trends → {trends_path}")

    # Indicator details (raw, pre-normalisation)
    detail_cols = [c for c in full_evi.columns
                   if not c.endswith("_norm") and c not in ["score_basis"]]
    full_evi[detail_cols].to_csv(
        OUT_DIR / f"{ISO3}_indicator_details.csv", index=False
    )
    print(f"✓ Indicator details → {OUT_DIR}/{ISO3}_indicator_details.csv")

    print(f"\n{'='*55}")
    print(f"Index summary for {ISO3} — {END_YEAR}")
    latest = full_evi[full_evi["year"] == END_YEAR]
    print(latest["evi_tier"].value_counts().sort_index().to_string())
    print(f"\nTop 5 most vulnerable districts:")
    print(latest.nlargest(5, "evi_score")[[ADMIN_COL,"evi_score","evi_tier","score_basis"]]
                .to_string(index=False))