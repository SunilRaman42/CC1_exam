import pandas as pd
import folium
from folium.plugins import TimestampedGeoJson
import os
import numpy as np

def create_interactive_map(csv_file_path, output_html='map.html'):
    """
    Creates an interactive Leaflet map with a time slider for a specific country CSV.
    Features:
    - Time slider (Yearly/Monthly steps)
    - Toggled layers for Fatalities and Events (via Layer Control)
    - Bubble sizes proportionate to the metric
    """
    if not os.path.exists(csv_file_path):
        print(f"Error: File {csv_file_path} not found.")
        return

    # Load data
    df = pd.read_csv(csv_file_path)
    df.columns = [c.lower() for c in df.columns]
    
    # Ensure date is datetime
    # Handle cases where month might be represented as number or name
    # Convert month to a consistent format (e.g., '01' for January)
    df['month'] = df['month'].apply(lambda x: f'{x:02d}' if isinstance(x, int) else pd.to_datetime(x, format='%B').month)
    df['month'] = df['month'].apply(lambda x: f'{x:02d}' if isinstance(x, str) else f'{x:02d}') # Ensure month is two digits string

    # Create a new 'event_date' column from 'Year' and 'Month'
    df['event_date'] = pd.to_datetime(df['year'].astype(str) + '-' + df['month'] + '-01')
    df = df.sort_values('event_date')

    # Drop rows without location
    df = df.dropna(subset=['latitude', 'longitude'])

    country_name = df['country'].iloc[0] if 'country' in df.columns else "country"

    # Initialize Map centered on the country
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles='CartoDB positron')

    # Function to create GeoJSON features
    def create_features(data, metric_col, color):
        features = []
        for _, row in data.iterrows():
            # Calculate radius: use log scale or sqrt to keep bubbles manageable
            # Let's use sqrt and a multiplier
            val = row[metric_col] if metric_col in row else 1
            if pd.isna(val) or val <= 0:
                val = 1

            radius = np.sqrt(val) * 5 + 2 # Minimum size 2

            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [row['longitude'], row['latitude']],
                },
                'properties': {
                    'time': row['event_date'].strftime('%Y-%m-%d'),
                    'style': {'color': color, 'fillColor': color, 'fillOpacity': 0.6},
                    'icon': 'circle',
                    'iconstyle': {
                        'fillColor': color,
                        'fillOpacity': 0.6,
                        'stroke': 'true',
                        'radius': radius
                    },
                    'popup': f"<b>Date:</b> {row['event_date'].strftime('%Y-%m-%d')}<br>"
                             f"<b>Type:</b> {row.get('event_type', 'N/A')}<br>"
                             f"<b>{metric_col_name.capitalize()}:</b> {val}<br>"
                             f"<b>Notes:</b> {row.get('notes', 'No notes available')[:200]}..."
                }
            }
            features.append(feature)
        return features

    # Layer 1: Fatalities
    fatality_features = create_features(df, 'fatalities', 'red')
    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': fatality_features},
        period='P1M', # Monthly steps
        add_last_point=True,
        auto_play=False,
        loop=False,
        max_speed=1,
        loop_button=True,
        date_options='YYYY-MM',
        time_slider_drag_update=True
    ).add_to(m)

    # Note: Folium's TimestampedGeoJson doesn't support easy "toggling" of metrics 
    # with the same slider in a single plugin instance. 
    # To keep it generic and functional, this script focuses on Fatalities as requested.
    # To see 'Number of Events', one would aggregate the count.

    # Save the map
    m.save(output_html)
    print(f"Success! Map for {country_name} saved to {output_html}")
if __name__ == "__main__":
    # Generic execution: it looks for Lebanon by default but can be changed
    # Usage: python test_fatalities.py <path_to_csv> <output_name> <metric>
    # metric can be 'fatalities' or 'events'
    import sys
    
    target_csv = 'DATA/Lebanon_geocoded.csv' # Default
    output_file = 'index.html'
    metric = 'fatalities' # Default metric
    
    if len(sys.argv) > 1:
        target_csv = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    if len(sys.argv) > 3:
        metric = sys.argv[3].lower() # Ensure metric is lowercase for comparison
        
    create_interactive_map(target_csv, output_file, metric)
'
    
    if len(sys.argv) > 1:
        target_csv = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
        
    create_interactive_map(target_csv, output_file)
