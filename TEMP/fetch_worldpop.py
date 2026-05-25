"""
worldpop_fetch.py
=================
Fetches WorldPop "Global per country 2000-2020" population density GeoTIFFs
via the WorldPop REST API, downsamples them to a web-friendly resolution,
and exports one compact JSON per year suitable for Leaflet heatmaps / tile overlays.

Data source : WorldPop (www.worldpop.org) — CC-BY 4.0
API root    : https://www.worldpop.org/rest/data/pop/wpgp?iso3={ISO3}
File mirror : https://data.worldpop.org/GIS/Population/Global_2000_2020/{YEAR}/{ISO3}/

Pipeline
--------
1. Query WorldPop API → resolve download URL for each (country, year)
2. Download GeoTIFF  → stored in ./tifs/
3. Downsample raster → ~5 km grid (from native ~100 m) using block-mean resampling
4. Export JSON       → [[lat, lon, pop_per_km2], ...] per year
5. Write index.json  → manifest consumed by the Leaflet map

Usage
-----
    pip install requests rasterio numpy tqdm
    python worldpop_fetch.py

Output
------
    output/
        pop_2005.json  …  pop_2015.json   ← heatmap data arrays
        index.json                         ← metadata / year list
"""

import os
import json
import math
import time
import requests
import numpy as np
import rasterio
import argparse
from typing import Optional
from rasterio.enums import Resampling
from tqdm import tqdm

# ── Configuration ──────────────────────────────────────────────────────────────

# Years to fetch (WorldPop Global 2000-2020 covers every year)
YEARS = list(range(2000, 2021))

# Downsample factor — 50 means 50×50 native pixels → 1 output pixel
# Native resolution ≈ 100 m → factor 50 ≈ 5 km output grid
# Increase for faster/smaller output; decrease for finer detail
DOWNSAMPLE_FACTOR = 50

# Minimum population per output pixel to include (filters out near-zero cells)
MIN_POP = 1.0

# Where to cache raw TIFs
TIF_DIR = "tifs"
# Where to write JSON outputs
OUT_DIR = "output"

# WorldPop API + FTP mirror
API_BASE  = "https://www.worldpop.org/rest/data/pop/wpgp"
FTP_TPL   = "https://data.worldpop.org/GIS/Population/Global_2000_2020/{year}/{iso3}/{iso3_lower}_ppp_{year}.tif"
# Note: some files use _UNadj suffix — fallback handled below
FTP_ALT   = "https://data.worldpop.org/GIS/Population/Global_2000_2020/{year}/{iso3}/{iso3_lower}_ppp_{year}_UNadj.tif"

os.makedirs(TIF_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)


# ── Step 1: Resolve download URLs via WorldPop API ─────────────────────────────

def get_worldpop_url(iso3: str, year: int) -> Optional[str]:
    """
    Query the WorldPop REST API to get the canonical download URL
    for a given country-year. Falls back to the FTP mirror pattern
    if the API is slow or the record is missing.
    """
    try:
        resp = requests.get(
            API_BASE,
            params={"iso3": iso3},
            timeout=15
        )
        resp.raise_for_status()
        records = resp.json().get("data", [])
        for rec in records:
            if str(rec.get("popyear")) == str(year) or str(year) in str(rec.get("title", "")):
                files = rec.get("files", [])
                if files:
                    # API returns ftp:// — convert to https://
                    url = files[0].replace(
                        "ftp://ftp.worldpop.org.uk",
                        "https://data.worldpop.org"
                    )
                    return url
    except Exception as e:
        print(f"  API lookup failed for {iso3}/{year}: {e} — using mirror URL")

    # Fallback: construct URL directly from known pattern
    return FTP_TPL.format(
        year=year,
        iso3=iso3,
        iso3_lower=iso3.lower()
    )


# ── Step 2: Download TIF with resume support ───────────────────────────────────

