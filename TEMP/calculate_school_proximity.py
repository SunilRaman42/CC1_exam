import pandas as pd
import numpy as np
import json
import os

def haversine_vectorized(lon1, lat1, lon2, lat2):
    """Vectorized haversine distance calculation."""
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return c * 6371

def main():
    # ── Config ────────────────────────────────────────────────────────────────
    SCHOOLS_PATH  = 'data/clean/schools/schools_BFA.csv'
    CONFLICT_PATH = 'data/clean/acled/HRP_2_countries/Burkina_Faso_geocoded.csv'
    OUTPUT_STATS  = 'artifacts/proximity_risk_stats.json'
    OUTPUT_DETAIL = 'artifacts/school_vulnerability_scores.json'
    
    RADIUS_KM = 10.0
    BASE_DECAY = 0.5    # 50% risk remains after 1 year of peace
    SCARRING_FACTOR = 0.1 # Each previous attack adds 10% to the retention rate
    MAX_RETENTION = 0.95  # Risk never decays slower than 95% per year
    RISK_THRESHOLD = 0.2  # Threshold to be considered "At Risk"
    
    print("--- Adaptive School Proximity Risk Calculator ---")
    print(f"Model: Base Decay {BASE_DECAY}, Scarring {SCARRING_FACTOR}")
    
    # ── Load Data ─────────────────────────────────────────────────────────────
    if not os.path.exists(SCHOOLS_PATH) or not os.path.exists(CONFLICT_PATH):
        print("✗ Required data files missing.")
        return

    schools = pd.read_csv(SCHOOLS_PATH)
    conflict = pd.read_csv(CONFLICT_PATH)
    conflict = conflict[conflict['Events'] > 0].copy()
    
    # ── Initialize State ──────────────────────────────────────────────────────
    num_schools = len(schools)
    v_scores = np.zeros(num_schools)
    trauma_counts = np.zeros(num_schools, dtype=int)
    # Track years a school was 'At Risk'
    at_risk_years = {i: [] for i in range(num_schools)}
    
    school_lats = schools['latitude'].values
    school_lons = schools['longitude'].values
    
    years = sorted(conflict['Year'].unique())
    years = range(min(years), 2027)
    
    yearly_counts = {}
    school_names = schools['name'].fillna("Unnamed School").values

    print(f"Processing {num_schools:,} schools over {len(years)} years...")

    # ── Simulation ────────────────────────────────────────────────────────────
    for year in years:
        year_events = conflict[conflict['Year'] == year]
        
        hit_this_year = np.zeros(num_schools, dtype=bool)
        if not year_events.empty:
            event_locs = year_events[['Latitude', 'Longitude']].drop_duplicates()
            for _, event in event_locs.iterrows():
                dist = haversine_vectorized(school_lons, school_lats, event['Longitude'], event['Latitude'])
                hit_this_year |= (dist <= RADIUS_KM)
        
        trauma_counts[hit_this_year] += 1
        retention_rates = np.minimum(MAX_RETENTION, BASE_DECAY + (SCARRING_FACTOR * (trauma_counts - 1)))
        retention_rates[trauma_counts == 0] = 0
        
        v_scores[~hit_this_year] *= retention_rates[~hit_this_year]
        v_scores[hit_this_year] = 1.0
        
        # Track years at risk
        at_risk_indices = np.where(v_scores > RISK_THRESHOLD)[0]
        for idx in at_risk_indices:
            at_risk_years[idx].append(int(year))
            
        yearly_counts[int(year)] = len(at_risk_indices)
        print(f"  Year {year}: {len(at_risk_indices):5,} at risk")

    # ── Export ────────────────────────────────────────────────────────────────
    os.makedirs('artifacts', exist_ok=True)
    
    with open(OUTPUT_STATS, 'w') as f:
        json.dump(yearly_counts, f, indent=2)
        
    final_state = []
    for i in range(num_schools):
        if v_scores[i] > 0.01:
            final_state.append({
                "name": str(school_names[i]),
                "lat": float(school_lats[i]),
                "lon": float(school_lons[i]),
                "v_score": round(float(v_scores[i]), 3),
                "trauma": int(trauma_counts[i]),
                "at_risk_years": at_risk_years[i]
            })
            
    with open(OUTPUT_DETAIL, 'w') as f:
        json.dump(final_state, f, indent=2)

    print(f"\n✓ Analysis complete.")
    print(f"  Summary stats: {OUTPUT_STATS}")
    print(f"  Detailed scores: {OUTPUT_DETAIL}")

if __name__ == "__main__":
    main()
