import geopandas as gpd

schools  = gpd.read_file("data/raw/schools/schools_hdx/BFA_schools.geojson")
admin2   = gpd.read_file("data/raw/boundaries/BFA_admin2.geojson")

# Detect the admin2 name column in boundaries
name_col = next(c for c in admin2.columns
                if any(x in c.lower() for x in ["adm2_en","adm2name","admin2","nom"]))

joined   = gpd.sjoin(schools, admin2[[name_col, "geometry"]], how="left", predicate="within")
counts   = joined.groupby(name_col).size().reset_index(name="school_count")
counts   = counts.rename(columns={name_col: "Admin2"})