"""Leaflet HTML map for Okanagan planning demo.

Streamlit's ``st.pydeck_chart`` does not reliably render deck.gl ``BitmapLayer``
overlays (WMS PNG fetches succeed but the heatmap never appears). This module
uses ``st.iframe`` with Leaflet ``L.imageOverlay`` and the same CWFIS WMS PNG
bytes fetched server-side (EPSG:4326), which displays correctly.
"""

from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import (
    OKANAGAN_CORRIDOR_BUFFER_CANDIDATES,
    OKANAGAN_CORRIDOR_BUFFER_GEOJSON,
    OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES,
    OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
)
from src.cwfis_fwi import (
    CWFIS_FWI_SOURCE_LABEL,
    fwi_risk_band_label,
    fwi_to_rgba_continuous,
)
from src.data_provenance import outage_marker_color
from src.map_geojson import load_geojson_features, resolve_bc_transmission_geojson, resolve_geojson_path
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_MAP_ZOOM, OKANAGAN_PILOT_LAT, OKANAGAN_PILOT_LON

LEAFLET_VERSION = "1.9.4"
MAP_HEIGHT_PX = 720
CARTO_POSITRON_TILE = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
_SEGMENT_POPUP_FOOTER_HTML = (
    "<div class='seg-footer'><em>Planning indicator only — not an outage prediction.</em></div>"
)


def _geojson_file_payload(path: Path) -> dict[str, Any] | None:
    features = load_geojson_features(path)
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _rgba_to_css(color: list[int] | tuple[int, ...]) -> str:
    r, g, b, a = list(color)[:4]
    alpha = a / 255.0 if a > 1 else float(a)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _color_value(raw: Any, *, default: list[int]) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return _rgba_to_css(default)
    if isinstance(raw, (list, tuple)):
        return _rgba_to_css(raw)
    if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes)):
        return _rgba_to_css(list(raw))
    return _rgba_to_css(default)


def _text_to_popup_html(text: str) -> str:
    if not text or (isinstance(text, float) and pd.isna(text)):
        return ""
    lines = [line.strip() for line in str(text).split("\n") if line.strip()]
    if not lines:
        return ""
    body = "<br/>".join(lines)
    return f'<div class="point-popup">{body}</div>'


def _fmt_num(value: Any, *, digits: int = 1, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_score(value: Any) -> str:
    return _fmt_num(value, digits=1)


_SCORE_RGB_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (46, 204, 113)),
    (50.0, (241, 196, 15)),
    (100.0, (192, 57, 43)),
)


