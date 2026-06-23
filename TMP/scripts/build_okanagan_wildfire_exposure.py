#!/usr/bin/env python3
"""
Wildfire exposure proxy for Okanagan corridor segments.

Fetches open/public CWFIS layers (CWFIF active fires + legacy 24h hotspots).
Falls back to synthetic placeholder only when live services are unreachable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import geopandas as gpd
import numpy as np
import pandas as pd
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.outage_loader import _public_http_get  # noqa: E402
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_REGION_NAME  # noqa: E402

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    OKANAGAN_PROCESSED_DIR,
    load_okanagan_segments,
    today_iso,
    write_csv,
)

CSV_OUT = OKANAGAN_PROCESSED_DIR / "okanagan_cwfis_wildfire_exposure.csv"
GEOJSON_OUT = OKANAGAN_PROCESSED_DIR / "okanagan_wildfire_layers.geojson"

# Public CWFIS / CWFIF GeoServer endpoints (NRCan open data — not BC Hydro internal)
CWFIF_WFS = "https://geoserver.cwfif.nrcan.gc.ca/geoserver/ows"
CWFIS_LEGACY_WFS = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows"
CWFIF_ACTIVE_LAYER = "public:cwfif_national_activefires"
CWFIS_HOTSPOTS_LAYER = "public:hotspots_24h"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _distance_band_score(km: float) -> float:
    if km <= 2:
        return 95.0
    if km <= 5:
        return 80.0
    if km <= 10:
        return 65.0
    if km <= 20:
        return 45.0
    if km <= 50:
        return 25.0
    return 10.0


def _in_bbox(lat: float | None, lon: float | None, bbox: tuple[float, float, float, float]) -> bool:
    if lat is None or lon is None:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _wfs_geojson(url: str) -> gpd.GeoDataFrame | None:
    content, _ = _public_http_get(url)
    payload = json.loads(content.decode("utf-8"))
    features = payload.get("features") or []
    if not features:
        return None
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    # CWFIF returns projected coordinates in geometry; prefer explicit lat/lon when present.
    if "latitude" in gdf.columns and "longitude" in gdf.columns:
        gdf = gdf.set_geometry(
            gpd.points_from_xy(gdf["longitude"], gdf["latitude"]),
            crs="EPSG:4326",
        )
    elif "lat" in gdf.columns and "lon" in gdf.columns:
        gdf = gdf.set_geometry(gpd.points_from_xy(gdf["lon"], gdf["lat"]), crs="EPSG:4326")
    return gdf


def _fetch_cwfif_active_fires(bbox: tuple[float, float, float, float]) -> tuple[gpd.GeoDataFrame | None, str | None]:
    """Currently active BC wildland fires from CWFIF WFS (agency-reported)."""
    params = urlencode(
        {
            "service": "WFS",
            "version": "2.0.1",
            "request": "GetFeature",
            "typeName": CWFIF_ACTIVE_LAYER,
            "outputFormat": "application/json",
            "CQL_FILTER": "agency_code='BC' AND now()>=record_start AND now()<=record_end",
            "count": "500",
        }
    )
    url = f"{CWFIF_WFS}?{params}"
    try:
        gdf = _wfs_geojson(url)
        if gdf is None or gdf.empty:
            return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326"), None
        if "latitude" in gdf.columns and "longitude" in gdf.columns:
            mask = [
                _in_bbox(row.get("latitude"), row.get("longitude"), bbox)
                for _, row in gdf.iterrows()
            ]
            gdf = gdf.loc[mask].copy()
        gdf["layer_type"] = "cwfif_active_fire"
        gdf["data_status"] = "cwfis_live"
        gdf["data_source"] = "CWFIF WFS public:cwfif_national_activefires (BC, currently active)"
        if "agency_fire_id" in gdf.columns:
            gdf["fire_id"] = gdf["agency_fire_id"]
        return (gdf if not gdf.empty else gpd.GeoDataFrame(columns=gdf.columns, crs="EPSG:4326")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"CWFIF active fires: {exc}"


def _fetch_cwfis_hotspots_24h(bbox: tuple[float, float, float, float]) -> tuple[gpd.GeoDataFrame | None, str | None]:
    """Satellite-detected hotspots (last 24 hours) from legacy CWFIS GeoServer."""
    min_lon, min_lat, max_lon, max_lat = bbox
    params = urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": CWFIS_HOTSPOTS_LAYER,
            "outputFormat": "application/json",
            "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat},EPSG:4326",
            "count": "5000",
        }
    )
    url = f"{CWFIS_LEGACY_WFS}?{params}"
    try:
        gdf = _wfs_geojson(url)
        if gdf is None or gdf.empty:
            return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326"), None
        if "lat" in gdf.columns and "lon" in gdf.columns and gdf.geometry.isna().all():
            gdf = gdf.set_geometry(gpd.points_from_xy(gdf["lon"], gdf["lat"]), crs="EPSG:4326")
        gdf["layer_type"] = "cwfis_hotspot_24h"
        gdf["data_status"] = "cwfis_live"
        gdf["data_source"] = "CWFIS WFS public:hotspots_24h (satellite, last 24h)"
        gdf["fire_id"] = [
            f"HOT-{i:05d}" for i in range(len(gdf))
        ]
        return gdf, None
    except Exception as exc:  # noqa: BLE001
        return None, f"CWFIS hotspots_24h: {exc}"


def _fetch_cwfis_live_layers(
    bbox: tuple[float, float, float, float],
) -> tuple[gpd.GeoDataFrame | None, list[str], list[str]]:
    """Return combined live fire points, successful layer notes, and fetch errors."""
    errors: list[str] = []
    layers: list[str] = []
    parts: list[gpd.GeoDataFrame] = []

    active, active_err = _fetch_cwfif_active_fires(bbox)
    if active_err:
        errors.append(active_err)
    elif active is not None:
        layers.append(f"CWFIF active fires ({len(active)} in AOI)")
        parts.append(active)

    hotspots, hot_err = _fetch_cwfis_hotspots_24h(bbox)
    if hot_err:
        errors.append(hot_err)
    elif hotspots is not None:
        layers.append(f"CWFIS hotspots_24h ({len(hotspots)} in AOI)")
        parts.append(hotspots)

    if not parts:
        return None, layers, errors

    combined = pd.concat(parts, ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
    return combined, layers, errors


def _synthetic_fire_points(bbox: tuple[float, float, float, float], *, seed: int) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    min_lon, min_lat, max_lon, max_lat = bbox
    n = 8
    lons = rng.uniform(min_lon, max_lon, n)
    lats = rng.uniform(min_lat, max_lat, n)
    return gpd.GeoDataFrame(
        {
            "fire_id": [f"SYN-FIRE-{i:03d}" for i in range(n)],
            "layer_type": "synthetic_placeholder",
            "data_status": "synthetic_placeholder",
            "data_source": (
                "Synthetic wildfire point placeholder (seed=42). "
                "CWFIS live fetch failed — replace when services are reachable."
            ),
            "notes": "Placeholder only; not agency or satellite data.",
        },
        geometry=gpd.points_from_xy(lons, lats),
        crs="EPSG:4326",
    )


def _wildfire_exposure_score(min_dist_km: float, fire_density: float) -> float:
    dist_score = _distance_band_score(min_dist_km)
    density_score = min(100.0, fire_density * 15.0)
    return round(float(np.clip(0.65 * dist_score + 0.35 * density_score, 0, 100)), 2)


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments).to_crs(4326)

    fires, layer_notes, fetch_errors = _fetch_cwfis_live_layers(OKANAGAN_AOI_BBOX)
    if fires is not None:
        data_status = "cwfis_live"
        source_note = (
            "Open/public CWFIS (NRCan): "
            + "; ".join(layer_notes)
            + ". Not BC Hydro internal data."
        )
        if fetch_errors:
            source_note += " Partial fetch warnings: " + "; ".join(fetch_errors)
        print(f"CWFIS live fetch OK — {len(fires)} fire/hotspot points in Okanagan AOI.")
        for note in layer_notes:
            print(f"  • {note}")
        for err in fetch_errors:
            print(f"  WARNING: {err}")
    else:
        fires = _synthetic_fire_points(OKANAGAN_AOI_BBOX, seed=args.seed)
        data_status = "synthetic_placeholder"
        source_note = fires.iloc[0]["data_source"]
        print("WARNING: CWFIS live fetch failed — using synthetic wildfire exposure.")
        for err in fetch_errors:
            print(f"  • {err}")

    active_count = int((fires.get("layer_type") == "cwfif_active_fire").sum()) if "layer_type" in fires.columns else 0
    hotspot_count = int((fires.get("layer_type") == "cwfis_hotspot_24h").sum()) if "layer_type" in fires.columns else 0

    fires_metric = fires.to_crs(3005)
    seg_metric = segments.to_crs(3005)

    rows: list[dict] = []
    for _, seg in seg_metric.iterrows():
        centroid = seg.geometry.centroid
        if len(fires_metric):
            distances_m = fires_metric.geometry.distance(centroid)
            min_dist_km = float(distances_m.min() / 1000.0)
            nearby = int((distances_m <= 20_000).sum())
        else:
            min_dist_km = 999.0
            nearby = 0
        exposure = _wildfire_exposure_score(min_dist_km, nearby)
        rows.append(
            {
                "corridor_id": seg.get("corridor_id"),
                "segment_id": seg.get("segment_id"),
                "region": seg.get("region", OKANAGAN_REGION_NAME),
                "nearest_fire_km": round(min_dist_km, 2),
                "fires_within_20km": nearby,
                "active_fires_in_aoi": active_count,
                "hotspots_24h_in_aoi": hotspot_count,
                "distance_band_score": _distance_band_score(min_dist_km),
                "wildfire_density_score": min(100.0, nearby * 15.0),
                "wildfire_exposure_score": exposure,
                "data_status": data_status,
                "data_source": source_note,
                "as_of_date": today_iso(),
            }
        )

    df = pd.DataFrame(rows)
    write_csv(df, CSV_OUT)

    layers = pd.concat(
        [
            fires.assign(layer="wildfire_points"),
            segments.assign(layer="corridor_segments"),
        ],
        ignore_index=True,
    )
    layers.to_file(GEOJSON_OUT, driver="GeoJSON")
    print(f"Wrote {CSV_OUT} ({len(df)} segments, status={data_status})")
    print(f"Wrote {GEOJSON_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
