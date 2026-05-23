import os
import sys # Needed to get the path to the current Python interpreter
import subprocess # To construct command strings, though not executing them

# --- Configuration ---
# Directory containing the HRP CSV files
HRP_DATA_DIR = "DATA/HRP_2_countries/"
# Path to the geocoding script
GEOCODER_SCRIPT = "30_04_playground/geocode_cities/geocode_admin.py"
# Directory to save the geocoded output files
OUTPUT_DIR = "DATA/HRP_2_countries_geocoded/"
# Shared cache file for all runs
CACHE_FILE = os.path.join(OUTPUT_DIR, "shared_geocode_cache.json")

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Column Name Configuration ---
# IMPORTANT: These column names are placeholders and might need adjustment.
# If your CSV files use different names for Country, Admin1, or Admin2,
# you will need to modify these variables or pass them via command-line arguments.
# Based on previous interactions, Admin1 and Admin2 columns are often missing or
# need explicit definition. Set to None to rely on auto-detection.
COUNTRY_COL_NAME = None # e.g., "Country", "Nation", "ISO3"
ADMIN1_COL_NAME = None  # e.g., "State", "Province", "Governorate"
ADMIN2_COL_NAME = None  # e.g., "District", "City", "LGA", "County"

print("--- Geocoding Execution Script ---")
print(f"HRP Data Directory: {HRP_DATA_DIR}")
print(f"Geocoder Script: {GEOCODER_SCRIPT}")
print(f"Output Directory: {OUTPUT_DIR}")
print(f"Shared Cache File: {CACHE_FILE}")

print("IMPORTANT: This script will now EXECUTE the geocoding commands.")
print("Geocoding can take a significant amount of time due to API rate limits (1 request/sec).")
print("Ensure column names are correctly set above or will be auto-detected by the script.")

print("Note: If auto-detection fails for Admin1/Admin2, you will need to manually")
print("edit this script to set COUNTRY_COL_NAME, ADMIN1_COL_NAME, and ADMIN2_COL_NAME")
print("before running it again.")

# List all CSV files in the HRP_2_countries directory
try:
    hrp_files = [f for f in os.listdir(HRP_DATA_DIR) if f.endswith('.csv')]
    hrp_files.sort() # Process them alphabetically
except FileNotFoundError:
    print(f"Error: Directory not found - {HRP_DATA_DIR}")
    hrp_files = []

if not hrp_files:
    print("No CSV files found in the specified HRP_2_countries directory.")
else:
    print(f"Found {len(hrp_files)} CSV files. Executing geocoding for each:")

    for filename in hrp_files:
        input_filepath = os.path.join(HRP_DATA_DIR, filename)
        # Generate output filename, e.g., 'Nigeria_geocoded.csv'
        output_filename = filename.replace(".csv", "_geocoded.csv")
        output_filepath = os.path.join(OUTPUT_DIR, output_filename)

        print(f"--- Processing: {filename} ---")
        
        # Construct the command to run geocode_admin.py
        # Use sys.executable to ensure we use the same Python interpreter
        command_parts = [
            sys.executable,
            GEOCODER_SCRIPT,
            input_filepath,
            output_filepath,
            f"--cache={CACHE_FILE}" # Use a shared cache in the output dir
        ]

        # Add column overrides if specified
        if COUNTRY_COL_NAME:
            command_parts.append(f"--country-col={COUNTRY_COL_NAME}")
        if ADMIN1_COL_NAME:
            command_parts.append(f"--admin1-col={ADMIN1_COL_NAME}")
        if ADMIN2_COL_NAME:
            command_parts.append(f"--admin2-col={ADMIN2_COL_NAME}")
        
        # Execute the command (no --dry-run anymore)
        command_str = ' '.join(command_parts)
        print(f"Executing: {command_str}")
        
        try:
            # Run the command, capture output, check for errors
            result = subprocess.run(command_parts, check=True, capture_output=True, text=True)
            print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            print(f"Successfully geocoded {filename}")
        except FileNotFoundError:
            print(f"Error: Geocoder script not found at {GEOCODER_SCRIPT}. Please ensure it exists.")
            break # Stop if the script itself isn't found
        except subprocess.CalledProcessError as e:
            print(f"Error executing geocoding for {filename}:")
            print("STDOUT:", e.stdout)
            print("STDERR:", e.stderr)
            print(f"Exit code: {e.returncode}")
            # Decide whether to continue or stop on error.
            # If critical error (like missing columns), it might be better to stop.
            # We'll print the error and continue with the next file.
        except Exception as e:
            print(f"An unexpected error occurred while processing {filename}: {e}")
        
        print("-" * 50)

    print("--- Geocoding process finished. ---")
    print(f"Check '{OUTPUT_DIR}' for geocoded CSV files.")
