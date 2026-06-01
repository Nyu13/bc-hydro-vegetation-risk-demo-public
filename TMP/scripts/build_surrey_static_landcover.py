#!/usr/bin/env python3
"""Zonal land-cover stats for Surrey transmission corridor buffer (WorldCover + NALCMS)."""

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
    NALCMS_FOREST_CLASSES,
    WORLDCOVER_BARE,
    WORLDCOVER_BUILT,
    WORLDCOVER_GRASS,
    WORLDCOVER_SHRUB,
    WORLDCOVER_TREE,
    load_aoi,
    stub_row,
    surrey_worldcover_tile_name,
    today_iso,
    try_download_file,
    worldcover_download_url_for_tile,
    worldcover_tile_for_aoi,
    write_csv,
    zonal_class_percentages,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Surrey static land-cover corridor stats.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI, help="Corridor buffer GeoJSON")
    parser.add_argument("--worldcover-raster", type=Path, default=None, help="Local WorldCover GeoTIFF")
    parser.add_argument("--nalcms-raster", type=Path, default=None, help="Local NALCMS GeoTIFF")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Processed CSV output dir")
    return parser.parse_args()


def resolve_worldcover_raster(args: argparse.Namespace, aoi_gdf) -> tuple[Path | None, str]:
    if args.worldcover_raster and args.worldcover_raster.is_file():
        return args.worldcover_raster, f"Using provided WorldCover raster: {args.worldcover_raster}"

    tile = surrey_worldcover_tile_name()
    cached = DEFAULT_RAW_DIR / "worldcover" / f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    if cached.is_file():
        return cached, f"Using cached WorldCover raster: {cached}"

    tile = worldcover_tile_for_aoi(aoi_gdf)
    cached = DEFAULT_RAW_DIR / "worldcover" / f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    if cached.is_file():
        return cached, f"Using cached WorldCover raster: {cached}"

    url = worldcover_download_url_for_tile(tile)
    ok, detail = try_download_file(url, cached, timeout=900)
    if ok:
        return cached, detail
    return None, (
        f"{detail}. Manual: download {url} to {cached} "
        "(or pass --worldcover-raster). See docs/free_data_pipeline_runbook.md."
    )


def build_worldcover_stats(aoi_path: Path, raster_path: Path | None, detail: str) -> pd.DataFrame:
    aoi, aoi_id = load_aoi(aoi_path)
    if raster_path is None:
        row = stub_row(
            aoi_id=aoi_id,
            layer="worldcover_2021",
            data_status="stub_missing_raster",
            instructions=detail,
            extra={
                "worldcover_tree_pct": None,
                "worldcover_shrub_grass_pct": None,
                "worldcover_built_pct": None,
                "worldcover_bare_pct": None,
            },
        )
        return pd.DataFrame([row])

    pct, status, msg = zonal_class_percentages(
        raster_path,
        aoi,
        class_map={
            "worldcover_tree_pct": {WORLDCOVER_TREE},
            "worldcover_shrub_grass_pct": {WORLDCOVER_SHRUB, WORLDCOVER_GRASS},
            "worldcover_built_pct": {WORLDCOVER_BUILT},
            "worldcover_bare_pct": {WORLDCOVER_BARE},
        },
    )
    row = {
        "aoi_id": aoi_id,
        "layer": "worldcover_2021",
        "data_status": status,
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
        "instructions": msg if status != "open_free_processed" else "",
        **pct,
    }
    return pd.DataFrame([row])


def build_nalcms_stats(aoi_path: Path, raster_path: Path | None, detail: str) -> pd.DataFrame:
    aoi, aoi_id = load_aoi(aoi_path)
    if raster_path is None:
        row = stub_row(
            aoi_id=aoi_id,
            layer="nalcms_2020",
            data_status="stub_missing_raster",
            instructions=detail or (
                "Download NALCMS 2020 GeoTIFF from "
                "https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47 "
                f"to {DEFAULT_RAW_DIR / 'nalcms'} and pass --nalcms-raster."
            ),
            extra={"nalcms_forest_pct": None},
        )
        return pd.DataFrame([row])

    pct, status, msg = zonal_class_percentages(
        raster_path,
        aoi,
        class_map={"nalcms_forest_pct": NALCMS_FOREST_CLASSES},
    )
    row = {
        "aoi_id": aoi_id,
        "layer": "nalcms_2020",
        "data_status": status,
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
        "instructions": msg if status != "open_free_processed" else "",
        **pct,
    }
    return pd.DataFrame([row])


def main() -> int:
    args = parse_args()
    aoi_gdf, _ = load_aoi(args.aoi)

    wc_raster, wc_detail = resolve_worldcover_raster(args, aoi_gdf)
    if args.worldcover_raster:
        wc_raster = args.worldcover_raster if args.worldcover_raster.is_file() else wc_raster

    nalcms_raster = args.nalcms_raster if args.nalcms_raster and args.nalcms_raster.is_file() else None
    nalcms_detail = ""
    if nalcms_raster is None:
        default_nalcms = DEFAULT_RAW_DIR / "nalcms" / "nalcms_2020_bc.tif"
        if default_nalcms.is_file():
            nalcms_raster = default_nalcms
        else:
            nalcms_detail = (
                "NALCMS raster not bundled. Optional validation layer — "
                "download Canada LC 2020 and pass --nalcms-raster."
            )

    wc_df = build_worldcover_stats(args.aoi, wc_raster, wc_detail)
    nalcms_df = build_nalcms_stats(args.aoi, nalcms_raster, nalcms_detail)

    wc_out = args.out_dir / "surrey_worldcover_corridor_stats.csv"
    nalcms_out = args.out_dir / "surrey_nalcms_corridor_stats.csv"
    write_csv(wc_df, wc_out)
    write_csv(nalcms_df, nalcms_out)

    print(f"Wrote {wc_out} (status={wc_df['data_status'].iloc[0]})")
    print(f"Wrote {nalcms_out} (status={nalcms_df['data_status'].iloc[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
