#!/usr/bin/env python3
"""WorldCover zonal stats per Okanagan corridor segment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    OKANAGAN_PROCESSED_DIR,
    WORLDCOVER_BARE,
    WORLDCOVER_BUILT,
    WORLDCOVER_GRASS,
    WORLDCOVER_SHRUB,
    WORLDCOVER_TREE,
    load_okanagan_segments,
    resolve_worldcover_raster,
    today_iso,
    write_csv,
    zonal_class_percentages,
)

OUTPUT = OKANAGAN_PROCESSED_DIR / "okanagan_worldcover_corridor_stats.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    parser.add_argument("--worldcover-raster", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments)
    segments_wgs = segments.to_crs(4326)

    if args.worldcover_raster and args.worldcover_raster.is_file():
        raster_path, detail = args.worldcover_raster, f"Using {args.worldcover_raster}"
    else:
        union = segments_wgs.union_all()
        aoi = gpd.GeoDataFrame(geometry=[union], crs="EPSG:4326")
        raster_path, detail = resolve_worldcover_raster(aoi)

    rows: list[dict] = []
    if raster_path is None:
        for _, seg in segments_wgs.iterrows():
            rows.append(
                {
                    "corridor_id": seg.get("corridor_id"),
                    "segment_id": seg.get("segment_id"),
                    "region": seg.get("region"),
                    "worldcover_tree_pct": None,
                    "worldcover_shrub_grass_pct": None,
                    "worldcover_built_pct": None,
                    "worldcover_bare_pct": None,
                    "data_status": "stub_missing_raster",
                    "data_source": "ESA WorldCover 2021",
                    "instructions": detail,
                    "as_of_date": today_iso(),
                }
            )
    else:
        for _, seg in segments_wgs.iterrows():
            seg_gdf = gpd.GeoDataFrame([seg], geometry="geometry", crs=segments_wgs.crs)
            pct, status, msg = zonal_class_percentages(
                raster_path,
                seg_gdf,
                class_map={
                    "worldcover_tree_pct": {WORLDCOVER_TREE},
                    "worldcover_shrub_grass_pct": {WORLDCOVER_SHRUB, WORLDCOVER_GRASS},
                    "worldcover_built_pct": {WORLDCOVER_BUILT},
                    "worldcover_bare_pct": {WORLDCOVER_BARE},
                },
            )
            rows.append(
                {
                    "corridor_id": seg.get("corridor_id"),
                    "segment_id": seg.get("segment_id"),
                    "region": seg.get("region"),
                    **pct,
                    "data_status": status,
                    "data_source": "ESA WorldCover 2021",
                    "instructions": msg if status != "open_free_processed" else "",
                    "as_of_date": today_iso(),
                }
            )

    df = pd.DataFrame(rows)
    write_csv(df, OUTPUT)
    print(f"Wrote {OUTPUT} ({len(df)} segments, raster={'yes' if raster_path else 'no'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
