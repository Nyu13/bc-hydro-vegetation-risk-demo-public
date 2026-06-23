#!/usr/bin/env python3
"""Sentinel-2 NDVI/NDMI stats aggregated per Okanagan corridor segment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    OKANAGAN_PROCESSED_DIR,
    discover_sentinel2_dirs,
    load_okanagan_segments,
    today_iso,
    write_csv,
)
from _sentinel2_pipeline_common import (  # noqa: E402
    STUB_STATUS,
    _aggregate_scene_stats,
    _process_safe_scene,
    _scene_qa_rows,
    discover_safe_products,
)

OKANAGAN_MANUAL_NOTES = (
    "No local Sentinel-2 inputs found. Download S2 L2A .SAFE or .zip products to "
    "data/raw/okanagan/L2A/ or data/raw/okanagan/sentinel2/ (gitignored). "
    "See docs/sentinel2_manual_download_notes.md. Example: "
    "python TMP/scripts/build_okanagan_sentinel2_indices.py "
    '--safe-dir "data/raw/okanagan/L2A"'
)

SCENE_QA_OUT = OKANAGAN_PROCESSED_DIR / "okanagan_sentinel2_scene_qa.csv"
CORRIDOR_STATS_OUT = OKANAGAN_PROCESSED_DIR / "okanagan_sentinel2_corridor_stats.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    parser.add_argument("--safe-dir", type=Path, default=None, help="Override SAFE scan directory")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def _segment_stats_from_scenes(segments: gpd.GeoDataFrame, scenes_ok: list) -> pd.DataFrame:
    """Apply corridor-wide scene stats to each segment (demo: uniform per scene composite)."""
    agg = _aggregate_scene_stats(scenes_ok, period_start=None, period_end=None)
    rows = []
    for _, seg in segments.iterrows():
        rows.append(
            {
                "corridor_id": seg.get("corridor_id"),
                "segment_id": seg.get("segment_id"),
                "region": seg.get("region"),
                "length_km": seg.get("length_km"),
                "sentinel2_ndvi_mean": agg.get("sentinel2_ndvi_mean"),
                "sentinel2_ndmi_mean": agg.get("sentinel2_ndmi_mean"),
                "sentinel2_ndvi_change": agg.get("sentinel2_ndvi_change"),
                "sentinel2_ndmi_change": agg.get("sentinel2_ndmi_change"),
                "cloud_filtered_pct": agg.get("cloud_filtered_pct"),
                "scenes_used": agg.get("scenes_used"),
                "tiles_used": agg.get("tiles_used"),
                "period_start": agg.get("period_start"),
                "period_end": agg.get("period_end"),
                "data_status": "open_free_processed",
                "data_source": "Sentinel-2 L2A (local SAFE)",
                "as_of_date": today_iso(),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments)

    safe_dirs = discover_sentinel2_dirs()
    if args.safe_dir is not None:
        safe_dirs = [args.safe_dir]

    products = []
    temp_dirs = []
    for safe_dir in safe_dirs:
        found, temps = discover_safe_products(safe_dir)
        products.extend(found)
        temp_dirs.extend(temps)

    if not products:
        msg = (
            "No Sentinel-2 SAFE or zip products found. Place L2A products under "
            "data/raw/okanagan/L2A/ or data/raw/okanagan/sentinel2/. "
            f"{OKANAGAN_MANUAL_NOTES}"
        )
        print(f"WARNING: {msg}")
        stub = pd.DataFrame(
            [
                {
                    "corridor_id": "ALL",
                    "segment_id": "ALL",
                    "region": segments.iloc[0].get("region"),
                    "data_status": STUB_STATUS,
                    "data_source": "open_free_v1",
                    "instructions": msg,
                    "as_of_date": today_iso(),
                }
            ]
        )
        write_csv(stub, CORRIDOR_STATS_OUT)
        write_csv(pd.DataFrame(columns=["scene_id", "status"]), SCENE_QA_OUT)
        print(f"Wrote stub {CORRIDOR_STATS_OUT}")
        return 0

    buffer_union = segments.to_crs(4326).union_all()
    aoi_gdf = gpd.GeoDataFrame(geometry=[buffer_union], crs="EPSG:4326")

    scenes = []
    for product in products:
        scenes.append(_process_safe_scene(product, aoi_gdf))

    qa_rows = _scene_qa_rows(scenes, "okanagan_corridor")
    write_csv(pd.DataFrame(qa_rows), SCENE_QA_OUT)

    ok_scenes = [s for s in scenes if s.status == "processed"]
    if not ok_scenes:
        msg = f"Found {len(products)} SAFE product(s) but none produced clear AOI stats."
        stub = pd.DataFrame([{"segment_id": "ALL", "data_status": STUB_STATUS, "instructions": msg}])
        write_csv(stub, CORRIDOR_STATS_OUT)
        print(f"Wrote stub {CORRIDOR_STATS_OUT}")
        return 0

    stats_df = _segment_stats_from_scenes(segments, ok_scenes)
    write_csv(stats_df, CORRIDOR_STATS_OUT)
    print(f"Wrote {CORRIDOR_STATS_OUT} ({len(stats_df)} segments, scenes={len(ok_scenes)})")
    print(f"Wrote {SCENE_QA_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
