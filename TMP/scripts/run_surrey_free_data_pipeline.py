#!/usr/bin/env python3
"""Run Surrey open/free data pipeline stages."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

STAGES = [
    ("static_landcover", "build_surrey_static_landcover.py"),
    ("sentinel2", "build_surrey_sentinel2_indices.py"),
    ("environmental_stress", "build_surrey_environmental_stress.py"),
    ("vri", "build_surrey_vri_stats.py"),
    ("terrain", "build_surrey_terrain_stats.py"),
    ("lidar_notes", "build_surrey_lidar_notes.py"),
    ("summary", "build_surrey_free_data_summary.py"),
]

STATIC_ONLY = {"static_landcover", "summary", "lidar_notes"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Surrey free/open data pipeline.")
    parser.add_argument("--static-only", action="store_true", help="Run WorldCover + summary only")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    return parser.parse_args()


def run_stage(python: str, script: str) -> int:
    path = SCRIPT_DIR / script
    print(f"\n=== {script} ===")
    result = subprocess.run([python, str(path)], cwd=str(PROJECT_ROOT), check=False)
    return int(result.returncode)


def main() -> int:
    args = parse_args()
    exit_code = 0
    for name, script in STAGES:
        if args.static_only and name not in STATIC_ONLY:
            print(f"Skipping {name} (--static-only)")
            continue
        code = run_stage(args.python, script)
        if code != 0:
            print(f"Warning: {script} exited {code} — continuing")
            exit_code = max(exit_code, code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
