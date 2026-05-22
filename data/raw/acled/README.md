# ACLED Data

This folder contains aggregated conflict event data sourced from the Humanitarian Data Exchange (HDX).

## Generating Script
- `scripts/01_fetch_acled_hdx.py`: This script fetches the latest version of the "Political Violence Events and Fatalities" dataset via the HDX API.

## File Features
- **Format**: `.xlsx` (Excel Workbook)
- **Contents**: The dataset is organized into multiple sheets (`TOU`, `Non_HRP`, `HRP_1`, `HRP_2`), providing varying levels of granularity for conflict events and fatalities.
- **Update Frequency**: The script pulls the most recent snapshot available on HDX.

## Notes
- This data is aggregated; for granular, row-by-row event data, please consult the ACLED website.
- The `scripts/01_fetch_acled_hdx.py` script includes an automatic integrity check to ensure files are downloaded correctly.
