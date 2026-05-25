import pandas as pd
import geopandas as gpd
from pathlib import Path

def fuzzy_deduplicate(iso3="BFA"):
    input_path = Path(f"data/clean/schools/schools_{iso3}.csv")
    output_path = Path(f"data/clean/schools/final_cleaned_schools_{iso3}.csv")
    
    if not input_path.exists():
        print(f"✗ Input file not found: {input_path}")
        return

    # Load data
    df = pd.read_csv(input_path)
    original_count = len(df)
    
    # Create GeoDataFrame for spatial analysis
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df.longitude, df.latitude),
        crs="EPSG:4326"
    ).to_crs(epsg=3857)
    
    # Create a 50m buffer
    gdf_buffer = gdf.copy()
    gdf_buffer['geometry'] = gdf_buffer.buffer(50)
    
    # Perform a spatial join of the schools against themselves
    joined = gpd.sjoin(gdf, gdf_buffer[['name', 'geometry']], how='inner', predicate='within')
    
    # Group by the name (assuming schools with the same name within 50m are dupes)
    # Using 'index_right' from the spatial join to identify the original index of the 'dupes'
    final_indices = joined.groupby('name_left')['index_right'].first().unique()
    
    df_cleaned = df.loc[final_indices]
    
    cleaned_count = len(df_cleaned)
    merged_count = original_count - cleaned_count
    
    df_cleaned.to_csv(output_path, index=False)
    
    print(f"--- Fuzzy Deduplication Report for {iso3} ---")
    print(f"Original row count:  {original_count:,}")
    print(f"Duplicates merged:   {merged_count:,}")
    print(f"Final row count:     {cleaned_count:,}")
    print(f"Output saved to:     {output_path}")

if __name__ == "__main__":
    fuzzy_deduplicate()
