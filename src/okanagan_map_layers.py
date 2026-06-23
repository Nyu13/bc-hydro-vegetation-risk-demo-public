"""PyDeck map layers for Kelowna / Okanagan planning demo."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk

from src.config import (
    BC_TRANSMISSION_BC_GEOJSON,
    BC_TRANSMISSION_LINES_GEOJSON,
    OKANAGAN_CORRIDOR_BUFFER_GEOJSON,
    OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
    OKANAGAN_TRANSMISSION_LINES_GEOJSON,
)
from src.cwfis_fwi import CWFIS_FWI_SOURCE_LABEL, FWI_LEGEND_STOPS, fwi_to_rgba
from src.okanagan_temporal_map import fwi_png_to_pydeck_image
from src.data_provenance import outage_marker_color
from src.outage_loader import outage_has_polygon_row
from src.regions import (
    OKANAGAN_AOI_BBOX,
    OKANAGAN_BC_HYDRO_REGION,
    OKANAGAN_MUNICIPALITIES,
)

OKANAGAN_OUTAGE_FEED_LABEL = "BC Hydro JSON (public)"
OKANAGAN_OUTAGE_DOT_RADIUS_PX = 8

LOGGER = logging.getLogger(__name__)


def _coords_to_path(coords: list) -> list[list[float]]:
    path: list[list[float]] = []
    for pt in coords:
        if len(pt) >= 2:
            path.append([float(pt[0]), float(pt[1])])
    return path


def _geometry_to_paths(geom: dict) -> list[list[list[float]]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return []
    if gtype == "LineString":
        path = _coords_to_path(coords)
        return [path] if len(path) >= 2 else []
    if gtype == "MultiLineString":
        paths = []
        for line in coords:
            path = _coords_to_path(line)
            if len(path) >= 2:
                paths.append(path)
        return paths
    if gtype == "Polygon":
        ring = coords[0] if coords else []
        path = _coords_to_path(ring)
        return [path] if len(path) >= 3 else []
    if gtype == "MultiPolygon":
        paths = []
        for poly in coords:
            ring = poly[0] if poly else []
            path = _coords_to_path(ring)
            if len(path) >= 3:
                paths.append(path)
        return paths
    return []


def _load_geojson_features(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to read GeoJSON %s: %s", path, exc)
        return []
    return payload.get("features") or []


def _resolve_bc_transmission_geojson() -> Path:
    """Province-wide transmission lines for map context; Okanagan clip as fallback."""
    for path in (
        BC_TRANSMISSION_LINES_GEOJSON,
        BC_TRANSMISSION_BC_GEOJSON,
        OKANAGAN_TRANSMISSION_LINES_GEOJSON,
    ):
        if path.is_file():
            return path
    return BC_TRANSMISSION_LINES_GEOJSON


def bc_transmission_path_layer() -> pdk.Layer | None:
    """BC Geographic Warehouse HV transmission lines (province-wide when available)."""
    source_path = _resolve_bc_transmission_geojson()
    rows: list[dict] = []
    province_wide = source_path.name.startswith("bc_transmission_lines")
    for feature in _load_geojson_features(source_path):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        line_id = props.get("line_id", props.get("TRANSMISSION_LINE_ID", ""))
        for path in _geometry_to_paths(geom):
            rows.append(
                {
                    "path": path,
                    "line_id": line_id,
                    "tooltip_text": (
                        f"Transmission line: {line_id}\n"
                        "BC Geographic Warehouse — province-wide reference overlay"
                        if province_wide
                        else f"Transmission line: {line_id}\nPublic BC Geographic Warehouse reference"
                    ),
                }
            )
    if not rows:
        return None
    return pdk.Layer(
        "PathLayer",
        data=rows,
        get_path="path",
        get_color=[41, 128, 185, 140 if province_wide else 200],
        get_width=3 if province_wide else 4,
        width_min_pixels=1 if province_wide else 2,
        pickable=True,
    )


def okanagan_transmission_path_layer() -> pdk.Layer | None:
    """Backward-compatible alias for BC transmission overlay."""
    return bc_transmission_path_layer()


def okanagan_buffer_geojson_layer() -> pdk.Layer | None:
    """200 m corridor buffer polygons."""
    features = _load_geojson_features(OKANAGAN_CORRIDOR_BUFFER_GEOJSON)
    if not features:
        return None
    return pdk.Layer(
        "GeoJsonLayer",
        data={"type": "FeatureCollection", "features": features},
        filled=True,
        stroked=True,
        get_fill_color=[52, 152, 219, 35],
        get_line_color=[52, 152, 219, 120],
        get_line_width=2,
        line_width_min_pixels=1,
        pickable=False,
    )


def _normalize_outage_coords(outage_df: pd.DataFrame) -> pd.DataFrame:
    if outage_df.empty:
        return outage_df
    frame = outage_df.copy()
    if not {"out_lat", "out_lon"}.issubset(frame.columns):
        if {"latitude", "longitude"}.issubset(frame.columns):
            frame["out_lat"] = pd.to_numeric(frame["latitude"], errors="coerce")
            frame["out_lon"] = pd.to_numeric(frame["longitude"], errors="coerce")
        else:
            frame["out_lat"] = pd.NA
            frame["out_lon"] = pd.NA
    else:
        frame["out_lat"] = pd.to_numeric(frame["out_lat"], errors="coerce")
        frame["out_lon"] = pd.to_numeric(frame["out_lon"], errors="coerce")
    return frame


def _coord_in_okanagan_bbox(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _outage_geometry_in_bbox(feature: object, bbox: tuple[float, float, float, float]) -> bool:
    if not isinstance(feature, dict):
        return False
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        return False
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    min_lon, min_lat, max_lon, max_lat = bbox
    points: list[tuple[float, float]] = []

    def _collect_pairs(values: object) -> None:
        if not isinstance(values, list):
            return
        if len(values) >= 2 and all(isinstance(v, (int, float)) for v in values[:2]):
            points.append((float(values[0]), float(values[1])))
            return
        for item in values:
            _collect_pairs(item)

    if gtype in {"Polygon", "MultiPolygon"} and isinstance(coords, list):
        _collect_pairs(coords)
    if not points:
        return False
    return any(min_lon <= lon <= max_lon and min_lat <= lat <= max_lat for lon, lat in points)


def _okanagan_place_match(row: pd.Series) -> bool:
    region = str(row.get("region", "") or "").strip().casefold()
    target_region = OKANAGAN_BC_HYDRO_REGION.casefold()
    if region == target_region or target_region in region:
        return True
    municipality = str(row.get("municipality", "") or "").strip().casefold()
    if not municipality:
        return False
    return any(municipality == place.casefold() or place.casefold() in municipality for place in OKANAGAN_MUNICIPALITIES)


def filter_outages_for_okanagan_map(outage_df: pd.DataFrame) -> pd.DataFrame:
    """Keep live JSON rows whose coordinates or labels fall in the Okanagan AOI."""
    if outage_df.empty:
        return outage_df
    frame = _normalize_outage_coords(outage_df)
    keep_idx: list[Any] = []
    for idx, row in frame.iterrows():
        lat = row.get("out_lat")
        lon = row.get("out_lon")
        if pd.notna(lat) and pd.notna(lon):
            try:
                if _coord_in_okanagan_bbox(float(lat), float(lon)):
                    keep_idx.append(idx)
                    continue
            except (TypeError, ValueError):
                pass
        if "outage_geojson" in frame.columns and _outage_geometry_in_bbox(
            row.get("outage_geojson"), OKANAGAN_AOI_BBOX
        ):
            keep_idx.append(idx)
            continue
        if _okanagan_place_match(row):
            keep_idx.append(idx)
    return frame.loc[keep_idx].copy()


def _outage_dot_radius_px(point_count: int) -> int:
    if point_count <= 1:
        return 14
    if point_count <= 5:
        return 11
    if point_count <= 15:
        return 9
    return OKANAGAN_OUTAGE_DOT_RADIUS_PX


def _outage_tooltip_lines(row: pd.Series, *, feed_label: str = OKANAGAN_OUTAGE_FEED_LABEL) -> str:
    lines: list[str] = []
    outage_id = row.get("outage_id", "")
    if outage_id is not None and str(outage_id).strip():
        lines.append(f"Outage: {outage_id}")
    if feed_label:
        lines.append(f"Source: {feed_label}")
    area = row.get("area") or row.get("area_text") or ""
    if area is not None and str(area).strip():
        lines.append(f"Area: {area}")
    for label, key in (
        ("Municipality", "municipality"),
        ("Customers", "customers_affected"),
        ("Cause", "cause"),
        ("Status", "status"),
        ("Updated", "updated"),
    ):
        value = row.get(key, row.get("timestamp", "")) if key == "updated" else row.get(key, "")
        if value is not None and str(value).strip():
            lines.append(f"{label}: {value}")
    if not any(line.startswith("Updated:") for line in lines):
        ts = row.get("timestamp", "")
        if ts is not None and str(ts).strip():
            lines.append(f"Updated: {ts}")
    return "\n".join(lines)


def prepare_okanagan_outage_map_points(outage_df: pd.DataFrame) -> pd.DataFrame:
    """Point-only rows for Okanagan ScatterplotLayer (centroids when polygon-only)."""
    if outage_df.empty:
        return outage_df
    frame = _normalize_outage_coords(outage_df)
    point_rows = frame.loc[~frame.apply(outage_has_polygon_row, axis=1)]
    if point_rows.empty:
        point_rows = frame
    points = point_rows.dropna(subset=["out_lat", "out_lon"]).copy()
    if points.empty:
        return points
    points["tooltip_text"] = points.apply(_outage_tooltip_lines, axis=1)
    return points


def okanagan_outage_scatter_layer(points_df: pd.DataFrame, *, is_synthetic: bool) -> pdk.Layer | None:
    """Live public outage markers for the Okanagan planning map."""
    if points_df.empty:
        return None
    radius = _outage_dot_radius_px(len(points_df))
    return pdk.Layer(
        "ScatterplotLayer",
        data=points_df,
        get_position=["out_lon", "out_lat"],
        get_fill_color=outage_marker_color(is_synthetic),
        get_radius=radius,
        radius_units="pixels",
        radius_min_pixels=radius,
        radius_max_pixels=radius,
        auto_highlight=True,
        pickable=True,
    )


def okanagan_segment_priority_path_layer(planning_df: pd.DataFrame) -> pdk.Layer | None:
    """Corridor segments colored by planning priority level."""
    if planning_df.empty or "segment_id" not in planning_df.columns:
        return None
    score_lookup = planning_df.set_index("segment_id")["planning_priority_score"].to_dict()
    level_lookup = planning_df.set_index("segment_id")["planning_priority_level"].to_dict()
    reason_lookup = (
        planning_df.set_index("segment_id")["top_reason_1"].to_dict()
        if "top_reason_1" in planning_df.columns
        else {}
    )
    level_colors = {
        "Critical": [192, 57, 43, 210],
        "High": [230, 126, 34, 200],
        "Medium": [241, 196, 15, 190],
        "Low": [46, 204, 113, 180],
    }
    rows: list[dict] = []
    for feature in _load_geojson_features(OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON):
        props = feature.get("properties") or {}
        segment_id = props.get("segment_id", "")
        level = str(level_lookup.get(segment_id, "Medium"))
        score = score_lookup.get(segment_id)
        color = level_colors.get(level, [150, 150, 150, 180])
        geom = feature.get("geometry") or {}
        for path in _geometry_to_paths(geom):
            rows.append(
                {
                    "path": path,
                    "segment_id": segment_id,
                    "segment_color": color,
                    "tooltip_text": "\n".join(
                        [
                            f"Segment: {segment_id}",
                            f"Priority: {level} ({score})",
                            f"Top reason: {reason_lookup.get(segment_id, '')}",
                        ]
                    ),
                }
            )
    if not rows:
        return None
    return pdk.Layer(
        "PathLayer",
        data=rows,
        get_path="path",
        get_color="segment_color",
        get_width=6,
        width_min_pixels=3,
        pickable=True,
    )


def okanagan_segment_fwi_path_layer(fwi_df: pd.DataFrame) -> pdk.Layer | None:
    """Corridor segments colored by sampled CWFIS FWI."""
    if fwi_df.empty or "segment_id" not in fwi_df.columns:
        return None

    fwi_lookup = fwi_df.set_index("segment_id")["fwi_value"].to_dict()
    rows: list[dict] = []
    for feature in _load_geojson_features(OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON):
        props = feature.get("properties") or {}
        segment_id = props.get("segment_id", "")
        raw_val = fwi_lookup.get(segment_id)
        fwi_val = None if raw_val is None or (isinstance(raw_val, float) and pd.isna(raw_val)) else float(raw_val)
        color = fwi_to_rgba(fwi_val)
        fwi_text = f"{fwi_val:.1f}" if fwi_val is not None else "n/a"
        geom = feature.get("geometry") or {}
        for path in _geometry_to_paths(geom):
            rows.append(
                {
                    "path": path,
                    "segment_id": segment_id,
                    "fwi_color": color,
                    "tooltip_text": (
                        f"Segment: {segment_id}\n"
                        f"CWFIS FWI: {fwi_text}\n"
                        f"{CWFIS_FWI_SOURCE_LABEL}"
                    ),
                }
            )
    if not rows:
        return None
    return pdk.Layer(
        "PathLayer",
        data=rows,
        get_path="path",
        get_color="fwi_color",
        get_width=6,
        width_min_pixels=3,
        pickable=True,
    )


def okanagan_outage_proxy_scatter_layer(proxy_df: pd.DataFrame) -> pdk.Layer | None:
    """Municipality-centroid outage archive proxy markers."""
    if proxy_df.empty:
        return None
    return pdk.Layer(
        "ScatterplotLayer",
        data=proxy_df,
        get_position=["lon", "lat"],
        get_fill_color="outage_color",
        get_radius="marker_radius_m",
        pickable=True,
    )


def okanagan_fwi_bitmap_layer(
    png_bytes: bytes,
    bbox: tuple[float, float, float, float],
    *,
    opacity: float = 0.72,
) -> pdk.Layer:
    """CWFIS-style FWI raster overlay (WMS cffdrs_fwi_col PNG)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return pdk.Layer(
        "BitmapLayer",
        data=None,
        image=fwi_png_to_pydeck_image(png_bytes),
        bounds=[min_lon, min_lat, max_lon, max_lat],
        opacity=opacity,
        pickable=False,
    )


