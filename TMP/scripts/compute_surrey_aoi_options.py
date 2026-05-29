#!/usr/bin/env python3
"""Compute Surrey AOI options (municipal, corridor buffers, outage-prone sub-area).

Downloads City of Surrey boundary via ArcGIS REST, intersects BC transmission lines,
and writes GeoJSON + hectare summary to data/demo/ and TMP/docs/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box, mapping
from shapely.ops import unary_union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
TMP_DOCS = PROJECT_ROOT / "TMP" / "docs"
SURREY_BOUNDARY_URL = (
    "https://gisservices.surrey.ca/arcgis/rest/services/Base_Map_All_Scales/MapServer/165/query"
    "?where=1%3D1&outSR=4326&f=geojson"
)
BC_TRANSMISSION_GEOJSON = DEMO_DIR / "demo_bc_transmission_lines_sample.geojson"
MUNICIPALITY_OUTAGE_CSV = DEMO_DIR / "demo_municipality_outage_summary.csv"
BUFFER_METERS = (100, 200, 300)
# Surrey pilot sub-area: approximate center of highest tree-related outage density proxy
# (full span-level hotspot requires BC Hydro internal data; this is a demo bbox)
OUTAGE_SUBAREA_CENTER = (-122.85, 49.19)
OUTAGE_SUBAREA_RADIUS_KM = 4.0


def fetch_surrey_boundary() -> gpd.GeoDataFrame:
    resp = requests.get(SURREY_BOUNDARY_URL, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    gdf = gpd.GeoDataFrame.from_features(data.get("features", []), crs="EPSG:4326")
    if gdf.empty:
        raise RuntimeError("Surrey boundary query returned no features")
    return gdf


def hectares_albers(gdf: gpd.GeoDataFrame) -> float:
    """Area in hectares using BC Albers equal-area projection."""
    projected = gdf.to_crs("EPSG:3005")
    return float(projected.geometry.area.sum() / 10_000.0)


def load_transmission_in_surrey(surrey: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if not BC_TRANSMISSION_GEOJSON.is_file():
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    lines = gpd.read_file(BC_TRANSMISSION_GEOJSON)
    if lines.crs is None:
        lines = lines.set_crs("EPSG:4326")
    return gpd.clip(lines, surrey)


def corridor_buffer_union(lines: gpd.GeoDataFrame, buffer_m: int, surrey: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if lines.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    lines_proj = lines.to_crs("EPSG:3005")
    buffered = lines_proj.buffer(buffer_m)
    union = unary_union(buffered.values)
    gdf = gpd.GeoDataFrame(geometry=[union], crs="EPSG:3005")
    gdf = gdf.to_crs("EPSG:4326")
    clipped = gpd.clip(gdf, surrey)
    return clipped


def outage_subarea_polygon(surrey: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    lon, lat = OUTAGE_SUBAREA_CENTER
    radius_deg = OUTAGE_SUBAREA_RADIUS_KM / 111.0
    circle = box(lon - radius_deg, lat - radius_deg, lon + radius_deg, lat + radius_deg)
    gdf = gpd.GeoDataFrame(geometry=[circle], crs="EPSG:4326")
    return gpd.clip(gdf, surrey)


def write_geojson(gdf: gpd.GeoDataFrame, path: Path, properties: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = gdf.copy()
    if properties:
        for key, val in properties.items():
            out[key] = val
    out.to_file(path, driver="GeoJSON")


def main() -> int:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DOCS.mkdir(parents=True, exist_ok=True)

    print("Fetching Surrey municipal boundary...")
    surrey = fetch_surrey_boundary()
    municipal_ha = hectares_albers(surrey)
    print(f"  Municipal area: {municipal_ha:,.1f} ha")

    boundary_path = DEMO_DIR / "surrey_municipal_boundary.geojson"
    write_geojson(
        surrey,
        boundary_path,
        {"aoi_id": "SURREY-MUNICIPAL", "area_hectares": round(municipal_ha, 1)},
    )

    lines = load_transmission_in_surrey(surrey)
    print(f"  Transmission line segments in Surrey (sample layer): {len(lines)}")

    buffer_results: dict[int, float] = {}
    for buf_m in BUFFER_METERS:
        buf_gdf = corridor_buffer_union(lines, buf_m, surrey)
        ha = hectares_albers(buf_gdf) if not buf_gdf.empty else 0.0
        buffer_results[buf_m] = ha
        out_path = DEMO_DIR / f"surrey_transmission_buffer_{buf_m}m.geojson"
        write_geojson(
            buf_gdf,
            out_path,
            {
                "aoi_id": f"SURREY-TX-BUF-{buf_m}M",
                "buffer_m": buf_m,
                "area_hectares": round(ha, 1),
            },
        )
        print(f"  Corridor buffer {buf_m}m: {ha:,.1f} ha")

    subarea = outage_subarea_polygon(surrey)
    subarea_ha = hectares_albers(subarea)
    subarea_path = DEMO_DIR / "surrey_outage_prone_subarea.geojson"
    write_geojson(
        subarea,
        subarea_path,
        {
            "aoi_id": "SURREY-OUTAGE-SUBAREA",
            "area_hectares": round(subarea_ha, 1),
            "note": "Demo sub-area (~4 km radius at Surrey centroid); not BC Hydro feeder truth",
        },
    )
    print(f"  Outage-prone sub-area (demo): {subarea_ha:,.1f} ha")

    # Outage summary for Surrey
    outage_note = ""
    if MUNICIPALITY_OUTAGE_CSV.is_file():
        df = pd.read_csv(MUNICIPALITY_OUTAGE_CSV)
        surrey_row = df[df["municipality"].str.lower() == "surrey"]
        if not surrey_row.empty:
            r = surrey_row.iloc[0]
            outage_note = (
                f"Surrey ranks #1 in unofficial municipality archive proxy "
                f"({int(r['unique_outages'])} unique outages, "
                f"{int(r['tree_related_outage_count'])} tree-related, "
                f"priority score {float(r['suggested_priority_score']):.3f})."
            )

    summary = {
        "municipal_hectares": round(municipal_ha, 1),
        "reference_hectares_31600": 31600,
        "corridor_buffer_hectares": {str(k): round(v, 1) for k, v in buffer_results.items()},
        "outage_subarea_hectares": round(subarea_ha, 1),
        "transmission_segments_in_sample": len(lines),
        "outage_proxy_note": outage_note,
        "files": [
            str(boundary_path.relative_to(PROJECT_ROOT)),
            *(f"data/demo/surrey_transmission_buffer_{b}m.geojson" for b in BUFFER_METERS),
            str(subarea_path.relative_to(PROJECT_ROOT)),
        ],
    }
    summary_path = TMP_DOCS / "surrey_aoi_hectares.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote summary to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
