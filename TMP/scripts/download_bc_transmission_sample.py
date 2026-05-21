"""
Fetch BC Geographic Warehouse transmission lines via WFS and write a demo GeoJSON sample.

Run from repo root (requires network + geopandas + requests):

  python TMP/scripts/download_bc_transmission_sample.py

Optional bbox (WGS84 lon/lat): --bbox -123.25 49.05 -122.35 49.45

Output (committed for Streamlit Cloud):
  data/demo/demo_bc_transmission_lines_sample.geojson

Full-province or custom exports (gitignored):
  data/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml  (NetworkLink stub only)
  data/raw/bc_transmission_lines_full.geojson

Metadata: https://geocore.metadata.geo.ca/384d551b-dee1-4df8-8148-b3fcf865096a.geojson
Docs: TMP/docs/BC_TRANSMISSION_DOWNLOAD.md
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "demo" / "demo_bc_transmission_lines_sample.geojson"

WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
NATIVE_CRS = "EPSG:3005"

# Lower Mainland (Vancouver metro) — aligns with demo corridor region
DEFAULT_BBOX_WGS84 = (-123.25, 49.05, -122.35, 49.45)


def _wgs84_to_native_bbox(bbox_wgs84: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = bbox_wgs84
    gdf = gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs="EPSG:4326").to_crs(NATIVE_CRS)
    return tuple(gdf.total_bounds)


def fetch_wfs_geojson(
    *,
    bbox_wgs84: tuple[float, float, float, float],
    max_features: int,
) -> dict:
    xmin, ymin, xmax, ymax = _wgs84_to_native_bbox(bbox_wgs84)
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": LAYER,
        "outputFormat": "application/json",
        "count": str(max_features),
        "bbox": f"{xmin},{ymin},{xmax},{ymax},urn:ogc:def:crs:EPSG::3005",
    }
    url = f"{WFS_URL}?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    return json.loads(resp.text)


def to_demo_geojson(payload: dict, out_path: Path) -> Path:
    gdf = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs=NATIVE_CRS)
    if gdf.empty:
        raise RuntimeError("WFS returned no features for the requested bbox.")

    gdf = gdf.to_crs(4326)
    attrs = [
        c
        for c in (
            "TRANSMISSION_LINE_ID",
            "CIRCUIT_NAME",
            "CIRCUIT_DESCRIPTION",
            "VOLTAGE",
            "OWNER",
            "OBJECTID",
        )
        if c in gdf.columns
    ]
    gdf = gdf[attrs + ["geometry"]]
    gdf["line_id"] = gdf.get("TRANSMISSION_LINE_ID", gdf.index.astype(str)).astype(str)
    gdf["dataset_note"] = (
        "BC Geographic Warehouse GBA_TRANSMISSION_LINES_SP — public proxy, not BC Hydro operational GIS."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GeoJSON")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=DEFAULT_BBOX_WGS84,
        help="WGS84 bounding box (default: Lower Mainland)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=120,
        help="WFS feature limit (server may cap below province total)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output GeoJSON path",
    )
    args = parser.parse_args()
    bbox = tuple(args.bbox)

    payload = fetch_wfs_geojson(bbox_wgs84=bbox, max_features=args.max_features)
    matched = payload.get("numberMatched", payload.get("totalFeatures", "?"))
    returned = len(payload.get("features") or [])
    out = to_demo_geojson(payload, args.out)
    size_kb = out.stat().st_size / 1024
    print(f"WFS matched ~{matched}, returned {returned} features")
    print(f"Wrote {out} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