def okanagan_fire_scatter_layer(fires_df: pd.DataFrame) -> pdk.Layer | None:
    """BC wildland fire points active on the selected map date."""
    if fires_df.empty:
        return None
    return pdk.Layer(
        "ScatterplotLayer",
        data=fires_df,
        get_position=["fire_lon", "fire_lat"],
        get_fill_color="fire_color",
        get_radius="marker_radius_m",
        radius_min_pixels=6,
        radius_max_pixels=24,
        pickable=True,
    )


OKANAGAN_ARCHIVE_OUTAGE_COLOR = [155, 89, 182, 220]


def okanagan_archive_outage_scatter_layer(outages_df: pd.DataFrame) -> pdk.Layer | None:
    """Unofficial outage archive points for the selected map date."""
    if outages_df.empty:
        return None
    frame = outages_df.copy()
    if "outage_color" not in frame.columns:
        frame["outage_color"] = [OKANAGAN_ARCHIVE_OUTAGE_COLOR] * len(frame)
    radius = _outage_dot_radius_px(len(frame))
    return pdk.Layer(
        "ScatterplotLayer",
        data=frame,
        get_position=["out_lon", "out_lat"],
        get_fill_color="outage_color",
        get_radius=radius,
        radius_units="pixels",
        radius_min_pixels=radius,
        radius_max_pixels=radius,
        auto_highlight=True,
        pickable=True,
    )