def download_tif(url: str, dest_path: str) -> bool:
    """Download a file with progress bar. Returns True on success."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 100_000:
        return True  # already cached

    # Try primary URL; if 404, try UNadj variant
    for attempt_url in [url, url.replace(".tif", "_UNadj.tif")]:
        try:
            with requests.get(attempt_url, stream=True, timeout=60) as r:
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                with open(dest_path, "wb") as f, tqdm(
                    desc=f"  ↓ {os.path.basename(dest_path)}",
                    total=total, unit="B", unit_scale=True, leave=False
                ) as bar:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        bar.update(len(chunk))
            return True
        except Exception as e:
            print(f"    Warning: {attempt_url} → {e}")

    print(f"  ✗ Could not download {os.path.basename(dest_path)}")
    return False


# ── Step 3: Downsample raster and extract point array ─────────────────────────

def tif_to_points(tif_path: str, factor: int = DOWNSAMPLE_FACTOR) -> list[list]:
    """
    Read a GeoTIFF, downsample by `factor`, and return a list of
    [lat, lon, population] rows for cells where population >= MIN_POP.

    The downsampling uses Sum resampling so population counts are
    preserved (not averaged), then we convert to people/km².
    """
    points = []
    try:
        with rasterio.open(tif_path) as src:
            # Calculate downsampled dimensions
            new_h = max(1, src.height // factor)
            new_w = max(1, src.width  // factor)

            # Read + resample in one shot (Sum = aggregate population counts)
            data = src.read(
                1,
                out_shape=(1, new_h, new_w),
                resampling=Resampling.sum,
            )

            # Pixel area at output resolution in km²
            # Native pixel ≈ (res_x * factor) degrees wide
            res_lon = abs(src.transform.a) * factor   # degrees lon per output pixel
            res_lat = abs(src.transform.e) * factor   # degrees lat per output pixel
            # Approximate km² at mean latitude of raster
            mid_lat  = (src.bounds.top + src.bounds.bottom) / 2
            km_per_deg_lat = 111.32
            km_per_deg_lon = 111.32 * math.cos(math.radians(mid_lat))
            pixel_area_km2 = res_lon * km_per_deg_lon * res_lat * km_per_deg_lat

            # Build affine transform for the downsampled grid
            transform = src.transform * src.transform.scale(
                src.width  / new_w,
                src.height / new_h
            )

            # nodata mask
            nodata = src.nodata if src.nodata is not None else -99999

            for row_i in range(new_h):
                for col_i in range(new_w):
                    val = data[0, row_i, col_i]
                    if val is None or val == nodata or np.isnan(val) or val < MIN_POP:
                        continue
                    # Pixel centre coordinates
                    lon, lat = rasterio.transform.xy(
                        transform, row_i, col_i, offset="center"
                    )
                    pop_km2 = round(float(val) / pixel_area_km2, 1)
                    points.append([round(lat, 4), round(lon, 4), pop_km2])

    except Exception as e:
        print(f"  ✗ Error processing {tif_path}: {e}")

    return points


# ── Step 4: Per-year aggregation ───────────────────────────────────────────────

def merge_points(all_points: list[list]) -> list[list]:
    """
    Merge overlapping grid cells from different countries
    by summing population values at the same (lat, lon) bin.
    Rounds coordinates to 4 decimal places to snap overlapping borders.
    """
    grid: dict[tuple, float] = {}
    for lat, lon, pop in all_points:
        key = (lat, lon)
        grid[key] = grid.get(key, 0) + pop
    return [[lat, lon, round(pop, 1)] for (lat, lon), pop in grid.items()]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch WorldPop data for a specific country.")
    parser.add_argument("iso3", help="ISO3 country code (e.g., BFA)")
    args = parser.parse_args()
    iso3 = args.iso3.upper()
    
    print(f"WorldPop fetcher | Country: {iso3} | {len(YEARS)} years\n")

    index = {
        "years":       YEARS,
        "country":     iso3,
        "description": "Population density (people/km²) per ~5km grid cell",
        "source":      "WorldPop Global per country 2000-2020 (CC-BY 4.0)",
        "files":       {}
    }

    for year in YEARS:
        print(f"\n{'='*60}")
        print(f" Year: {year}")
        print(f"{'='*60}")

        tif_name = f"{iso3.lower()}_ppp_{year}.tif"
        tif_path = os.path.join(TIF_DIR, tif_name)

        # 1. Resolve URL
        url = get_worldpop_url(iso3, year)

        # 2. Download
        ok = download_tif(url, tif_path)
        if not ok:
            continue

        # 3. Extract points
        pts = tif_to_points(tif_path)
        print(f"  {iso3}: {len(pts):,} grid cells")
        
        # 4. Write output JSON
        out_name = f"{iso3.lower()}_pop_{year}.json"
        out_path = os.path.join(OUT_DIR, out_name)
        with open(out_path, "w") as f:
            json.dump({
                "year":   year,
                "count":  len(pts),
                "unit":   "people_per_km2",
                "data":   pts
            }, f, separators=(",", ":"))

        size_mb = os.path.getsize(out_path) / 1e6
        print(f"\n  ✓ Saved {out_name}  ({len(pts):,} cells, {size_mb:.1f} MB)")
        index["files"][str(year)] = out_name

    # Write manifest
    manifest_path = os.path.join(OUT_DIR, f"{iso3.lower()}_index.json")
    with open(manifest_path, "w") as f:
        json.dump(index, f, indent=2)

    print(f"\n✅ Done. Outputs in ./{OUT_DIR}/")
    print(f"   {iso3.lower()}_index.json + {len(YEARS)} files")