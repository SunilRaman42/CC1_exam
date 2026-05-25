import json
import pandas as pd
from pathlib import Path

def aggregate_at_risk_schools():
    # Load data
    score_path = Path("artifacts/school_vulnerability_scores.json")
    if not score_path.exists():
        print("✗ Score data missing.")
        return

    with open(score_path, 'r', encoding='utf-8') as f:
        scores = json.load(f)

    # Structure: { year: { province: { count: int, schools: [{name, lat, lon}] } } }
    aggregated = {}

    for s in scores:
        province = s.get("province", "Unknown")
        v_score = s.get("v_score", 0)
        at_risk_years = s.get("at_risk_years", [])
        name = s.get("name", "Unnamed School")
        lat = s.get("lat", 0)
        lon = s.get("lon", 0)

        # Threshold criteria (using 0.7 as per existing UI logic)
        if v_score > 0.7:
            for year in at_risk_years:
                y_str = str(year)
                if y_str not in aggregated:
                    aggregated[y_str] = {}
                if province not in aggregated[y_str]:
                    aggregated[y_str][province] = {"count": 0, "schools": []}
                
                aggregated[y_str][province]["count"] += 1
                aggregated[y_str][province]["schools"].append({
                    "name": name,
                    "lat": lat,
                    "lon": lon
                })

    # Save output with ensure_ascii=False for proper Unicode support
    out_path = Path("artifacts/province_at_risk_stats.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Aggregation complete. Saved to {out_path}")

if __name__ == "__main__":
    aggregate_at_risk_schools()
