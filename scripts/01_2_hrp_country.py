import pandas as pd
import os
import re
import json
import argparse

# Base directory for input CSVs (from step 01_1)
input_base_dir = 'data/raw/acled/split'
manifest_path = os.path.join(input_base_dir, 'manifest.json')
country_column = 'Country' # The column to group by

def sanitize_name(name):
    safe_name = re.sub(r'[^\w\s-]', '', str(name)).strip()
    safe_name = re.sub(r'[-\s]+', '_', safe_name)
    return safe_name if safe_name else f"name_{hash(name)}"

def process_csv(csv_filename, target_country=None):
    input_csv_path = os.path.join(input_base_dir, csv_filename)
    if not os.path.exists(input_csv_path):
        print(f"Error: {input_csv_path} not found.")
        return

    # Determine output directory based on input filename
    base_name = os.path.splitext(csv_filename)[0]
    output_base_dir = os.path.join('data/clean/acled', f"{base_name}_countries")
    os.makedirs(output_base_dir, exist_ok=True)

    try:
        print(f"Reading: {csv_filename}")
        df = pd.read_csv(input_csv_path)

        if country_column not in df.columns:
            print(f"  ! Error: Column '{country_column}' not found.")
            return

        if target_country:
            # Single country mode
            country_df = df[df[country_column] == target_country]
            if not country_df.empty:
                safe_name = sanitize_name(target_country)
                out_path = os.path.join(output_base_dir, f"{safe_name}.csv")
                country_df.to_csv(out_path, index=False)
                print(f"  ✓ Saved {target_country} to {out_path}")
        else:
            # Full group-by mode
            grouped = df.groupby(country_column)
            for country_name, country_df in grouped:
                safe_name = sanitize_name(country_name)
                out_path = os.path.join(output_base_dir, f"{safe_name}.csv")
                country_df.to_csv(out_path, index=False)
            print(f"  ✓ Split {len(grouped)} countries in {csv_filename}")

    except Exception as e:
        print(f"  ! Error processing {csv_filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split ACLED CSVs by country.")
    parser.add_argument("--country", "-c", help="Specific country to extract (e.g., 'Burkina Faso')")
    args = parser.parse_args()

    # Load manifest
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest not found at {manifest_path}. Run 01_1 first.")
        exit(1)

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    if args.country:
        # Target country mode
        if args.country in manifest:
            print(f"Processing '{args.country}' using manifest...")
            relevant_csvs = manifest[args.country]
            for csv_file in relevant_csvs:
                process_csv(csv_file, target_country=args.country)
        else:
            print(f"Error: Country '{args.country}' not found in manifest.")
    else:
        # Process everything
        print("No country specified. Processing all files in manifest...")
        # Get all unique CSVs from the manifest values
        all_csvs = sorted(list(set([csv for csv_list in manifest.values() for csv in csv_list])))
        for csv_file in all_csvs:
            process_csv(csv_file)

    print("\n✓ Operation complete.")
