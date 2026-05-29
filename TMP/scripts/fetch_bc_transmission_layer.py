"""
Fetch BC Geographic Warehouse transmission lines (WFS) into data/processed/.

Run from repo root (network + geopandas + requests):

  python TMP/scripts/fetch_bc_transmission_layer.py
  python TMP/scripts/fetch_bc_transmission_layer.py --bbox -123.25 49.05 -122.35 49.45

Output (gitignored, preferred by network_loader when present):
  data/processed/bc_transmission_lines_lower_mainland.geojson

Bundled fallback (commit for Streamlit Cloud):
  data/demo/demo_bc_transmission_lines_sample.geojson
  python TMP/scripts/export_bc_transmission_sample.py --lower-mainland

WFS: https://openmaps.gov.bc.ca/geo/pub/wfs
Layer: pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP
Docs: docs/bc_transmission_lines_public_data.md
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import (  # noqa: E402
    BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84,
    BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON,
    PROCESSED_DATA_DIR,
)
from src.outage_loader import _public_http_get  # noqa: E402

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/wfs"
WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
NATIVE_CRS = "EPSG:3005"
DATASET_NOTE = (
    "BC Geographic Warehouse WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP — "
    "Lower Mainland WFS export (openmaps.gov.bc.ca). Reference overlay only."
)


def _wgs84_to_native_bbox(bbox_wgs84: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = bbox_wgs84
    gdf = gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs="EPSG:4326").to_crs(NATIVE_CRS)
    return tuple(gdf.total_bounds)


def fetch_wfs_geojson(
    *,
    bbox_wgs84: tuple[float, float, float, float],
    max_features: int | None,
) -> dict:
    xmin, ymin, xmax, ymax = _wgs84_to_native_bbox(bbox_wgs84)
    params: dict[str, str] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
        "bbox": f"{xmin},{ymin},{xmax},{ymax},urn:ogc:def:crs:EPSG::3005",
    }
    if max_features is not None:
        params["count"] = str(max_features)
    url = f"{WFS_BASE}?{urllib.parse.urlencode(params)}"
    content, _ssl_note = _public_http_get(url)
    return json.loads(content.decode("utf-8"))


def to_processed_geojson(payload: dict, out_path: Path) -> Path:
    gdf = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs=NATIVE_CRS)
    if gdf.empty:
        raise RuntimeError("WFS returned no features (check bbox CRS, network, or firewall).")

    gdf = gdf.to_crs(4326)
    keep = [
        c
        for c in (
            "TRANSMISSION_LINE_ID",
            "CIRCUIT_NAME",
            "CIRCUIT_DESCRIPTION",
            "VOLTAGE",
            "OWNER",
            "FEATURE_LENGTH_M",
            "OBJECTID",
        )
        if c in gdf.columns
    ]
    out = gdf[keep + ["geometry"]].copy()
    if "TRANSMISSION_LINE_ID" in out.columns:
        out["line_id"] = out["TRANSMISSION_LINE_ID"].astype(str)
    else:
        out["line_id"] = out.index.astype(str)
    out["dataset_note"] = DATASET_NOTE

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(out_path, driver="GeoJSON")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84,
        help="WGS84 bounding box (default: Lower Mainland)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=None,
        help="Optional WFS feature cap (default: all features in bbox)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON,
        help="Output GeoJSON path",
    )
    args = parser.parse_args()
    bbox = tuple(args.bbox)

    payload = fetch_wfs_geojson(bbox_wgs84=bbox, max_features=args.max_features)
    matched = payload.get("numberMatched", payload.get("totalFeatures", "?"))
    returned = len(payload.get("features") or [])
    out = to_processed_geojson(payload, args.out)
    size_kb = out.stat().st_size / 1024
    print(f"WFS layer: {WFS_LAYER}")
    print(f"WFS endpoint: {WFS_BASE}")
    print(f"Matched ~{matched}, returned {returned} features")
    print(f"Wrote {out} ({size_kb:.1f} KB)")
    print()
    print("Manual fallback (no Python):")
    print(
        "  ogr2ogr -f GeoJSON data/processed/bc_transmission_lines_lower_mainland.geojson "
        f'WFS:"{WFS_BASE}" {WFS_LAYER} '
        "-spat_srs EPSG:3005 -spat <native xmin ymin xmax ymax from QGIS>"
    )


if __name__ == "__main__":
    main()
