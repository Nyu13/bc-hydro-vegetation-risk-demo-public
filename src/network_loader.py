from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.config import (
    BC_TRANSMISSION_BC_GEOJSON,
    BC_TRANSMISSION_GEOJSON,
    BC_TRANSMISSION_KML,
    BC_TRANSMISSION_LINES_GEOJSON,
    BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84,
    BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON,
    BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON,
    DEMO_DATA_DIR,
    DEMO_PILOT_MUNICIPALITY,
    DEMO_PILOT_TRANSMISSION_BBOX,
)
from src.data_provenance import tag_dataframe

LOGGER = logging.getLogger(__name__)

BC_TRANSMISSION_UI_LABEL = (
    "Show BC transmission lines (BC Geographic Warehouse — reference overlay)"
)


def _read_demo_corridors_csv() -> pd.DataFrame:
    try:
        return tag_dataframe(
            pd.read_csv(DEMO_DATA_DIR / "demo_corridors.csv"),
            is_synthetic=True,
            source="demo_corridors.csv (no public live corridor feed)",
        )
    except Exception as exc:
        LOGGER.error("Failed to load demo corridor data: %s", exc)
        return pd.DataFrame()


def load_transmission_lines(*, pilot_scope: bool = True) -> pd.DataFrame:
    """Demo corridor centroids; defaults to Surrey pilot rows when present."""
    df = _read_demo_corridors_csv()
    if df.empty or not pilot_scope or "municipality" not in df.columns:
        return df
    pilot_rows = df.loc[df["municipality"] == DEMO_PILOT_MUNICIPALITY]
    if not pilot_rows.empty:
        return pilot_rows.copy()
    return df


def load_all_demo_corridors() -> pd.DataFrame:
    """Full bundled demo_corridors.csv (all BC regions in the demo file)."""
    return _read_demo_corridors_csv()


def resolve_bc_transmission_geojson() -> Path | None:
    """
    Prefer local WFS exports (data/processed/) when present; else bundled Lower Mainland;
    else small demo sample for offline/legacy deploys.
    """
    if BC_TRANSMISSION_LINES_GEOJSON.exists():
        return BC_TRANSMISSION_LINES_GEOJSON
    if BC_TRANSMISSION_BC_GEOJSON.exists():
        return BC_TRANSMISSION_BC_GEOJSON
    if BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON.exists():
        return BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON
    if BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON.exists():
        return BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON
    if BC_TRANSMISSION_GEOJSON.exists():
        return BC_TRANSMISSION_GEOJSON
    return None


def bc_transmission_geojson_source() -> str:
    """Short label for UI / logging: which GeoJSON file backs the overlay."""
    path = resolve_bc_transmission_geojson()
    if path is None:
        return "unavailable"
    if path == BC_TRANSMISSION_BC_GEOJSON:
        return "processed BC-wide WFS export"
    if path == BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON:
        return "processed Lower Mainland WFS export"
    if path == BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON:
        return "bundled Lower Mainland WFS export"
    return "bundled demo sample (subset)"


def transmission_overlay_bbox(*, clip_to_pilot: bool = False) -> tuple[float, float, float, float] | None:
    """
    Optional map clip. Full exports are shown unclipped unless clip_to_pilot is requested.
    The small demo sample uses the Lower Mainland bbox so lines stay near the pilot map.
    """
    if clip_to_pilot:
        return DEMO_PILOT_TRANSMISSION_BBOX
    path = resolve_bc_transmission_geojson()
    if path == BC_TRANSMISSION_GEOJSON:
        return BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84
    return None


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
        p = _coords_to_path(coords)
        return [p] if len(p) >= 2 else []
    if gtype == "MultiLineString":
        paths = []
        for line in coords:
            p = _coords_to_path(line)
            if len(p) >= 2:
                paths.append(p)
        return paths
    return []


def _path_intersects_bbox(path: list[list[float]], bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    for lon, lat in path:
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return True
    return False


def load_bc_transmission_paths(
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> pd.DataFrame:
    geojson_path = resolve_bc_transmission_geojson()
    if geojson_path is None:
        LOGGER.warning(
            "BC transmission GeoJSON missing (expected processed, bundled LM, or demo sample under %s)",
            DEMO_DATA_DIR,
        )
        return pd.DataFrame()
    try:
        with geojson_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        LOGGER.error("Failed to read BC transmission GeoJSON %s: %s", geojson_path, exc)
        return pd.DataFrame()
    rows: list[dict] = []
    default_note = (
        "BC Geographic Warehouse transmission lines — reference overlay (not feeder GIS)."
    )
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        line_id = props.get("line_id", props.get("TRANSMISSION_LINE_ID"))
        note = props.get("dataset_note", default_note)
        for path in _geometry_to_paths(geom):
            if bbox is not None and not _path_intersects_bbox(path, bbox):
                continue
            rows.append({"path": path, "line_id": line_id, "dataset_note": note})
    if not rows:
        return pd.DataFrame()
    LOGGER.debug(
        "Loaded %s transmission path segment(s) from %s (%s)",
        len(rows),
        geojson_path.name,
        bc_transmission_geojson_source(),
    )
    return pd.DataFrame(rows)


def bc_transmission_kml_available() -> bool:
    return BC_TRANSMISSION_KML.exists()
