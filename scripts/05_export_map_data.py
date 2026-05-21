"""
05_export_map_data.py
=====================
Joins vulnerability scores onto admin1 boundaries and exports:
  - assets/data.geojson   → choropleth map layer (Leaflet-ready)
  - assets/trends.json    → time-series data for the chart panel
  - assets/insights.json  → headline stats and key findings

Generic — change ISO3 at the top.
"""

import json
import pandas as pd
import geopandas as gpd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
ISO3 = "BFA"

IN_VULN      = Path(f"data/clean/{ISO3}_vulnerability.csv")
IN_TRENDS    = Path(f"data/clean/{ISO3}_national_trends.csv")
IN_ADMIN1    = Path(f"data/raw/boundaries/{ISO3}_admin1.geojson")
ASSETS_DIR   = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)

# Year to use for the default map view
MAP_YEAR = 2023


def build_geojson(vuln: pd.DataFrame, boundaries: gpd.GeoDataFrame) -> dict:
    """
    Join vulnerability scores onto admin1 polygons for the choropleth.
    Tries common admin1 name column variants from OCHA COD boundaries.
    """
    # Latest year available
    latest_year = vuln["year"].max()
    vuln_latest = vuln[vuln["year"] == latest_year].copy()

    # Detect admin1 name column in boundaries
    name_col = next(
        (c for c in boundaries.columns
         if any(x in c.lower() for x in ["adm1_en", "adm1name", "name_1", "shapename", "admin1name"])),
        boundaries.columns[0]
    )
    boundaries = boundaries.rename(columns={name_col: "region"})
    boundaries["region"] = boundaries["region"].str.strip().str.title()

    merged = boundaries.merge(
        vuln_latest[["region", "score", "score_tercile", "score_basis",
                     "events", "fatalities", "events_norm"]],
        on="region",
        how="left"
    )

    # Build GeoJSON manually so we control exactly what's in properties
    features = []
    for _, row in merged.iterrows():
        if row.geometry is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": json.loads(row.geometry.to_json()),
            "properties": {
                "region":        row["region"],
                "score":         round(float(row["score"]), 3) if pd.notna(row.get("score")) else None,
                "priority":      str(row.get("score_tercile", "unknown")),
                "score_basis":   str(row.get("score_basis", "")),
                "events":        int(row["events"])        if pd.notna(row.get("events"))     else None,
                "fatalities":    int(row["fatalities"])    if pd.notna(row.get("fatalities")) else None,
                "year":          int(latest_year),
            }
        })

    return {"type": "FeatureCollection", "features": features}


def build_trends_json(trends: pd.DataFrame) -> list[dict]:
    """Convert national trends DataFrame to a JSON array for the chart."""
    records = []
    for _, row in trends.iterrows():
        record = {"year": int(row["year"])}
        for col in trends.columns:
            if col == "year":
                continue
            val = row[col]
            record[col] = round(float(val), 2) if pd.notna(val) else None
        records.append(record)
    return records


def build_insights(vuln: pd.DataFrame, trends: pd.DataFrame) -> dict:
    """
    Compute headline stats for the artifact's summary panel.
    These become the 'above the fold' numbers on index.html.
    """
    latest_year  = vuln["year"].max()
    vuln_latest  = vuln[vuln["year"] == latest_year]
    high_risk    = vuln_latest[vuln_latest["score_tercile"] == "high_priority"]

    # Conflict trend: compare last 3 years to prior 3 years
    recent    = trends[trends["year"] >= latest_year - 2]["total_events"].mean()
    prior     = trends[trends["year"].between(latest_year - 5, latest_year - 3)]["total_events"].mean()
    trend_pct = round((recent - prior) / prior * 100, 1) if prior > 0 else None

    # Survival rate in latest available year
    survival_col = next((c for c in trends.columns if "SURVCOMP.PT4" in c
                         and "F" not in c and "M" not in c), None)
    survival_latest = None
    if survival_col:
        sv = trends[trends["year"] == latest_year][survival_col]
        survival_latest = round(float(sv.values[0]), 1) if len(sv) and pd.notna(sv.values[0]) else None

    return {
        "country":           ISO3,
        "analysis_year":     int(latest_year),
        "high_risk_regions": int(len(high_risk)),
        "total_regions":     int(len(vuln_latest)),
        "conflict_trend_pct": trend_pct,
        "survival_rate_pct": survival_latest,
        "top_3_high_risk":   high_risk.nlargest(3, "score")["region"].tolist(),
        "total_events":      int(trends[trends["year"] == latest_year]["total_events"].sum()),
        "total_fatalities":  int(trends[trends["year"] == latest_year]["total_fatalities"].sum()),
    }


if __name__ == "__main__":
    print(f"Exporting map data for {ISO3}...")

    vuln   = pd.read_csv(IN_VULN)
    trends = pd.read_csv(IN_TRENDS)

    # ── GeoJSON ──────────────────────────────────────────────────────────────
    if IN_ADMIN1.exists():
        boundaries = gpd.read_file(IN_ADMIN1)
        geojson    = build_geojson(vuln, boundaries)
        geojson_path = ASSETS_DIR / "data.geojson"
        with open(geojson_path, "w") as f:
            json.dump(geojson, f, separators=(",", ":"))
        print(f"  ✓ GeoJSON ({len(geojson['features'])} features) → {geojson_path}")
    else:
        print(f"  ⚠ No boundary file at {IN_ADMIN1} — skipping GeoJSON")
        print(f"    Run 03_fetch_boundaries.py first, or download manually")

    # ── Trends JSON ───────────────────────────────────────────────────────────
    trends_json = build_trends_json(trends)
    trends_path = ASSETS_DIR / "trends.json"
    with open(trends_path, "w") as f:
        json.dump(trends_json, f, separators=(",", ":"))
    print(f"  ✓ Trends ({len(trends_json)} years) → {trends_path}")

    # ── Insights JSON ─────────────────────────────────────────────────────────
    insights = build_insights(vuln, trends)
    insights_path = ASSETS_DIR / "insights.json"
    with open(insights_path, "w") as f:
        json.dump(insights, f, indent=2)
    print(f"  ✓ Insights → {insights_path}")
    print(f"\n  Headline: {insights['high_risk_regions']}/{insights['total_regions']} "
          f"admin1 regions classified HIGH priority")
    print(f"  Top 3 high-risk: {', '.join(insights['top_3_high_risk'])}")
