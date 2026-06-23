#!/usr/bin/env python3
"""
Build Okanagan transmission corridors from BC Geographic Warehouse lines.

Downloads KML stub, fetches lines via WFS for Okanagan bbox, buffers 200 m,
splits into ~5 km segments, and writes QA + preview map.

Proof-of-process only — public transmission reference, not BC Hydro operational GIS.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, box, mapping
from shapely.ops import linemerge, unary_union

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from src.outage_loader import _public_http_get  # noqa: E402
from src.regions import (  # noqa: E402
    OKANAGAN_AOI_BBOX,
    OKANAGAN_CORRIDOR_BUFFER_M,
    OKANAGAN_REGION_NAME,
    OKANAGAN_SEGMENT_LENGTH_KM,
)

from _okanagan_pipeline_common import ensure_dirs, today_iso, write_csv  # noqa: E402

KML_URL = "https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP.kml"
WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
NATIVE_CRS = "EPSG:3005"
METRIC_CRS = "EPSG:3005"

RAW_KML_DIR = RAW_DATA_DIR / "bc_transmission_lines"
LINES_OUT = PROCESSED_DATA_DIR / "okanagan_transmission_lines.geojson"
BUFFER_OUT = PROCESSED_DATA_DIR / "okanagan_corridor_buffer_200m.geojson"
SEGMENTS_OUT = PROCESSED_DATA_DIR / "okanagan_corridor_segments.geojson"
QA_OUT = PROCESSED_DATA_DIR / "okanagan_transmission_qa_summary.csv"
PREVIEW_OUT = PROCESSED_DATA_DIR / "okanagan_transmission_preview.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=OKANAGAN_AOI_BBOX,
    )
    parser.add_argument("--buffer-m", type=float, default=OKANAGAN_CORRIDOR_BUFFER_M)
    parser.add_argument("--segment-km", type=float, default=OKANAGAN_SEGMENT_LENGTH_KM)
    parser.add_argument("--max-features", type=int, default=500)
    return parser.parse_args()


def _wgs84_to_native_bbox(bbox_wgs84: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = bbox_wgs84
    gdf = gpd.GeoDataFrame(geometry=[box(xmin, ymin, xmax, ymax)], crs="EPSG:4326").to_crs(NATIVE_CRS)
    return tuple(gdf.total_bounds)


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


def fetch_wfs_lines(bbox_wgs84: tuple[float, float, float, float], max_features: int) -> gpd.GeoDataFrame:
    xmin, ymin, xmax, ymax = _wgs84_to_native_bbox(bbox_wgs84)
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
        "count": str(max_features),
        "bbox": f"{xmin},{ymin},{xmax},{ymax},urn:ogc:def:crs:EPSG::3005",
    }
    url = f"{WFS_URL}?{urllib.parse.urlencode(params)}"
    content, _ = _public_http_get(url)
    payload = json.loads(content.decode("utf-8"))
    gdf = gpd.GeoDataFrame.from_features(payload.get("features") or [], crs=NATIVE_CRS)
    if gdf.empty:
        raise RuntimeError("WFS returned no transmission lines for Okanagan bbox.")
    return gdf


def _line_parts(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if not part.is_empty]
    merged = linemerge(geom)
    if merged.geom_type == "LineString":
        return [merged]
    if merged.geom_type == "MultiLineString":
        return [part for part in merged.geoms if not part.is_empty]
    return []


def split_line_to_segments(line: LineString, segment_m: float) -> list[LineString]:
    if line.length <= segment_m:
        return [line]
    segments: list[LineString] = []
    start = 0.0
    while start < line.length:
        end = min(start + segment_m, line.length)
        sub = _substring(line, start, end)
        if sub is not None and not sub.is_empty and sub.length > 1:
            segments.append(sub)
        if end >= line.length:
            break
        start = end
    return segments


def _substring(line: LineString, start_dist: float, end_dist: float) -> LineString | None:
    if end_dist <= start_dist:
        return None
    try:
        total = line.length
        if total <= 0:
            return None
        start_frac = max(0.0, min(1.0, start_dist / total))
        end_frac = max(0.0, min(1.0, end_dist / total))
        if end_frac <= start_frac:
            return None
        # Use equal-interval point sampling for robust substring
        n = max(2, int((end_frac - start_frac) * 50) + 1)
        fracs = [start_frac + (end_frac - start_frac) * i / (n - 1) for i in range(n)]
        coords = [line.interpolate(frac, normalized=True).coords[0] for frac in fracs]
        return LineString(coords)
    except Exception:  # noqa: BLE001
        return None


def build_segments(gdf: gpd.GeoDataFrame, segment_km: float) -> gpd.GeoDataFrame:
    segment_m = segment_km * 1000.0
    rows: list[dict] = []
    metric = gdf.to_crs(METRIC_CRS)
    for idx, row in metric.iterrows():
        line_id = str(row.get("TRANSMISSION_LINE_ID", row.get("line_id", idx)))
        corridor_id = f"OK-TX-{line_id}"
        parts = _line_parts(row.geometry)
        seg_num = 0
        for part in parts:
            for seg in split_line_to_segments(part, segment_m):
                seg_num += 1
                length_km = round(seg.length / 1000.0, 3)
                rows.append(
                    {
                        "corridor_id": corridor_id,
                        "segment_id": f"{corridor_id}-S{seg_num:03d}",
                        "region": OKANAGAN_REGION_NAME,
                        "transmission_line_id": line_id,
                        "length_km": length_km,
                        "geometry": seg,
                    }
                )
    if not rows:
        raise RuntimeError("No corridor segments created from transmission lines.")
    return gpd.GeoDataFrame(rows, crs=METRIC_CRS)


def build_buffer(gdf: gpd.GeoDataFrame, buffer_m: float) -> gpd.GeoDataFrame:
    metric = gdf.to_crs(METRIC_CRS)
    dissolved = unary_union(metric.geometry)
    if dissolved.geom_type == "LineString":
        geoms = [dissolved]
    elif dissolved.geom_type == "MultiLineString":
        geoms = list(dissolved.geoms)
    else:
        geoms = _line_parts(dissolved)
    buffers = [geom.buffer(buffer_m) for geom in geoms if geom is not None and not geom.is_empty]
    if not buffers:
        raise RuntimeError("Buffer creation failed — no line geometry.")
    union = unary_union(buffers)
    buf_gdf = gpd.GeoDataFrame(
        [{"aoi_id": "okanagan_buffer_200m", "region": OKANAGAN_REGION_NAME, "buffer_m": buffer_m, "geometry": union}],
        crs=METRIC_CRS,
    )
    return buf_gdf


def write_preview_map(lines_wgs84: gpd.GeoDataFrame, segments_wgs84: gpd.GeoDataFrame, out_path: Path) -> None:
    try:
        import folium

        center_lat = (OKANAGAN_AOI_BBOX[1] + OKANAGAN_AOI_BBOX[3]) / 2
        center_lon = (OKANAGAN_AOI_BBOX[0] + OKANAGAN_AOI_BBOX[2]) / 2
        m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles="CartoDB positron")
        folium.GeoJson(
            mapping(box(*OKANAGAN_AOI_BBOX)),
            name="Okanagan AOI",
            style_function=lambda _: {"color": "#555", "weight": 1, "fillOpacity": 0.05},
        ).add_to(m)
        for _, row in lines_wgs84.iterrows():
            folium.GeoJson(
                mapping(row.geometry),
                style_function=lambda _: {"color": "#2980b9", "weight": 3},
            ).add_to(m)
        for _, row in segments_wgs84.head(50).iterrows():
            folium.GeoJson(
                mapping(row.geometry),
                style_function=lambda _: {"color": "#e74c3c", "weight": 2},
                tooltip=row.get("segment_id", ""),
            ).add_to(m)
        folium.LayerControl().add_to(m)
        ensure_dirs(out_path.parent)
        m.save(str(out_path))
        print(f"Wrote preview map {out_path}")
        return
    except ImportError:
        pass

    # Fallback: minimal Leaflet HTML without folium
    center_lat = (OKANAGAN_AOI_BBOX[1] + OKANAGAN_AOI_BBOX[3]) / 2
    center_lon = (OKANAGAN_AOI_BBOX[0] + OKANAGAN_AOI_BBOX[2]) / 2
    lines_geojson = json.loads(lines_wgs84.to_json())
    segs_geojson = json.loads(segments_wgs84.head(50).to_json())
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/><title>Okanagan Transmission Preview</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{height:100%;margin:0}}</style>
</head><body>
<div id="map"></div>
<script>
const map = L.map('map').setView([{center_lat}, {center_lon}], 9);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
L.geoJSON({json.dumps(lines_geojson)}, {{style: {{color:'#2980b9', weight:3}}}}).addTo(map);
L.geoJSON({json.dumps(segs_geojson)}, {{style: {{color:'#e74c3c', weight:2}}}}).addTo(map);
</script></body></html>"""
    ensure_dirs(out_path.parent)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote preview map {out_path} (Leaflet fallback)")


