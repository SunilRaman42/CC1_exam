# OPRI (UNESCO UIS) Data

This folder contains education indicator data from the UNESCO Institute for Statistics (UIS) Education Operational Risk Indicator (OPRI) dataset.

## Generating Script
- `scripts/02_fetch_opri.py`: This script streams the bulk OPRI CSV file, filters it for core education indicators (e.g., enrolment, out-of-school rates, survival rates) and the target year range (2000–2023), and exports a separate file for every country found in the dataset.

## File Features
- **Format**: `.csv`
- **Granularity**: One file per country (e.g., `opri_BFA.csv`).
- **Indicators**: Includes key metrics such as Net Enrolment Rate (primary/secondary), Out-of-School Rate, and Survival Rates (total/female/male).

## Notes
- Files are generated programmatically by filtering the full UIS bulk dataset.
