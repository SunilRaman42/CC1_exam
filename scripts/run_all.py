"""
run_all.py
==========
Orchestrator — runs the full pipeline in order for a given country.

Usage:
    python run_all.py              # runs BFA (default)
    python run_all.py --iso3 MLI   # runs Mali
    python run_all.py --skip 1 2   # skip fetch steps (use existing raw data)

Steps:
    01  Fetch ACLED conflict events
    02  Fetch UNESCO OPRI education indicators
    03  Fetch OCHA admin boundaries
    04  Build vulnerability analysis
    05  Export map data (GeoJSON + JSON)
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


STEPS = {
    1: ("01_fetch_acled.py",        "Fetch ACLED conflict events"),
    2: ("02_fetch_opri.py",         "Fetch UNESCO OPRI indicators"),
    3: ("03_fetch_boundaries.py",   "Fetch OCHA admin boundaries"),
    4: ("04_build_analysis.py",     "Build vulnerability analysis"),
    5: ("05_export_map_data.py",    "Export map data (GeoJSON + JSON)"),
}


def run_step(script: str, iso3: str) -> bool:
    """Run a single pipeline step, injecting ISO3 if needed."""
    path = Path("scripts") / script
    if not path.exists():
        print(f"  ✗ Script not found: {path}")
        return False

    # Pass ISO3 as environment variable so scripts can pick it up
    import os
    env = os.environ.copy()
    env["PIPELINE_ISO3"] = iso3

    result = subprocess.run(
        [sys.executable, str(path)],
        env=env,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run the education risk pipeline")
    parser.add_argument("--iso3",   default="BFA",      help="ISO3 country code (default: BFA)")
    parser.add_argument("--skip",   nargs="*", type=int, default=[], help="Step numbers to skip")
    parser.add_argument("--only",   nargs="*", type=int, default=None, help="Run only these steps")
    args = parser.parse_args()

    iso3        = args.iso3.upper()
    skip_steps  = set(args.skip)
    only_steps  = set(args.only) if args.only else None

    print(f"\n{'='*55}")
    print(f"  Education Risk Pipeline — {iso3}")
    print(f"{'='*55}\n")

    failed = []
    for step_num, (script, label) in STEPS.items():
        if step_num in skip_steps:
            print(f"  [{step_num}/5] SKIP  {label}")
            continue
        if only_steps and step_num not in only_steps:
            print(f"  [{step_num}/5] SKIP  {label}")
            continue

        print(f"  [{step_num}/5] START {label}")
        t0 = time.time()
        ok = run_step(script, iso3)
        elapsed = time.time() - t0

        if ok:
            print(f"  [{step_num}/5] DONE  {label} ({elapsed:.0f}s)\n")
        else:
            print(f"  [{step_num}/5] FAIL  {label}\n")
            failed.append(step_num)
            # Steps 4 and 5 depend on earlier steps — abort on failure
            if step_num < 4:
                print("  Aborting — fix the error above and re-run")
                sys.exit(1)

    print(f"{'='*55}")
    if failed:
        print(f"  Pipeline finished with failures: steps {failed}")
        print(f"  Re-run failed steps with: python run_all.py --iso3 {iso3} --only {' '.join(map(str, failed))}")
    else:
        print(f"  ✅  Pipeline complete for {iso3}")
        print(f"\n  Outputs:")
        print(f"    data/clean/{iso3}_vulnerability.csv")
        print(f"    data/clean/{iso3}_national_trends.csv")
        print(f"    assets/data.geojson")
        print(f"    assets/trends.json")
        print(f"    assets/insights.json")
        print(f"\n  Next: open index.html or push to GitHub Pages")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
