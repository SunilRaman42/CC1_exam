"""
06_export_map_data.py
=====================
Joins hybrid vulnerability scores onto admin2 boundaries and exports:
  - artifacts/data.geojson   → choropleth map layer (Leaflet-ready)
  - artifacts/trends.json    → time-series data for the chart panel
  - artifacts/insights.json  → headline stats and key findings

Supports dynamic ISO3 input. Defaults to Admin2 resolution.
"""

import json
import argparse
import os
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import mapping

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_ISO3 = os.environ.get("PIPELINE_ISO3", "BFA")
OUT_DIR      = Path("artifacts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def build_geojson(vuln: pd.DataFrame, boundaries: gpd.GeoDataFrame) -> dict:
    """
    Join vulnerability scores onto admin2 polygons for the choropleth.
    """
    # Detect admin2 name column in boundaries (standard OCHA COD naming)
    name_col = next(
        (c for c in boundaries.columns
         if any(x in c.lower() for x in ["adm2_en", "adm2_name", "name_2", "shapename", "admin2name"])),
        boundaries.columns[0]
    )
    boundaries = boundaries.rename(columns={name_col: "Admin2"})
    boundaries["Admin2"] = boundaries["Admin2"].str.strip().str.title()
    
    # Standardize Admin2 in vuln data as well
    vuln["Admin2"] = vuln["Admin2"].str.strip().str.title()

    # Build GeoJSON manually so we control exactly what's in properties
    features = []
    # We include ALL years in the GeoJSON now, index.html filters by year
    for _, row in vuln.iterrows():
        # Find matching boundary
        match = boundaries[boundaries["Admin2"] == row["Admin2"]]
        if match.empty:
            continue
            
        geom = match.iloc[0].geometry
        if geom is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "admin2":        row["Admin2"],
                "region":        row["region"],
                "year":          int(row["year"]),
                "score":         round(float(row["score"]), 3),
                "priority":      str(row["score_tercile"]),
                "events":        int(row["events"]) if pd.notna(row["events"]) else 0,
                "fatalities":    int(row["fatalities"]) if pd.notna(row["fatalities"]) else 0,
                "edu_baseline":  round(float(row["edu_baseline"]), 3),
                "conflict_score": round(float(row["conflict_score"]), 3),
                "score_basis":   str(row["score_basis"])
            }
        })

    return {"type": "FeatureCollection", "features": features}


def build_trends_json(trends: pd.DataFrame) -> list[dict]:
    """Convert national trends DataFrame to a JSON array for the chart."""
    # Round all numeric columns
    trends = trends.round(3)
    return trends.to_dict(orient="records")


def build_insights(vuln: pd.DataFrame, trends: pd.DataFrame, iso3: str) -> dict:
    """
    Compute headline stats for the summary panel.
    """
    latest_year  = vuln["year"].max()
    vuln_latest  = vuln[vuln["year"] == latest_year]
    # In our 4-tier system, high risk is critical + high_priority
    critical     = vuln_latest[vuln_latest["score_tercile"] == "critical"]
    high_priority = vuln_latest[vuln_latest["score_tercile"] == "high_priority"]

    # Conflict trend: compare last 3 years to prior 3 years
    recent    = trends[trends["year"] >= latest_year - 2]["total_events"].mean()
    prior     = trends[trends["year"].between(latest_year - 5, latest_year - 3)]["total_events"].mean()
    trend_pct = round((recent - prior) / prior * 100, 1) if prior and prior > 0 else 0

    return {
        "country":           iso3,
        "analysis_year":     int(latest_year),
        "critical_regions":  int(len(critical)),
        "high_risk_regions": int(len(high_priority)),
        "total_regions":     int(len(vuln_latest)),
        "conflict_trend_pct": trend_pct,
        "top_3_critical":    critical.nlargest(3, "score")["Admin2"].tolist(),
        "total_events":      int(trends[trends["year"] == latest_year]["total_events"].sum()),
        "total_fatalities":  int(trends[trends["year"] == latest_year]["total_fatalities"].sum()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export analysis results to web formats.")
    parser.add_argument("--iso3", default=DEFAULT_ISO3, help="ISO3 country code")
    args = parser.parse_args()
    iso3 = args.iso3.upper()

    print(f"Exporting map data for {iso3}...")

    in_vuln   = OUT_DIR / f"{iso3}_hybrid_vulnerability_index.csv"
    in_trends = OUT_DIR / f"{iso3}_national_trends.csv"
    in_admin2 = Path(f"data/raw/boundaries/{iso3}_admin2.geojson")

    if not in_vuln.exists():
        print(f"✗ Vulnerability file missing: {in_vuln}")
        exit(1)
    if not in_trends.exists():
        print(f"✗ National trends file missing: {in_trends}")
        exit(1)

    vuln   = pd.read_csv(in_vuln)
    trends = pd.read_csv(in_trends)

    # ── GeoJSON ──────────────────────────────────────────────────────────────
    if in_admin2.exists():
        boundaries = gpd.read_file(in_admin2)
        geojson    = build_geojson(vuln, boundaries)
        geojson_path = OUT_DIR / "data.geojson"
        with open(geojson_path, "w") as f:
            json.dump(geojson, f, separators=(",", ":"))
        print(f"  ✓ GeoJSON ({len(geojson['features'])} features) → {geojson_path}")
    else:
        print(f"  ⚠ No Admin2 boundary file at {in_admin2} — skipping GeoJSON")

    # ── Trends JSON ───────────────────────────────────────────────────────────
    trends_json = build_trends_json(trends)
    trends_path = OUT_DIR / "trends.json"
    with open(trends_path, "w") as f:
        json.dump(trends_json, f, separators=(",", ":"))
    print(f"  ✓ Trends ({len(trends_json)} years) → {trends_path}")

    # ── Insights JSON ─────────────────────────────────────────────────────────
    insights = build_insights(vuln, trends, iso3)
    insights_path = OUT_DIR / "insights.json"
    with open(insights_path, "w") as f:
        json.dump(insights, f, indent=2)
    print(f"  ✓ Insights → {insights_path}")
    print(f"\n  Headline: {insights['critical_regions']} regions CRITICAL, {insights['high_risk_regions']} HIGH priority")
