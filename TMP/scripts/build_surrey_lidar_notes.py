#!/usr/bin/env python3
"""Write Surrey LiDAR canopy-height integration plan (no bulk download)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"

PLAN = """# Surrey LiDAR Canopy Height Plan

City of Surrey **2022 LiDAR** is the best free structural vegetation source for the municipal AOI. Provincial LidarBC coverage is sparse in built-up Surrey.

## Sources

| Dataset | URL | Licence |
| --- | --- | --- |
| Raw LiDAR 2022 | https://data.surrey.ca/dataset/raw-lidar-data | Open Government Licence |
| Elevation grid 2022 | https://data.surrey.ca/dataset/elevation-grid-2022 | Open Government Licence |
| Bulk request | https://www.surrey.ca/services-payments/online-services/open-data/bulk-data | ≥750 GB via gis@surrey.ca |

## Recommended PoC workflow

1. **Sample tiles only** — intersect `data/demo/surrey_transmission_buffer_200m.geojson` with Surrey tile index; download 2–4 LAS/LAZ tiles covering forested ROW segments (Green Timbers, riparian buffers).
2. **Canopy height raster** — `canopy_height = max(0, DSM - DEM)` per 1 m cell; aggregate **mean** and **p95** inside corridor buffer.
3. **Write column** — `lidar_canopy_height_mean_m` in `data/processed/surrey_free_data_corridor_summary.csv`.
4. **Validation** — compare against BC VRI `HEIGHT` where polygons intersect; expect VRI gaps in urban Surrey.

## Processing notes

- Use PDAL or `laspy` + `rasterio` for DSM/DEM generation from sample tiles.
- Exclude buildings via City open data building footprints or height threshold (>45 m) as QA only.
- Do **not** commit `.las`/`.laz` to git — store under `data/raw/surrey/lidar/` (gitignored).

## Demo integration

When `lidar_canopy_height_mean_m` is populated, `build_surrey_free_data_summary.py` feeds `canopy_exposure_score` alongside WorldCover tree fraction and VRI height.

## Status

**Not executed in automated pipeline** — manual sample download required. Pipeline writes `lidar_canopy_height_mean_m=null` with `data_status` notes until sample tiles are processed.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write Surrey LiDAR canopy height plan.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DOCS_DIR / "surrey_lidar_canopy_height_plan.md",
        help="Output markdown path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(PLAN, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
