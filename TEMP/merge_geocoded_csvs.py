import pandas as pd
import os
import argparse

def merge_csvs(input_dir, output_file):
    print(f"--- Starting merge process for files in: {input_dir} ---")
    
    # List all files in the input directory
    try:
        all_files = os.listdir(input_dir)
        csv_files = [f for f in all_files if f.endswith('.csv')]
        csv_files.sort() # Ensure consistent order
    except FileNotFoundError:
        print(f"Error: Directory not found - {input_dir}")
        return

    if not csv_files:
        print("No CSV files found to merge.")
        return

    print(f"Found {len(csv_files)} files to merge.")

    dataframes = []
    total_rows = 0

    for filename in csv_files:
        filepath = os.path.join(input_dir, filename)
        try:
            # Read the CSV file. Use latin1 encoding as seen in previous geocoding scripts.
            df = pd.read_csv(filepath, encoding='latin1')
            dataframes.append(df)
            rows = len(df)
            total_rows += rows
            print(f"  - Merged: {filename} ({rows:,} rows)")
        except Exception as e:
            print(f"  - Error reading {filename}: {e}")

    if not dataframes:
        print("No valid data was merged.")
        return

    # Concatenate all DataFrames
    print("\nConcatenating data...")
    merged_df = pd.concat(dataframes, ignore_index=True)

    # Save to the output CSV file
    print(f"Saving merged data to: {output_file}")
    try:
        merged_df.to_csv(output_file, index=False)
        print(f"\n--- Merge Complete! ---")
        print(f"Total rows in merged file: {len(merged_df):,}")
    except Exception as e:
        print(f"Error saving merged file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge individual CSV files into a single CSV.")
    parser.add_argument("input_dir", help="Directory containing individual CSV files")
    parser.add_argument("output_file", help="Path for the output merged CSV file")
    
    args = parser.parse_args()
    
    merge_csvs(args.input_dir, args.output_file)
