# Scripts Overview

This folder contains the data acquisition and processing scripts for the analysis pipeline.

## 01. ACLED Data Pipeline

### [01_fetch_acled_hdx.py](./01_fetch_acled_hdx.py)
Fetches the latest ACLED conflict data from the Humanitarian Data Exchange (HDX) API.
- **Output**: `data/raw/acled/acled_YYYY-MM-DD.xlsx`
- **Features**: Includes automated integrity checks to ensure the Excel archive is valid.

### [01_1_split_acled.py](./01_1_split_acled.py)
Processes the ACLED Excel file, splitting each sheet into individual CSV files.
- **Output**: `data/raw/acled/split/*.csv`
- **Features**: 
    - Generates a `manifest.json` mapping countries to their respective CSV files.
    - Creates Markdown summaries of unique countries for each sheet.

### [01_2_hrp_country.py](./01_2_hrp_country.py)
Filters and groups ACLED data into country-specific files.
- **Input**: Uses the `manifest.json` and CSVs from step 01_1.
- **Usage**: 
    - `python3 scripts/01_2_hrp_country.py --country "Burkina Faso"` (Targeted extraction)
    - `python3 scripts/01_2_hrp_country.py` (Full split of all countries)
- **Output**: `data/raw/acled/countries/{SheetName}_countries/{Country}.csv`

---

## 02. Infrastructure Data (Schools)

### [02_fetch_schools_hdx.py](./02_fetch_schools_hdx.py)
Downloads HOTOSM education facility point data for multiple countries from HDX.
- **Output**: 
    - `data/raw/schools_hdx/{ISO3}_schools.geojson`
    - `data/raw/schools_hdx/schools_all.geojson` (Merged dataset)
    - `data/raw/schools_hdx/schools_all.csv` (Flat CSV with coordinates)
- **Features**: Uses dynamic HDX API discovery and fuzzy matching to resolve stale download links automatically.

### [02_fetch_schools.py](./02_fetch_schools.py)
(Legacy) Original version of the school fetcher using hardcoded UUIDs. Superseded by the HDX API version.

---

## 03. Education Indicators

### [03_fetch_opri.py](./03_fetch_opri.py)
Streams the UNESCO UIS OPRI (Education Operational Risk Indicators) bulk dataset and filters for key metrics.
- **Output**: `data/raw/opri/opri_{ISO3}.csv` (one file per country)
- **Features**: Processes enrolment rates, out-of-school rates, and survival rates for the period 2000–2023.

---

## 04. Geographic Boundaries

### [04_fetch_boundaries.py](./04_fetch_boundaries.py)
Downloads Administrative Level 1 and 2 boundaries (GeoJSON) from OCHA HDX.
- **Output**: `data/raw/boundaries/{ISO3}_admin1.geojson` and `admin2.geojson`
- **Usage**: `python3 scripts/04_fetch_boundaries.py BFA MLI NER` (Accepts ISO3 codes as arguments)

---

## 05. Analysis & Export

### [05_build_analysis.py](./05_build_analysis.py)
Merges conflict, education, and school data to perform spatial and statistical analysis.

### [06_export_map_data.py](./06_export_map_data.py)
Finalizes the data for visualization, exporting cleaned and formatted layers for the interactive map.

---

## Utilities

### [geocode_admin.py](./geocode_admin.py)
A robust geocoder that resolves latitude and longitude for administrative names (Country, Admin1, Admin2) using the Nominatim (OpenStreetMap) API.
- **Input**: `.csv` or `.xlsx` files containing administrative name columns.
- **Output**: A new geocoded file (default: `*_geocoded.csv`) with added `latitude` and `longitude` columns.
- **Features**: 
    - **Deduplication**: Only unique location combinations are queried to save time and API quota.
    - **Fallback Logic**: Tries Admin2+Admin1+Country → Admin2+Country → Admin1+Country to maximize resolution.
    - **Caching**: Saves results to a JSON cache file so identical locations are never queried twice.
    - **Rate Limiting**: Automatically respects API terms of service (1 request per second).

---

## Orchestration

### [run_all.py](./run_all.py)
The master script that orchestrates the execution of the entire pipeline in the correct order.
