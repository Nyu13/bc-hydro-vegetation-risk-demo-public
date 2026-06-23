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
    OKANAGAN_CORRIDOR_BUFFER_GEOJSON,
    OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON,
)
from src.cwfis_fwi import (
    CWFIS_FWI_SOURCE_LABEL,
    fwi_risk_band_label,
    fwi_to_rgba_continuous,
)
from src.okanagan_map_layers import (
    _load_geojson_features,
    _resolve_bc_transmission_geojson,
    outage_marker_color,
)
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_MAP_ZOOM, OKANAGAN_PILOT_LAT, OKANAGAN_PILOT_LON

LEAFLET_VERSION = "1.9.4"
MAP_HEIGHT_PX = 520
CARTO_POSITRON_TILE = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"


def _geojson_file_payload(path: Path) -> dict[str, Any] | None:
    features = _load_geojson_features(path)
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def _rgba_to_css(color: list[int]) -> str:
    r, g, b, a = color[:4]
    alpha = a / 255.0 if a > 1 else float(a)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _fmt_num(value: Any, *, digits: int = 1, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_score(value: Any) -> str:
    return _fmt_num(value, digits=1)


def _segment_row_lookup(planning_df: pd.DataFrame) -> dict[str, pd.Series]:
    if planning_df.empty or "segment_id" not in planning_df.columns:
        return {}
    return {str(k): v for k, v in planning_df.set_index("segment_id", drop=False).iterrows()}


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
        sections = "".join(
            [
                section("Fire Weather Index — segment color mode", fwi_lines),
                section("Planning priority (composite, static)", planning_lines),
            ]
        )
        return f"<div class='seg-popup'>{header}{sections}</div>"

    planning_lines = [
        f"Priority: <strong>{priority_level}</strong> (score {_fmt_score(priority_score)})",
    ]
    if reason_1 and not pd.isna(reason_1):
        planning_lines.append(f"Top reason: {reason_1}")
    if reason_2 and not pd.isna(reason_2):
        planning_lines.append(f"Also: {reason_2}")

    satellite_lines = [
        f"NDVI mean: {_fmt_num(row.get('sentinel2_ndvi_mean'), digits=3)}",
        f"NDMI mean: {_fmt_num(row.get('sentinel2_ndmi_mean'), digits=3)}",
        f"Cloud-filtered pixels: {_fmt_num(row.get('cloud_filtered_pct'), digits=1, suffix='%')}",
        f"Status: {row.get('vegetation_data_status', 'n/a')}",
        "Source: open/free Sentinel-2 L2A processed locally",
    ]

    vegetation_lines = [
        f"WorldCover tree cover: {_fmt_num(row.get('worldcover_tree_pct'), digits=1, suffix='%')}",
        f"WorldCover built-up: {_fmt_num(row.get('worldcover_built_pct'), digits=1, suffix='%')}",
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

    sections = "".join(
        [
            section("Planning priority — segment color mode", planning_lines),
            section("Satellite (Sentinel-2 L2A)", satellite_lines),
            section("Vegetation", vegetation_lines),
            section("Wildfire", wildfire_lines),
            section("Weather", weather_lines),
            section("Outage history", outage_lines),
            section("Treatment gap", treatment_lines),
        ]
    )
    return f"<div class='seg-popup'>{header}{sections}{notes_html}</div>"


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
    for feature in _load_geojson_features(OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON):
        props = feature.get("properties") or {}
        segment_id = str(props.get("segment_id", ""))
        row = row_lookup.get(segment_id)
        fwi_val = fwi_lookup.get(segment_id)

        if color_mode == "fwi":
            color = fwi_to_rgba_continuous(fwi_val)
        else:
            level = str(level_lookup.get(segment_id, "Medium"))
            color = level_colors.get(level, [150, 150, 150, 180])

        geom = feature.get("geometry")
        if not geom:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "segment_id": segment_id,
                    "stroke": _rgba_to_css(color),
                    "weight": 6,
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


def _segment_priority_geojson(planning_df: pd.DataFrame, *, selected_date_iso: str = "") -> dict[str, Any] | None:
    return _segment_geojson(
        planning_df,
        color_mode="planning_priority_score",
        selected_date_iso=selected_date_iso,
    )


def _segment_fwi_geojson(
    fwi_df: pd.DataFrame,
    planning_df: pd.DataFrame,
    *,
    selected_date_iso: str = "",
) -> dict[str, Any] | None:
    return _segment_geojson(
        planning_df,
        fwi_df=fwi_df,
        color_mode="fwi",
        selected_date_iso=selected_date_iso,
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
) -> list[dict[str, Any]]:
    if df.empty or lat_col not in df.columns or lon_col not in df.columns:
        return []
    default_css = _rgba_to_css(color) if isinstance(color, list) else str(color)
    markers: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        lat = row.get(lat_col)
        lon = row.get(lon_col)
        if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
            continue
        if color_col and color_col in df.columns and row.get(color_col) is not None:
            raw = row[color_col]
            css_color = _rgba_to_css(raw) if isinstance(raw, list) else default_css
        else:
            css_color = default_css
        tooltip = row.get(tooltip_col, "") if tooltip_col else ""
        markers.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "color": css_color,
                "radius": radius,
                "tooltip": str(tooltip) if tooltip and not pd.isna(tooltip) else "",
            }
        )
    return markers


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
) -> str:
    """Build self-contained Leaflet HTML for ``st.iframe``."""
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    fwi_bounds = None
    if fwi_bbox:
        fwi_min_lon, fwi_min_lat, fwi_max_lon, fwi_max_lat = fwi_bbox
        fwi_bounds = [[fwi_min_lat, fwi_min_lon], [fwi_max_lat, fwi_max_lon]]
    payload: dict[str, Any] = {
        "center": [center_lat, center_lon],
        "zoom": zoom,
        "aoiBounds": [[min_lat, min_lon], [max_lat, max_lon]],
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
        tx_path = _resolve_bc_transmission_geojson()
        payload["transmissionGeoJson"] = _geojson_file_payload(tx_path)
    if show_buffer:
        payload["bufferGeoJson"] = _geojson_file_payload(OKANAGAN_CORRIDOR_BUFFER_GEOJSON)
    if show_segments:
        if segment_color_mode == "fwi":
            payload["segmentsGeoJson"] = _segment_fwi_geojson(
                fwi_df, planning_df, selected_date_iso=selected_date_iso
            )
        else:
            payload["segmentsGeoJson"] = _segment_priority_geojson(
                planning_df, selected_date_iso=selected_date_iso
            )

    payload["fireMarkers"] = _point_markers(
        fires_df,
        lat_col="fire_lat",
        lon_col="fire_lon",
        color=[231, 76, 60, 220],
        color_col="fire_color",
        radius=8,
    )
    payload["archiveOutageMarkers"] = _point_markers(
        archive_outages_df,
        lat_col="out_lat",
        lon_col="out_lon",
        color=[155, 89, 182, 220],
        radius=7,
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
    .seg-popup {{ font-family: system-ui, sans-serif; font-size: 12px; line-height: 1.35; max-width: 340px; }}
    .seg-popup ul {{ margin: 4px 0 8px 0; padding-left: 18px; }}
    .seg-section {{ margin-top: 6px; }}
    .seg-notes {{ margin-top: 8px; font-size: 11px; color: #555; border-top: 1px solid #ddd; padding-top: 6px; }}
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
      L.geoJSON(cfg.segmentsGeoJson, {{
        style: function(feature) {{
          const p = feature.properties || {{}};
          return {{ color: p.stroke || '#e74c3c', weight: p.weight || 5, opacity: 0.9 }};
        }},
        onEachFeature: function(feature, layer) {{
          const p = feature.properties || {{}};
          if (p.tooltip) {{
            layer.bindTooltip(p.tooltip, {{ sticky: true, opacity: 0.95 }});
          }}
          if (p.popup) {{
            layer.bindPopup(p.popup, {{ maxWidth: 360, minWidth: 240 }});
          }}
        }}
      }}).addTo(map);
    }}

    function addMarkers(markers) {{
      markers.forEach(function(m) {{
        const circle = L.circleMarker([m.lat, m.lon], {{
          radius: m.radius || 7,
          color: m.color,
          fillColor: m.color,
          fillOpacity: 0.85,
          weight: 1
        }});
        if (m.tooltip) circle.bindTooltip(m.tooltip);
        circle.addTo(map);
      }});
    }}

    addMarkers(cfg.fireMarkers);
    addMarkers(cfg.archiveOutageMarkers);
    addMarkers(cfg.liveOutageMarkers);

    if (cfg.aoiBounds) {{
      map.fitBounds(cfg.aoiBounds, {{ padding: [12, 12] }});
    }}
  </script>
</body>
</html>"""
