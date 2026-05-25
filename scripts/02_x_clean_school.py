import pandas as pd
import geopandas as gpd
from pathlib import Path

def process_school_data(iso3="BFA", buffer_meters=50):
    input_path = Path(f"data/clean/schools/schools_{iso3}.csv")
    output_path = Path(f"data/clean/schools/final_cleaned_schools_{iso3}.csv")
    
    if not input_path.exists():
        print(f"✗ Input file not found: {input_path}")
        return

    # Load data
    df = pd.read_csv(input_path)
    original_count = len(df)
    
    # 1. Coordinate-based deduplication (strict exact matches)
    df['lat_round'] = df['latitude'].round(5)
    df['lon_round'] = df['longitude'].round(5)
    df_strict = df.drop_duplicates(subset=['lat_round', 'lon_round'])
    
    # 2. Spatial/Fuzzy deduplication using buffer
    gdf = gpd.GeoDataFrame(
        df_strict, 
        geometry=gpd.points_from_xy(df_strict.longitude, df_strict.latitude),
        crs="EPSG:4326"
    ).to_crs(epsg=3857) # Projected CRS for buffer calculation in meters
    
    # Buffer schools to catch duplicates within 'buffer_meters'
    gdf['geometry'] = gdf.buffer(buffer_meters)
    
    # Self-spatial join
    joined = gpd.sjoin(gdf, gdf[['geometry']], how='inner', predicate='intersects')
    
    # Keep the first index for each cluster
    final_indices = joined.groupby(joined.index)['index_right'].first().unique()
    
    # Reconstruct cleaned dataframe
    df_cleaned = df_strict.loc[final_indices].drop(columns=['lat_round', 'lon_round'])
    
    cleaned_count = len(df_cleaned)
    merged_count = original_count - cleaned_count
    
    df_cleaned.to_csv(output_path, index=False)
    
    print(f"--- Unified School Data Processing Report for {iso3} ---")
    print(f"Original row count:  {original_count:,}")
    print(f"Duplicates merged:   {merged_count:,}")
    print(f"Final row count:     {cleaned_count:,}")
    print(f"Output saved to:     {output_path}")

if __name__ == "__main__":
    process_school_data()
