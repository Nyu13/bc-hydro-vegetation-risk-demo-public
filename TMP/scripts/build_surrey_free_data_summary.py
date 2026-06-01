#!/usr/bin/env python3
"""Merge Surrey open/free pipeline outputs into corridor summary CSV with demo scores."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _surrey_pipeline_common import DEFAULT_AOI, DEFAULT_OUT_DIR, load_aoi, today_iso, write_csv  # noqa: E402
from src.risk_scoring import (  # noqa: E402
    compute_free_data_canopy_exposure_score,
    compute_free_data_terrain_access_score,
    compute_free_data_vegetation_dryness_score,
    compute_free_data_vegetation_exposure_score,
)


SUMMARY_COLUMNS = [
    "aoi_id",
    "worldcover_tree_pct",
    "worldcover_shrub_grass_pct",
    "worldcover_built_pct",
    "worldcover_bare_pct",
    "nalcms_forest_pct",
    "sentinel2_ndvi_mean",
    "sentinel2_ndmi_mean",
    "sentinel2_ndvi_change",
    "cloud_filtered_pct",
    "scenes_used",
    "tiles_used",
    "vegetation_change_score",
    "modis_lst_day_mean_c",
    "era5_soil_moisture_anomaly",
    "vri_mean_crown_closure",
    "vri_mean_height_m",
    "lidar_canopy_height_mean_m",
    "terrain_slope_mean_deg",
    "vegetation_exposure_score",
    "canopy_exposure_score",
    "vegetation_dryness_score",
    "heat_drought_stress_score",
    "environmental_stress_notes",
    "terrain_access_score",
    "data_source",
    "data_status",
    "as_of_date",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge Surrey free-data layer CSVs into summary.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--in-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def _read_layer(path: Path) -> pd.Series:
    if not path.is_file():
        return pd.Series(dtype=object)
    df = pd.read_csv(path)
    if df.empty:
        return pd.Series(dtype=object)
    return df.iloc[0]


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def vegetation_change_from_ndvi_delta(ndvi_change: float | None) -> float | None:
    """Map Sentinel-2 NDVI delta to 0–100 change score (magnitude of shift)."""
    if ndvi_change is None or pd.isna(ndvi_change):
        return None
    return round(float(np.clip(abs(float(ndvi_change)) / 0.3 * 100.0, 0, 100)), 2)


def merge_layers(in_dir: Path, aoi_id: str) -> dict[str, object]:
    wc = _read_layer(in_dir / "surrey_worldcover_corridor_stats.csv")
    nalcms = _read_layer(in_dir / "surrey_nalcms_corridor_stats.csv")
    s2 = _read_layer(in_dir / "surrey_sentinel2_corridor_stats.csv")
    stress = _read_layer(in_dir / "surrey_eccc_weather_stress_stats.csv")
    vri = _read_layer(in_dir / "surrey_vri_corridor_stats.csv")
    terrain = _read_layer(in_dir / "surrey_terrain_corridor_stats.csv")

    ndvi_change = _float_or_none(s2.get("sentinel2_ndvi_change"))

    row: dict[str, object] = {
        "aoi_id": aoi_id,
        "worldcover_tree_pct": _float_or_none(wc.get("worldcover_tree_pct")),
        "worldcover_shrub_grass_pct": _float_or_none(wc.get("worldcover_shrub_grass_pct")),
        "worldcover_built_pct": _float_or_none(wc.get("worldcover_built_pct")),
        "worldcover_bare_pct": _float_or_none(wc.get("worldcover_bare_pct")),
        "nalcms_forest_pct": _float_or_none(nalcms.get("nalcms_forest_pct")),
        "sentinel2_ndvi_mean": _float_or_none(s2.get("sentinel2_ndvi_mean")),
        "sentinel2_ndmi_mean": _float_or_none(s2.get("sentinel2_ndmi_mean")),
        "sentinel2_ndvi_change": ndvi_change,
        "cloud_filtered_pct": _float_or_none(s2.get("cloud_filtered_pct")),
        "scenes_used": _int_or_none(s2.get("scenes_used")),
        "tiles_used": str(s2.get("tiles_used", "") or ""),
        "vegetation_change_score": vegetation_change_from_ndvi_delta(ndvi_change),
        "modis_lst_day_mean_c": None,
        "era5_soil_moisture_anomaly": None,
        "vri_mean_crown_closure": _float_or_none(vri.get("vri_mean_crown_closure")),
        "vri_mean_height_m": _float_or_none(vri.get("vri_mean_height_m")),
        "lidar_canopy_height_mean_m": None,
        "terrain_slope_mean_deg": _float_or_none(terrain.get("terrain_slope_mean_deg")),
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
    }

    statuses = [
        str(wc.get("data_status", "")),
        str(nalcms.get("data_status", "")),
        str(s2.get("data_status", "")),
        str(stress.get("data_status", "")),
        str(vri.get("data_status", "")),
        str(terrain.get("data_status", "")),
    ]
    if any(s == "open_free_processed" for s in statuses):
        row["data_status"] = "open_free_processed"
    else:
        row["data_status"] = "stub_pipeline"

    row["vegetation_exposure_score"] = compute_free_data_vegetation_exposure_score(
        worldcover_tree_pct=row["worldcover_tree_pct"],
        nalcms_forest_pct=row["nalcms_forest_pct"],
        vri_mean_crown_closure=row["vri_mean_crown_closure"],
    )
    row["canopy_exposure_score"] = compute_free_data_canopy_exposure_score(
        worldcover_tree_pct=row["worldcover_tree_pct"],
        vri_mean_height_m=row["vri_mean_height_m"],
        lidar_canopy_height_mean_m=row["lidar_canopy_height_mean_m"],
    )
    row["vegetation_dryness_score"] = compute_free_data_vegetation_dryness_score(
        sentinel2_ndmi_mean=row["sentinel2_ndmi_mean"],
        era5_soil_moisture_anomaly=row["era5_soil_moisture_anomaly"],
    )
    row["heat_drought_stress_score"] = _float_or_none(stress.get("eccc_weather_stress_score"))
    row["environmental_stress_notes"] = str(stress.get("notes", "") or "").strip() or (
        "ECCC atmospheric weather stress proxy (wind, precipitation, air temperature, short-term dryness). "
        "Not satellite land surface temperature or soil water content."
    )
    row["terrain_access_score"] = compute_free_data_terrain_access_score(
        terrain_slope_mean_deg=row["terrain_slope_mean_deg"],
    )
    return row


def main() -> int:
    args = parse_args()
    _, aoi_id = load_aoi(args.aoi)
    row = merge_layers(args.in_dir, aoi_id)
    df = pd.DataFrame([row], columns=SUMMARY_COLUMNS)
    out = args.out_dir / "surrey_free_data_corridor_summary.csv"
    write_csv(df, out)
    print(f"Wrote {out} (data_status={row['data_status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