def _score_to_rgba_continuous(value: float | None, *, alpha: int = 210) -> list[int]:
    """Smooth green→yellow→red ramp for 0–100 planning-style scores."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return [180, 180, 180, 120]
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return [180, 180, 180, 120]
    stops = _SCORE_RGB_STOPS
    if v >= stops[-1][0]:
        r, g, b = stops[-1][1]
        return [r, g, b, alpha]
    for i in range(len(stops) - 1):
        v0, c0 = stops[i]
        v1, c1 = stops[i + 1]
        if v0 <= v <= v1:
            span = v1 - v0
            t = (v - v0) / span if span > 0 else 0.0
            rgb = [int(c0[j] + t * (c1[j] - c0[j])) for j in range(3)]
            return [*rgb, alpha]
    r, g, b = stops[0][1]
    return [r, g, b, alpha]


def _segment_row_lookup(planning_df: pd.DataFrame) -> dict[str, pd.Series]:
    if planning_df.empty or "segment_id" not in planning_df.columns:
        return {}
    return {str(k): v for k, v in planning_df.set_index("segment_id", drop=False).iterrows()}


def _segment_story_html(row: pd.Series) -> str:
    """Problem story block — leads segment popups for presentation demos."""
    problem = row.get("problem_type", "")
    action = row.get("recommended_planning_action", "")
    why = row.get("explanation_short", "")
    tree_contact = row.get("tree_contact_exposure_proxy")

    lines: list[str] = []
    if problem and not pd.isna(problem):
        lines.append(f"Problem type: <strong>{problem}</strong>")
    if action and not pd.isna(action):
        lines.append(f"Suggested planning action: <strong>{action}</strong>")
    if why and not pd.isna(why):
        lines.append(f"Why: {why}")
    if tree_contact is not None and not (isinstance(tree_contact, float) and pd.isna(tree_contact)):
        lines.append(
            f"Tree contact / fall-in review proxy: <strong>{_fmt_score(tree_contact)}</strong>"
        )
    if not lines:
        return ""
    items = "".join(f"<li>{line}</li>" for line in lines)
    return f"<div class='seg-section seg-story'><ul>{items}</ul></div>"


def _segment_scenario_html(row: pd.Series) -> str:
    """Synthetic treatment scenario scores for popup storytelling."""
    scenario_cols = [
        ("Current priority", "current_priority_score"),
        ("After inspection", "scenario_after_inspection_score"),
        ("After trimming", "scenario_after_trimming_score"),
        ("After trimming + inspection", "scenario_after_trimming_and_inspection_score"),
    ]
    lines: list[str] = []
    for label, col in scenario_cols:
        if col not in row.index:
            return ""
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        lines.append(f"{label}: <strong>{_fmt_score(val)}</strong>")
    if not lines:
        return ""
    items = "".join(f"<li>{line}</li>" for line in lines)
    return (
        f"<div class='seg-section'><strong>Scenario only — synthetic treatment assumptions.</strong>"
        f"<ul>{items}</ul></div>"
    )


def _segment_popup_html(
    row: pd.Series | None,
    *,
    color_mode: str = "planning_priority_score",
    selected_date_iso: str = "",
    fwi_val: float | None = None,
) -> str:
    """Readable HTML popup for corridor segment click/hover."""
    if row is None:
        seg = "Unknown segment"
        body = "<p>No planning data for this segment.</p>"
        return f"<div class='seg-popup'><strong>{seg}</strong>{body}</div>"

    segment_id = row.get("segment_id", "")
    corridor_id = row.get("corridor_id", "")
    length_km = row.get("length_km")
    priority_level = row.get("planning_priority_level", "")
    priority_score = row.get("planning_priority_score")
    reason_1 = row.get("top_reason_1", "")
    reason_2 = row.get("top_reason_2", "")

    def section(title: str, lines: list[str]) -> str:
        items = "".join(f"<li>{line}</li>" for line in lines if line)
        if not items:
            return ""
        return f"<div class='seg-section'><strong>{title}</strong><ul>{items}</ul></div>"

    header = (
        f"<strong>{segment_id}</strong><br/>"
        f"Corridor: {corridor_id or 'n/a'} &nbsp;|&nbsp; Length: {_fmt_num(length_km, digits=2)} km"
    )

    story_html = _segment_story_html(row)
    scenario_html = _segment_scenario_html(row)

    if color_mode == "fwi":
        fwi_lines = [
            f"CWFIS FWI ({selected_date_iso or 'selected date'}): "
            f"<strong>{_fmt_num(fwi_val, digits=1)}</strong> ({fwi_risk_band_label(fwi_val)} band)",
            f"Source: {CWFIS_FWI_SOURCE_LABEL}",
        ]
        planning_lines = [
            f"Composite priority (reference): {priority_level} (score {_fmt_score(priority_score)})",
        ]
        if reason_1 and not pd.isna(reason_1):
            planning_lines.append(f"Top planning reason: {reason_1}")
        reference = "".join(
            [
                section("Fire Weather Index — segment color mode (reference)", fwi_lines),
                section("Planning priority (composite, static)", planning_lines),
            ]
        )
        return (
            f"<div class='seg-popup'>{header}{story_html}{scenario_html}{reference}"
            f"{_SEGMENT_POPUP_FOOTER_HTML}</div>"
        )

    if color_mode == "tree_contact_exposure_proxy":
        tree_val = row.get("tree_contact_exposure_proxy")
        color_lines = [
            f"Tree contact / fall-in review proxy: <strong>{_fmt_score(tree_val)}</strong>",
        ]
        quality = row.get("tree_contact_score_data_quality", "")
        if quality and not pd.isna(quality):
            color_lines.append(f"Data quality: {quality}")
        reference = section(
            "Tree contact / fall-in review proxy — segment color mode (reference)", color_lines
        )
    else:
        planning_lines = [
            f"Priority: <strong>{priority_level}</strong> (score {_fmt_score(priority_score)})",
        ]
        if reason_1 and not pd.isna(reason_1):
            planning_lines.append(f"Top reason: {reason_1}")
        if reason_2 and not pd.isna(reason_2):
            planning_lines.append(f"Also: {reason_2}")
        reference = section("Planning priority — segment color mode (reference)", planning_lines)

    vegetation_lines = [
        f"WorldCover tree cover: {_fmt_num(row.get('worldcover_tree_pct'), digits=1, suffix='%')}",
        f"WorldCover built-up: {_fmt_num(row.get('worldcover_built_pct'), digits=1, suffix='%')}",
        f"Sentinel-2 NDVI mean: {_fmt_num(row.get('sentinel2_ndvi_mean'), digits=3)}",
        f"Sentinel-2 NDMI mean: {_fmt_num(row.get('sentinel2_ndmi_mean'), digits=3)}",
        f"Cloud-filtered pixels: {_fmt_num(row.get('cloud_filtered_pct'), digits=1, suffix='%')}",
        f"Vegetation dryness score: {_fmt_score(row.get('vegetation_dryness_score'))} "
        "<em>(proxy from NDMI)</em>",
        f"Vegetation score: {_fmt_score(row.get('vegetation_score'))}",
    ]

    wildfire_lines = [
        f"Wildfire exposure score: {_fmt_score(row.get('wildfire_exposure_score'))}",
        f"Nearest active fire: {_fmt_num(row.get('nearest_fire_km'), digits=1, suffix=' km')}",
    ]

    weather_lines = [f"ECCC weather stress score: {_fmt_score(row.get('eccc_weather_stress_score'))}"]
    outage_lines = [f"Outage history proxy score: {_fmt_score(row.get('outage_history_proxy_score'))}"]
    treatment_lines = [
        f"Treatment gap score: {_fmt_score(row.get('treatment_gap_score'))} "
        "<em>(synthetic — BC Hydro work-management placeholder)</em>",
    ]

    notes = row.get("data_source_notes", "")
    notes_html = ""
    if notes and not pd.isna(notes):
        notes_html = f"<div class='seg-notes'><em>{notes}</em></div>"

    detail_sections = "".join(
        [
            reference,
            section("Vegetation & satellite", vegetation_lines),
            section("Wildfire", wildfire_lines),
            section("Weather", weather_lines),
            section("Outage history", outage_lines),
            section("Treatment gap", treatment_lines),
        ]
    )
    return (
        f"<div class='seg-popup'>{header}{story_html}{scenario_html}{detail_sections}{notes_html}"
        f"{_SEGMENT_POPUP_FOOTER_HTML}</div>"
    )


def _segment_tooltip_short(
    row: pd.Series | None,
    *,
    color_mode: str = "planning_priority_score",
    selected_date_iso: str = "",
    fwi_val: float | None = None,
) -> str:
    if row is None:
        return "Segment: unknown"
    parts = [f"Segment: {row.get('segment_id', '')}"]
    if color_mode == "fwi":
        if fwi_val is not None:
            parts.append(
                f"CWFIS FWI ({selected_date_iso or 'date'}): {_fmt_num(fwi_val, digits=1)} "
                f"({fwi_risk_band_label(fwi_val)})"
            )
        else:
            parts.append(f"CWFIS FWI ({selected_date_iso or 'date'}): n/a")
        level = row.get("planning_priority_level")
        score = row.get("planning_priority_score")
        if level and not pd.isna(level):
            parts.append(f"Planning ref.: {level} ({_fmt_score(score)})")
        return "<br>".join(parts)

    if color_mode == "tree_contact_exposure_proxy":
        proxy = row.get("tree_contact_exposure_proxy")
        if proxy is not None and not pd.isna(proxy):
            parts.append(f"Tree contact / fall-in review proxy: {_fmt_score(proxy)}")
        problem = row.get("problem_type")
        if problem and not pd.isna(problem):
            parts.append(str(problem))
        return "<br>".join(parts)

    level = row.get("planning_priority_level")
    score = row.get("planning_priority_score")
    if level and not pd.isna(level):
        parts.append(f"Priority: {level} ({_fmt_score(score)})")
    ndvi = row.get("sentinel2_ndvi_mean")
    if ndvi is not None and not pd.isna(ndvi):
        parts.append(f"NDVI: {_fmt_num(ndvi, digits=3)}")
    return "<br>".join(parts)


def _segment_geojson(
    planning_df: pd.DataFrame,
    *,
    fwi_df: pd.DataFrame | None = None,
    color_mode: str = "planning_priority_score",
    selected_date_iso: str = "",
    focus_segment_id: str | None = None,
    segments_geojson_path: Path = OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
) -> dict[str, Any] | None:
    row_lookup = _segment_row_lookup(planning_df)
    fwi_lookup: dict[str, float] = {}
    if fwi_df is not None and not fwi_df.empty and "segment_id" in fwi_df.columns:
        for seg_id, val in fwi_df.set_index("segment_id")["fwi_value"].items():
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                fwi_lookup[str(seg_id)] = float(val)

    level_colors = {
        "Critical": [192, 57, 43, 210],
        "High": [230, 126, 34, 200],
        "Medium": [241, 196, 15, 190],
        "Low": [46, 204, 113, 180],
    }
    level_lookup = (
        planning_df.set_index("segment_id")["planning_priority_level"].to_dict()
        if not planning_df.empty and "planning_priority_level" in planning_df.columns
        else {}
    )

    features: list[dict[str, Any]] = []
    for feature in load_geojson_features(segments_geojson_path):
        props = feature.get("properties") or {}
        segment_id = str(props.get("segment_id", ""))
        row = row_lookup.get(segment_id)
        fwi_val = fwi_lookup.get(segment_id)

        if color_mode == "fwi":
            color = fwi_to_rgba_continuous(fwi_val)
        elif color_mode == "tree_contact_exposure_proxy":
            proxy_val = None
            if row is not None:
                raw = row.get("tree_contact_exposure_proxy")
                if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                    proxy_val = float(raw)
            color = _score_to_rgba_continuous(proxy_val)
        else:
            level = str(level_lookup.get(segment_id, "Medium"))
            color = level_colors.get(level, [150, 150, 150, 180])

        geom = feature.get("geometry")
        if not geom:
            continue
        focused = bool(focus_segment_id and segment_id == focus_segment_id)
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "segment_id": segment_id,
                    "stroke": _rgba_to_css(color),
                    "weight": 10 if focused else 6,
                    "focused": focused,
                    "tooltip": _segment_tooltip_short(
                        row,
                        color_mode=color_mode,
                        selected_date_iso=selected_date_iso,
                        fwi_val=fwi_val if color_mode == "fwi" else None,
                    ),
                    "popup": _segment_popup_html(
                        row,
                        color_mode=color_mode,
                        selected_date_iso=selected_date_iso,
                        fwi_val=fwi_val if color_mode == "fwi" else None,
                    ),
                },
            }
        )
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _segment_priority_geojson(
    planning_df: pd.DataFrame,
    *,
    selected_date_iso: str = "",
    focus_segment_id: str | None = None,
    segments_geojson_path: Path = OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
) -> dict[str, Any] | None:
    return _segment_geojson(
        planning_df,
        color_mode="planning_priority_score",
        selected_date_iso=selected_date_iso,
        focus_segment_id=focus_segment_id,
        segments_geojson_path=segments_geojson_path,
    )


def _segment_fwi_geojson(
    fwi_df: pd.DataFrame,
    planning_df: pd.DataFrame,
    *,
    selected_date_iso: str = "",
    focus_segment_id: str | None = None,
    segments_geojson_path: Path = OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
) -> dict[str, Any] | None:
    return _segment_geojson(
        planning_df,
        fwi_df=fwi_df,
        color_mode="fwi",
        selected_date_iso=selected_date_iso,
        focus_segment_id=focus_segment_id,
        segments_geojson_path=segments_geojson_path,
    )


def _point_markers(
    df: pd.DataFrame,
    *,
    lat_col: str,
    lon_col: str,
    color: list[int] | str,
    radius: int = 7,
    tooltip_col: str | None = None,
    color_col: str | None = None,
    radius_m_col: str | None = None,
) -> list[dict[str, Any]]:
    if df.empty or lat_col not in df.columns or lon_col not in df.columns:
        return []
    default_color = color if isinstance(color, list) else [231, 76, 60, 220]
    default_css = _rgba_to_css(default_color) if isinstance(color, list) else str(color)
    markers: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        lat = row.get(lat_col)
        lon = row.get(lon_col)
        if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            continue
        css_color = _color_value(row.get(color_col) if color_col else None, default=default_color)
        tooltip = row.get(tooltip_col, "") if tooltip_col else ""
        tooltip_text = str(tooltip) if tooltip and not pd.isna(tooltip) else ""
        marker: dict[str, Any] = {
            "lat": float(lat),
            "lon": float(lon),
            "color": css_color,
            "radius": radius,
            "tooltip": tooltip_text,
            "popup": _text_to_popup_html(tooltip_text),
        }
        if radius_m_col and radius_m_col in df.columns:
            raw_radius_m = row.get(radius_m_col)
            if raw_radius_m is not None and not pd.isna(raw_radius_m):
                try:
                    marker["radiusM"] = float(raw_radius_m)
                except (TypeError, ValueError):
                    pass
        markers.append(marker)
    return markers


def _resolve_transmission_geojson(candidates: tuple[Path, ...] | None = None) -> Path:
    for path in candidates or ():
        if path.is_file():
            return path
    return resolve_bc_transmission_geojson()


def build_okanagan_leaflet_map_html(
    *,
    selected_date_iso: str,
    show_fwi_raster: bool,
    fwi_png_base64: str | None = None,
    fwi_bbox: tuple[float, float, float, float] | None = None,
    show_tx_lines: bool,
    show_buffer: bool,
    show_segments: bool,
    segment_color_mode: str,
    planning_df: pd.DataFrame,
    fwi_df: pd.DataFrame,
    fires_df: pd.DataFrame,
    archive_outages_df: pd.DataFrame,
    live_outages_df: pd.DataFrame,
    live_outages_synthetic: bool,
    center_lat: float = OKANAGAN_PILOT_LAT,
    center_lon: float = OKANAGAN_PILOT_LON,
    zoom: int = OKANAGAN_MAP_ZOOM,
    focus_segment_id: str | None = None,
    aoi_bbox: tuple[float, float, float, float] = OKANAGAN_AOI_BBOX,
    segments_geojson_path: Path = OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
    buffer_geojson_path: Path = OKANAGAN_CORRIDOR_BUFFER_GEOJSON,
    transmission_geojson_candidates: tuple[Path, ...] | None = None,
) -> str:
    """Build self-contained Leaflet HTML for ``st.iframe``."""
    if not segments_geojson_path.is_file():
        segments_geojson_path = (
            resolve_geojson_path(OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES) or segments_geojson_path
        )
    if not buffer_geojson_path.is_file():
        buffer_geojson_path = (
            resolve_geojson_path(OKANAGAN_CORRIDOR_BUFFER_CANDIDATES) or buffer_geojson_path
        )
    min_lon, min_lat, max_lon, max_lat = aoi_bbox
    fwi_bounds = None
    if fwi_bbox:
        fwi_min_lon, fwi_min_lat, fwi_max_lon, fwi_max_lat = fwi_bbox
        fwi_bounds = [[fwi_min_lat, fwi_min_lon], [fwi_max_lat, fwi_max_lon]]
    focus_center: list[float] | None = None
    if focus_segment_id:
        row = _segment_row_lookup(planning_df).get(str(focus_segment_id))
        if row is not None:
            lat = row.get("centroid_lat")
            lon = row.get("centroid_lon")
            if lat is not None and lon is not None and not pd.isna(lat) and not pd.isna(lon):
                focus_center = [float(lat), float(lon)]
    payload: dict[str, Any] = {
        "center": [center_lat, center_lon],
        "zoom": zoom,
        "aoiBounds": [[min_lat, min_lon], [max_lat, max_lon]],
        "focusSegmentId": focus_segment_id if focus_center else None,
        "focusCenter": focus_center,
        "focusZoom": 13,
        "selectedDate": selected_date_iso,
        "showFwiRaster": show_fwi_raster and bool(fwi_png_base64 and fwi_bounds),
        "fwiImageUrl": f"data:image/png;base64,{fwi_png_base64}" if fwi_png_base64 else None,
        "fwiBounds": fwi_bounds,
        "showTxLines": show_tx_lines,
        "showBuffer": show_buffer,
        "showSegments": show_segments,
        "transmissionGeoJson": None,
        "bufferGeoJson": None,
        "segmentsGeoJson": None,
        "fireMarkers": [],
        "archiveOutageMarkers": [],
        "liveOutageMarkers": [],
    }

    if show_tx_lines:
        tx_path = _resolve_transmission_geojson(transmission_geojson_candidates)
        payload["transmissionGeoJson"] = _geojson_file_payload(tx_path)
    if show_buffer:
        payload["bufferGeoJson"] = _geojson_file_payload(buffer_geojson_path)
    if show_segments:
        if segment_color_mode == "fwi":
            payload["segmentsGeoJson"] = _segment_fwi_geojson(
                fwi_df,
                planning_df,
                selected_date_iso=selected_date_iso,
                focus_segment_id=focus_segment_id,
                segments_geojson_path=segments_geojson_path,
            )
        elif segment_color_mode == "tree_contact_exposure_proxy":
            payload["segmentsGeoJson"] = _segment_geojson(
                planning_df,
                color_mode="tree_contact_exposure_proxy",
                selected_date_iso=selected_date_iso,
                focus_segment_id=focus_segment_id,
                segments_geojson_path=segments_geojson_path,
            )
        else:
            payload["segmentsGeoJson"] = _segment_priority_geojson(
                planning_df,
                selected_date_iso=selected_date_iso,
                focus_segment_id=focus_segment_id,
                segments_geojson_path=segments_geojson_path,
            )

    payload["fireMarkers"] = _point_markers(
        fires_df,
        lat_col="fire_lat",
        lon_col="fire_lon",
        color=[231, 76, 60, 220],
        color_col="fire_color",
        radius=10,
        tooltip_col="tooltip_text",
        radius_m_col="marker_radius_m",
    )
    payload["archiveOutageMarkers"] = _point_markers(
        archive_outages_df,
        lat_col="out_lat",
        lon_col="out_lon",
        color=[155, 89, 182, 220],
        radius=8,
        tooltip_col="tooltip_text",
    )
    live_color = outage_marker_color(live_outages_synthetic)
    payload["liveOutageMarkers"] = _point_markers(
        live_outages_df,
        lat_col="out_lat",
        lon_col="out_lon",
        color=live_color,
        radius=8,
        tooltip_col="tooltip_text",
    )

    config_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@{LEAFLET_VERSION}/dist/leaflet.js"></script>
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
    .leaflet-tooltip {{ white-space: pre-line; font-size: 12px; }}
    .leaflet-tooltip.wide-tooltip {{
      min-width: 260px;
      max-width: 340px;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-line;
      word-break: normal;
      overflow-wrap: anywhere;
    }}
    .leaflet-popup-content .point-popup {{
      min-width: 260px;
      max-width: 340px;
      font-size: 12px;
      line-height: 1.45;
      white-space: normal;
      word-break: normal;
      overflow-wrap: anywhere;
    }}
    .leaflet-popup-content-wrapper {{
      border-radius: 6px;
    }}
    .leaflet-popup-content {{
      margin: 10px 14px;
      min-width: 240px;
    }}
    .seg-popup {{ font-family: system-ui, sans-serif; font-size: 12px; line-height: 1.35; max-width: 340px; min-width: 240px; }}
    .seg-popup ul {{ margin: 4px 0 8px 0; padding-left: 18px; }}
    .seg-section {{ margin-top: 6px; }}
    .seg-story {{ margin-top: 4px; }}
    .seg-story ul {{ list-style: none; padding-left: 0; margin: 6px 0; }}
    .seg-story li {{ margin-bottom: 4px; }}
    .seg-notes {{ margin-top: 8px; font-size: 11px; color: #555; border-top: 1px solid #ddd; padding-top: 6px; }}
    .seg-footer {{ margin-top: 8px; font-size: 10px; color: #777; border-top: 1px solid #eee; padding-top: 4px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const cfg = {config_json};
    const map = L.map('map', {{ zoomControl: true }}).setView(cfg.center, cfg.zoom);
    L.tileLayer('{CARTO_POSITRON_TILE}', {{
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19
    }}).addTo(map);

    if (cfg.showFwiRaster && cfg.fwiImageUrl && cfg.fwiBounds) {{
      L.imageOverlay(cfg.fwiImageUrl, cfg.fwiBounds, {{
        opacity: 0.72,
        interactive: false
      }}).addTo(map);
    }}

    if (cfg.transmissionGeoJson) {{
      L.geoJSON(cfg.transmissionGeoJson, {{
        style: {{ color: '#2980b9', weight: 3, opacity: 0.85 }}
      }}).addTo(map);
    }}

    if (cfg.bufferGeoJson) {{
      L.geoJSON(cfg.bufferGeoJson, {{
        style: {{ color: '#3498db', weight: 2, fillColor: '#3498db', fillOpacity: 0.12, opacity: 0.55 }}
      }}).addTo(map);
    }}

    if (cfg.segmentsGeoJson) {{
      let focusLayer = null;
      L.geoJSON(cfg.segmentsGeoJson, {{
        style: function(feature) {{
          const p = feature.properties || {{}};
          const focused = cfg.focusSegmentId && p.segment_id === cfg.focusSegmentId;
          return {{
            color: focused ? '#111111' : (p.stroke || '#e74c3c'),
            weight: focused ? 10 : (p.weight || 5),
            opacity: focused ? 1.0 : 0.9
          }};
        }},
        onEachFeature: function(feature, layer) {{
          const p = feature.properties || {{}};
          if (p.tooltip) {{
            layer.bindTooltip(p.tooltip, {{ sticky: true, opacity: 0.95 }});
          }}
          if (p.popup) {{
            layer.bindPopup(p.popup, {{ maxWidth: 360, minWidth: 240 }});
          }}
          if (cfg.focusSegmentId && p.segment_id === cfg.focusSegmentId) {{
            focusLayer = layer;
          }}
        }}
      }}).addTo(map);
      if (focusLayer) {{
        focusLayer.bringToFront();
      }}
    }}

    function addMarkers(markers) {{
      markers.forEach(function(m) {{
        // Geographic fire extent (visual only — overlayPane, below corridor lines).
        if (m.radiusM) {{
          L.circle([m.lat, m.lon], {{
            radius: m.radiusM,
            color: m.color,
            fillColor: m.color,
            fillOpacity: 0.22,
            weight: 2,
            opacity: 0.85,
            interactive: false
          }}).addTo(map);
        }}
        // Interactive hit target on markerPane so tooltips/popups stay above segments.
        const hitRadius = m.radiusM ? Math.max(m.radius || 10, 10) : (m.radius || 7);
        const layer = L.circleMarker([m.lat, m.lon], {{
          radius: hitRadius,
          color: m.color,
          fillColor: m.color,
          fillOpacity: m.radiusM ? 0.9 : 0.85,
          weight: m.radiusM ? 2 : 1,
          opacity: 0.95
        }});
        if (m.popup) {{
          layer.bindPopup(m.popup, {{ maxWidth: 340, minWidth: 260, className: 'wide-popup' }});
        }}
        if (m.tooltip) {{
          layer.bindTooltip(m.tooltip, {{ sticky: true, opacity: 0.95, className: 'wide-tooltip' }});
        }}
        layer.addTo(map);
        layer.bringToFront();
      }});
    }}

    addMarkers(cfg.fireMarkers);
    addMarkers(cfg.archiveOutageMarkers);
    addMarkers(cfg.liveOutageMarkers);

    if (cfg.focusCenter && cfg.focusZoom) {{
      map.flyTo(cfg.focusCenter, cfg.focusZoom);
    }} else if (cfg.aoiBounds) {{
      map.fitBounds(cfg.aoiBounds, {{ padding: [12, 12] }});
    }}
  </script>
</body>
</html>"""