def fwi_legend_html(*, continuous: bool = False) -> str:
    """Compact HTML legend matching CWFIS FWI color ramp."""
    stops = "".join(
        f'<span style="display:inline-block;width:42px;height:14px;background:{color};"></span>'
        for _, color in FWI_LEGEND_STOPS
    )
    labels = "".join(
        f'<span style="font-size:0.75rem;margin-right:6px;">{label}</span>'
        for label, _ in FWI_LEGEND_STOPS
    )
    ramp_note = (
        "Segment lines use a continuous FWI ramp (sampled at each centroid for the selected date)."
        if continuous
        else "FWI (low → extreme)"
    )
    return (
        f'<div style="margin:4px 0 8px 0;">'
        f'<div style="font-size:0.8rem;margin-bottom:2px;">{ramp_note}</div>'
        f'<div>{stops}</div>'
        f'<div style="margin-top:2px;">{labels}</div>'
        f"</div>"
    )


def planning_priority_legend_html() -> str:
    """HTML legend for composite planning priority level buckets."""
    levels = (
        ("Critical", "#c0392b"),
        ("High", "#e67e22"),
        ("Medium", "#f1c40f"),
        ("Low", "#2ecc71"),
    )
    stops = "".join(
        f'<span style="display:inline-block;width:42px;height:14px;background:{color};"></span>'
        for _, color in levels
    )
    labels = "".join(
        f'<span style="font-size:0.75rem;margin-right:6px;">{label}</span>'
        for label, _ in levels
    )
    return (
        f'<div style="margin:4px 0 8px 0;">'
        f'<div style="font-size:0.8rem;margin-bottom:2px;">'
        f"Planning priority (composite score: vegetation + wildfire + weather + treatment + outage)"
        f"</div>"
        f"<div>{stops}</div>"
        f'<div style="margin-top:2px;">{labels}</div>'
        f"</div>"
    )
