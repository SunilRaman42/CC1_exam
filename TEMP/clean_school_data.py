import pandas as pd
import numpy as np
import os
from pathlib import Path

def deduplicate_schools(iso3="BFA"):
    input_path = Path(f"data/clean/schools/schools_{iso3}.csv")
    output_path = Path(f"data/clean/schools/cleaned_schools_{iso3}.csv")
    
    if not input_path.exists():
        print(f"✗ Input file not found: {input_path}")
        return

    df = pd.read_csv(input_path)
    original_count = len(df)
    
    # Use rounding to account for floating point precision issues in lat/long
    # 5 decimal places is roughly 1.1 meters, which is plenty for school deduplication
    df['lat_round'] = df['latitude'].round(5)
    df['lon_round'] = df['longitude'].round(5)
    
    # Deduplicate based on rounded coordinates
    # We keep the first occurrence of each unique location
    df_cleaned = df.drop_duplicates(subset=['lat_round', 'lon_round'])
    
    cleaned_count = len(df_cleaned)
    merged_count = original_count - cleaned_count
    
    # Clean up temp columns
    df_cleaned = df_cleaned.drop(columns=['lat_round', 'lon_round'])
    
    df_cleaned.to_csv(output_path, index=False)
    
    print(f"--- Deduplication Report for {iso3} ---")
    print(f"Original row count:  {original_count:,}")
    print(f"Rows merged:         {merged_count:,}")
    print(f"Final row count:     {cleaned_count:,}")
    print(f"Output saved to:     {output_path}")

if __name__ == "__main__":
    deduplicate_schools()