def main() -> int:
    args = parse_args()
    bbox = tuple(args.bbox)

    download_kml_stub(RAW_KML_DIR)
    lines = fetch_wfs_lines(bbox, args.max_features)
    lines = lines.copy()
    if "TRANSMISSION_LINE_ID" in lines.columns:
        lines["line_id"] = lines["TRANSMISSION_LINE_ID"].astype(str)
    else:
        lines["line_id"] = lines.index.astype(str)
    lines["region"] = OKANAGAN_REGION_NAME
    lines["dataset_note"] = (
        "BC Geographic Warehouse GBA_TRANSMISSION_LINES_SP — public proxy for Okanagan planning demo."
    )

    ensure_dirs(LINES_OUT.parent)
    lines_wgs84 = lines.to_crs(4326)
    lines_wgs84.to_file(LINES_OUT, driver="GeoJSON")
    print(f"Wrote {len(lines_wgs84)} lines to {LINES_OUT}")

    buffer_gdf = build_buffer(lines, args.buffer_m)
    buffer_wgs84 = buffer_gdf.to_crs(4326)
    buffer_wgs84.to_file(BUFFER_OUT, driver="GeoJSON")
    print(f"Wrote corridor buffer to {BUFFER_OUT}")

    segments = build_segments(lines, args.segment_km)
    segments_wgs84 = segments.to_crs(4326)
    segments_wgs84.to_file(SEGMENTS_OUT, driver="GeoJSON")
    print(f"Wrote {len(segments_wgs84)} segments to {SEGMENTS_OUT}")

    qa = pd.DataFrame(
        [
            {
                "as_of_date": today_iso(),
                "region": OKANAGAN_REGION_NAME,
                "bbox_wgs84": str(bbox),
                "transmission_lines_count": len(lines_wgs84),
                "segment_count": len(segments_wgs84),
                "total_length_km": round(float(segments["length_km"].sum()), 2),
                "mean_segment_km": round(float(segments["length_km"].mean()), 3),
                "buffer_m": args.buffer_m,
                "target_segment_km": args.segment_km,
                "data_source": "openmaps.gov.bc.ca WFS + KML stub",
                "notes": "Public transmission reference — not BC Hydro feeder/circuit topology.",
            }
        ]
    )
    write_csv(qa, QA_OUT)
    print(f"Wrote QA summary to {QA_OUT}")

    write_preview_map(lines_wgs84, segments_wgs84, PREVIEW_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
