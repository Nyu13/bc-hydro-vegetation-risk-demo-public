#!/usr/bin/env python3
"""
Build province-wide BC transmission lines GeoJSON for map context overlay.

Downloads the BC Geographic Warehouse KML stub and fetches all HV lines via WFS
(no Okanagan clip). Corridor segmentation remains Okanagan-only.

Output: data/processed/bc_transmission_lines.geojson
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import geopandas as gpd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.config import BC_TRANSMISSION_LINES_GEOJSON, RAW_DATA_DIR  # noqa: E402
from src.outage_loader import _public_http_get  # noqa: E402

from _okanagan_pipeline_common import ensure_dirs  # noqa: E402

KML_URL = "https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP.kml"
WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
NATIVE_CRS = "EPSG:3005"
RAW_KML_DIR = RAW_DATA_DIR / "bc_transmission_lines"
DATASET_NOTE = (
    "BC Geographic Warehouse WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP — "
    "province-wide WFS export (openmaps.gov.bc.ca). Map context overlay only."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=BC_TRANSMISSION_LINES_GEOJSON,
        help="Output GeoJSON path",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=None,
        help="Optional WFS feature cap (default: all BC lines)",
    )
    parser.add_argument(
        "--simplify-m",
        type=float,
        default=0.0,
        help="Optional Douglas-Peucker simplify tolerance in metres (EPSG:3005)",
    )
    return parser.parse_args()


def download_kml_stub(dest_dir: Path) -> Path:
    ensure_dirs(dest_dir)
    dest = dest_dir / "WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP.kml"
    if dest.is_file() and dest.stat().st_size > 200:
        return dest
    try:
        content, _ = _public_http_get(KML_URL)
        dest.write_bytes(content)
        print(f"Downloaded KML stub to {dest}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: KML download failed ({exc}); continuing with WFS only.")
    return dest


def fetch_bc_lines(max_features: int | None) -> gpd.GeoDataFrame:
    params: dict[str, str] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
    }
    if max_features is not None:
        params["count"] = str(max_features)
    url = f"{WFS_URL}?{urllib.parse.urlencode(params)}"
    content, _ = _public_http_get(url)
    payload = json.loads(content.decode("utf-8"))
    gdf = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs=NATIVE_CRS)
    if gdf.empty:
        raise RuntimeError("WFS returned no transmission lines for BC.")
    return gdf


def main() -> int:
    args = parse_args()
    download_kml_stub(RAW_KML_DIR)
    lines = fetch_bc_lines(args.max_features)
    if args.simplify_m > 0:
        metric = lines.to_crs(NATIVE_CRS)
        metric["geometry"] = metric.geometry.simplify(args.simplify_m, preserve_topology=True)
        lines = metric

    keep = [
        c
        for c in (
            "TRANSMISSION_LINE_ID",
            "CIRCUIT_NAME",
            "VOLTAGE",
            "OWNER",
            "FEATURE_LENGTH_M",
        )
        if c in lines.columns
    ]
    out = lines[keep + ["geometry"]].copy()
    if "TRANSMISSION_LINE_ID" in out.columns:
        out["line_id"] = out["TRANSMISSION_LINE_ID"].astype(str)
    else:
        out["line_id"] = out.index.astype(str)
    out["dataset_note"] = DATASET_NOTE

    ensure_dirs(args.out.parent)
    out_wgs84 = out.to_crs(4326)
    out_wgs84.to_file(args.out, driver="GeoJSON")
    size_mb = args.out.stat().st_size / (1024 * 1024)
    print(f"Wrote {len(out_wgs84)} lines to {args.out} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
