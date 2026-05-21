"""
03_fetch_boundaries.py
======================
Downloads admin1 + admin2 boundaries from OCHA HDX for target countries.
Used to build the choropleth map layer.

Output: data/raw/boundaries/{ISO3}_admin1.geojson
        data/raw/boundaries/{ISO3}_admin2.geojson
"""

import requests, json, time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_COUNTRIES = {
    "BFA": "burkina-faso",   # HDX location slug
    # Add more: "MLI": "mali", "NER": "niger"
}

OUT_DIR = Path("data/raw/boundaries")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HDX_API  = "https://data.humdata.org/api/3/action"
HEADERS  = {"User-Agent": "education-risk-research/1.0"}

# Known COD boundary dataset slugs for admin boundaries
# Pattern: cod-ab-{location_slug}
COD_SLUG_PATTERN = "cod-ab-{slug}"


def find_boundary_resources(location_slug: str) -> list[dict]:
    """Search HDX for COD admin boundary resources for a country."""
    slug = COD_SLUG_PATTERN.format(slug=location_slug)
    r = requests.get(
        f"{HDX_API}/package_show",
        params={"id": slug},
        headers=HEADERS,
        timeout=15,
    )
    if r.status_code != 200:
        return []
    data = r.json()
    if not data.get("success"):
        return []
    return data["result"].get("resources", [])


def download_geojson(url: str, out_path: Path) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        # If it's a ZIP, extract the GeoJSON
        if "zip" in url.lower() or r.headers.get("Content-Type", "").startswith("application/zip"):
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                geojson_files = [n for n in z.namelist() if n.endswith(".geojson") or n.endswith(".json")]
                if geojson_files:
                    with z.open(geojson_files[0]) as f:
                        data = json.load(f)
                    with open(out_path, "w") as out:
                        json.dump(data, out)
                    return True
        else:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


if __name__ == "__main__":
    for iso3, slug in TARGET_COUNTRIES.items():
        print(f"\n[{iso3}] Fetching boundaries...")
        resources = find_boundary_resources(slug)

        if not resources:
            print(f"  ⚠ No COD dataset found for {iso3}")
            print(f"    Manual: https://data.humdata.org/dataset/cod-ab-{slug}")
            continue

        # Filter to admin1 and admin2 GeoJSON/Shapefile resources
        for res in resources:
            name = res.get("name", "").lower()
            url  = res.get("url", "")
            fmt  = res.get("format", "").lower()

            if "adm1" in name and ("geojson" in fmt or "geojson" in url.lower()):
                out = OUT_DIR / f"{iso3}_admin1.geojson"
                ok  = download_geojson(url, out)
                print(f"  Admin1: {'✓' if ok else '✗'} → {out}")

            elif "adm2" in name and ("geojson" in fmt or "geojson" in url.lower()):
                out = OUT_DIR / f"{iso3}_admin2.geojson"
                ok  = download_geojson(url, out)
                print(f"  Admin2: {'✓' if ok else '✗'} → {out}")

        time.sleep(0.5)

    print("\n✓ Boundary fetch complete")
    print("  If files are missing, download manually from:")
    print("  https://data.humdata.org/dataset/cod-ab-{country-slug}")
