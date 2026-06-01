#!/usr/bin/env python3
"""BC VRI WFS clip + aggregate crown closure / height for Surrey corridor AOI."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _surrey_pipeline_common import DEFAULT_AOI, DEFAULT_OUT_DIR, load_aoi, stub_row, today_iso, write_csv  # noqa: E402

VRI_WFS = "https://openmaps.gov.bc.ca/geo/pub/WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY/wfs"
VRI_LAYER = "pub:WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Surrey VRI corridor stats.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-features", type=int, default=5000)
    return parser.parse_args()


def fetch_vri_bbox(bbox: tuple[float, float, float, float], max_features: int) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": VRI_LAYER,
        "outputFormat": "application/json",
        "count": str(max_features),
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
    }
    resp = requests.get(VRI_WFS, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return gpd.GeoDataFrame.from_features(data.get("features", []), crs="EPSG:4326")


def main() -> int:
    args = parse_args()
    aoi, aoi_id = load_aoi(args.aoi)
    aoi_union = aoi.to_crs("EPSG:4326").union_all()
    minx, miny, maxx, maxy = aoi_union.bounds

    try:
        vri = fetch_vri_bbox((minx, miny, maxx, maxy), args.max_features)
        if vri.empty:
            row = stub_row(
                aoi_id=aoi_id,
                layer="bc_vri_r1",
                data_status="stub_no_polygons",
                instructions="VRI WFS returned no polygons in corridor bbox (sparse urban Surrey).",
                extra={"vri_mean_crown_closure": None, "vri_mean_height_m": None},
            )
        else:
            clipped = gpd.clip(vri, aoi.to_crs("EPSG:4326"))
            if clipped.empty:
                row = stub_row(
                    aoi_id=aoi_id,
                    layer="bc_vri_r1",
                    data_status="stub_no_intersection",
                    instructions="VRI polygons in bbox but none intersect corridor buffer.",
                    extra={"vri_mean_crown_closure": None, "vri_mean_height_m": None},
                )
            else:
                crown_col = next((c for c in ("CROWN_CLOSURE", "CROWN_CLOS") if c in clipped.columns), None)
                height_col = next((c for c in ("HEIGHT", "STAND_HEIGHT") if c in clipped.columns), None)
                crown = (
                    pd.to_numeric(clipped[crown_col], errors="coerce").mean()
                    if crown_col
                    else None
                )
                height = (
                    pd.to_numeric(clipped[height_col], errors="coerce").mean()
                    if height_col
                    else None
                )
                row = {
                    "aoi_id": aoi_id,
                    "layer": "bc_vri_r1",
                    "data_status": "open_free_processed",
                    "data_source": "open_free_v1",
                    "as_of_date": today_iso(),
                    "instructions": "",
                    "vri_polygon_count": len(clipped),
                    "vri_mean_crown_closure": round(float(crown), 2) if crown is not None and pd.notna(crown) else None,
                    "vri_mean_height_m": round(float(height), 2) if height is not None and pd.notna(height) else None,
                }
        df = pd.DataFrame([row])
    except ET.ParseError as exc:
        df = pd.DataFrame(
            [
                stub_row(
                    aoi_id=aoi_id,
                    layer="bc_vri_r1",
                    data_status="stub_wfs_error",
                    instructions=f"VRI WFS parse error: {exc}",
                    extra={"vri_mean_crown_closure": None, "vri_mean_height_m": None},
                )
            ]
        )
    except Exception as exc:  # noqa: BLE001
        df = pd.DataFrame(
            [
                stub_row(
                    aoi_id=aoi_id,
                    layer="bc_vri_r1",
                    data_status="stub_wfs_error",
                    instructions=f"VRI WFS fetch failed: {exc}",
                    extra={"vri_mean_crown_closure": None, "vri_mean_height_m": None},
                )
            ]
        )

    out = args.out_dir / "surrey_vri_corridor_stats.csv"
    write_csv(df, out)
    print(f"Wrote {out} (status={df['data_status'].iloc[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
