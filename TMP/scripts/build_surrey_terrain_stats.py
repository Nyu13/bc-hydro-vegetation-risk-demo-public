#!/usr/bin/env python3
"""Terrain slope stats for Surrey corridor (BC CDED / Copernicus DEM fallback stub)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _surrey_pipeline_common import (  # noqa: E402
    DEFAULT_AOI,
    DEFAULT_OUT_DIR,
    DEFAULT_RAW_DIR,
    load_aoi,
    stub_row,
    today_iso,
    try_download_file,
    write_csv,
)

# Copernicus DEM 30m global mosaic — lightweight open fallback for slope proxy
COP30_SLOPE_STUB_URL = (
    "https://portal.opentopography.org/API/globaldem"
    "?demtype=COP30&south=49.0&north=49.35&west=-123.1&east=-122.6&outputFormat=GTiff"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Surrey terrain slope corridor stats.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--dem-raster", type=Path, default=None, help="Local DEM GeoTIFF (meters)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def compute_mean_slope_deg(dem_path: Path, aoi) -> tuple[float | None, str, str]:
    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask
    except ImportError as exc:
        return None, "stub_missing_deps", str(exc)

    if not dem_path.is_file():
        return None, "stub_missing_raster", f"DEM not found: {dem_path}"

    try:
        aoi_proj = aoi.to_crs("EPSG:4326")
        with rasterio.open(dem_path) as src:
            shapes = [g.__geo_interface__ for g in aoi_proj.to_crs(src.crs).geometry if g is not None]
            out_image, out_transform = mask(src, shapes, crop=True, all_touched=True)
            elev = out_image[0].astype("float64")
            nodata = src.nodata
            if nodata is not None:
                elev[elev == nodata] = np.nan

            cell_x, cell_y = abs(out_transform.a), abs(out_transform.e)
            dy, dx = np.gradient(elev, cell_y, cell_x)
            slope_rad = np.arctan(np.sqrt(dx * dx + dy * dy))
            slope_deg = np.degrees(slope_rad)
            valid = slope_deg[np.isfinite(slope_deg)]
            if valid.size == 0:
                return None, "stub_no_valid_pixels", "No valid DEM pixels under AOI"
            return round(float(valid.mean()), 2), "open_free_processed", f"Mean slope from {dem_path.name}"
    except Exception as exc:  # noqa: BLE001
        return None, "stub_processing_error", str(exc)


def try_fetch_dem() -> tuple[Path | None, str]:
    dest = DEFAULT_RAW_DIR / "dem" / "surrey_cop30_dem.tif"
    ok, detail = try_download_file(COP30_SLOPE_STUB_URL, dest, timeout=180)
    if ok:
        return dest, detail
    return None, (
        f"{detail}. Download BC CDED 25 m from "
        "https://open.canada.ca/data/en/dataset/7b4fef7e-7cae-4379-97b8-62b03e9ac83d "
        f"to {dest.parent} and pass --dem-raster."
    )


def main() -> int:
    args = parse_args()
    aoi, aoi_id = load_aoi(args.aoi)

    dem_path = args.dem_raster if args.dem_raster and args.dem_raster.is_file() else None
    detail = ""
    if dem_path is None:
        default_dem = DEFAULT_RAW_DIR / "dem" / "surrey_cop30_dem.tif"
        if default_dem.is_file():
            dem_path = default_dem
        else:
            dem_path, detail = try_fetch_dem()

    slope, status, msg = compute_mean_slope_deg(dem_path, aoi) if dem_path else (None, "stub_missing_raster", detail)

    if slope is None:
        row = stub_row(
            aoi_id=aoi_id,
            layer="terrain_slope",
            data_status=status,
            instructions=msg or detail,
            extra={"terrain_slope_mean_deg": None},
        )
    else:
        row = {
            "aoi_id": aoi_id,
            "layer": "terrain_slope",
            "data_status": status,
            "data_source": "open_free_v1",
            "as_of_date": today_iso(),
            "instructions": "",
            "terrain_slope_mean_deg": slope,
        }

    df = pd.DataFrame([row])
    out = args.out_dir / "surrey_terrain_corridor_stats.csv"
    write_csv(df, out)
    print(f"Wrote {out} (status={df['data_status'].iloc[0]}, slope={slope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
