"""
Export BC Geographic Warehouse transmission lines to bundled demo GeoJSON (WGS84).

Run from repo root:
  python TMP/scripts/export_bc_transmission_sample.py

Input (optional local copies, gitignored):
  data/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml  (NetworkLink stub only)
  data/*.kml with full vector geometry if downloaded separately

Primary source when no local vectors:
  WFS pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP (openmaps.gov.bc.ca)

Output (committed for Streamlit Cloud, target < 500 KB):
  data/demo/demo_bc_transmission_lines_sample.geojson
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.outage_loader import _public_http_get  # noqa: E402

LOCAL_KML = REPO_ROOT / "data" / "WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml"
OUT_PATH = REPO_ROOT / "data" / "demo" / "demo_bc_transmission_lines_sample.geojson"
MAX_BYTES = 500 * 1024
TARGET_FEATURES = 70
SIMPLIFY_TOLERANCE_DEG = 0.0008

WFS_BASE = "https://openmaps.gov.bc.ca/geo/pub/wfs"
WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
# Lower Mainland — matches demo corridor region (WGS84)
DEFAULT_BBOX_WGS84 = (-123.25, 49.05, -122.35, 49.45)

DATASET_NOTE = (
    "BC Geographic Warehouse WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP — "
    "province-wide HV transmission reference (Geo.ca / openmaps.gov.bc.ca). "
    "Bundled sample for demo overlay; not BC Hydro feeder topology."
)


def _wgs84_bbox_to_native(bbox_wgs84: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = bbox_wgs84
    gdf = gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs="EPSG:4326").to_crs(3005)
    return tuple(gdf.total_bounds)


def _load_from_wfs(
    *,
    bbox_wgs84: tuple[float, float, float, float] | None = None,
    max_features: int | None = None,
) -> gpd.GeoDataFrame:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
    }
    if max_features is not None:
        params["count"] = str(max_features)
    if bbox_wgs84 is not None:
        xmin, ymin, xmax, ymax = _wgs84_bbox_to_native(bbox_wgs84)
        params["bbox"] = f"{xmin},{ymin},{xmax},{ymax},urn:ogc:def:crs:EPSG::3005"
    url = f"{WFS_BASE}?{urllib.parse.urlencode(params)}"
    content, _ssl_note = _public_http_get(url)
    payload = json.loads(content.decode("utf-8"))
    gdf = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs="EPSG:3005")
    if gdf.empty:
        raise RuntimeError("WFS returned no features (check bbox CRS or network).")
    return gdf


def _load_from_local_kml(path: Path) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        gdf = gpd.read_file(path)
    except Exception:
        return None
    if gdf.empty or not {"LineString", "MultiLineString"} & set(gdf.geometry.geom_type):
        return None
    return gdf


def _stratified_sample(gdf: gpd.GeoDataFrame, target: int) -> gpd.GeoDataFrame:
    """Spread sample across BC using a coarse grid on projected centroids."""
    work = gdf.to_crs(3005).copy()
    cent = work.geometry.centroid
    work["cx"] = cent.x
    work["cy"] = cent.y
    if "FEATURE_LENGTH_M" not in work.columns:
        work["FEATURE_LENGTH_M"] = work.geometry.length

    x_bins = np.linspace(work["cx"].min(), work["cx"].max(), 7)
    y_bins = np.linspace(work["cy"].min(), work["cy"].max(), 6)
    picks: list[pd.DataFrame] = []
    per_cell = 1

    for i in range(len(x_bins) - 1):
        for j in range(len(y_bins) - 1):
            mask = (
                (work["cx"] >= x_bins[i])
                & (work["cx"] < x_bins[i + 1])
                & (work["cy"] >= y_bins[j])
                & (work["cy"] < y_bins[j + 1])
            )
            cell = work.loc[mask].sort_values("FEATURE_LENGTH_M", ascending=False).head(per_cell)
            if not cell.empty:
                picks.append(cell)

    if not picks:
        return work.sample(n=min(target, len(work)), random_state=42)

    sample = pd.concat(picks, ignore_index=True).drop_duplicates(
        subset=["TRANSMISSION_LINE_ID"] if "TRANSMISSION_LINE_ID" in work.columns else None
    )
    if len(sample) > target:
        sample = sample.sort_values("FEATURE_LENGTH_M", ascending=False).head(target)
    elif len(sample) < target:
        remaining = work.loc[~work.index.isin(sample.index)]
        extra = remaining.sample(n=min(target - len(sample), len(remaining)), random_state=42)
        sample = pd.concat([sample, extra], ignore_index=True)
    return gpd.GeoDataFrame(sample, geometry="geometry", crs=work.crs)


def _prepare_output(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.to_crs(4326)
    if SIMPLIFY_TOLERANCE_DEG > 0:
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(
            SIMPLIFY_TOLERANCE_DEG, preserve_topology=True
        )
    keep = [
        c
        for c in (
            "TRANSMISSION_LINE_ID",
            "CIRCUIT_NAME",
            "CIRCUIT_DESCRIPTION",
            "OWNER",
            "FEATURE_LENGTH_M",
        )
        if c in gdf.columns
    ]
    out = gdf[keep + ["geometry"]].copy()
    out["dataset_note"] = DATASET_NOTE
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lower-mainland",
        action="store_true",
        help="Fetch only Lower Mainland bbox (skip province-wide stratified sample)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=None,
        help="WFS feature cap (default: 120 for --lower-mainland, else full layer)",
    )
    args = parser.parse_args()

    gdf = _load_from_local_kml(LOCAL_KML)
    source = "local KML"
    if gdf is None:
        bbox = DEFAULT_BBOX_WGS84 if args.lower_mainland else None
        cap = args.max_features if args.max_features is not None else (120 if args.lower_mainland else None)
        gdf = _load_from_wfs(bbox_wgs84=bbox, max_features=cap)
        source = "WFS (openmaps.gov.bc.ca)" + (" [Lower Mainland bbox]" if bbox else "")

    print(f"Loaded {len(gdf)} features from {source}")
    print("geometry types:", gdf.geometry.geom_type.value_counts().to_dict())
    print("native CRS:", gdf.crs)
    bounds = gdf.to_crs(4326).total_bounds.tolist()
    print("WGS84 bounds [minx, miny, maxx, maxy]:", bounds)

    if args.lower_mainland:
        sample = gdf
    else:
        sample = _stratified_sample(gdf, TARGET_FEATURES)
    out = _prepare_output(sample)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_file(OUT_PATH, driver="GeoJSON")

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {len(out)} features to {OUT_PATH} ({size_kb:.1f} KB)")
    if OUT_PATH.stat().st_size > MAX_BYTES:
        print(f"WARNING: exceeds {MAX_BYTES // 1024} KB Streamlit bundle target")


if __name__ == "__main__":
    main()
