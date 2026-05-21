from __future__ import annotations

import json
import logging

import pandas as pd

from src.config import (
    BC_TRANSMISSION_GEOJSON,
    BC_TRANSMISSION_KML,
    DEMO_DATA_DIR,
)

LOGGER = logging.getLogger(__name__)

BC_TRANSMISSION_UI_LABEL = (
    "Show BC transmission lines (BC Geographic Warehouse — reference overlay)"
)


def load_transmission_lines() -> pd.DataFrame:
    try:
        df = pd.read_csv(DEMO_DATA_DIR / "demo_corridors.csv")
        return df
    except Exception as exc:
        LOGGER.error("Failed to load demo corridor data: %s", exc)
        return pd.DataFrame()


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


def load_bc_transmission_paths() -> pd.DataFrame:
    geojson_path = BC_TRANSMISSION_GEOJSON
    if not geojson_path.exists():
        LOGGER.warning("BC transmission sample missing: %s", geojson_path)
        return pd.DataFrame()
    try:
        with geojson_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        LOGGER.error("Failed to read BC transmission GeoJSON: %s", exc)
        return pd.DataFrame()
    rows: list[dict] = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        line_id = props.get("line_id", props.get("TRANSMISSION_LINE_ID"))
        note = props.get(
            "dataset_note",
            "BC Geographic Warehouse transmission lines — reference overlay (not feeder GIS).",
        )
        for path in _geometry_to_paths(geom):
            rows.append({"path": path, "line_id": line_id, "dataset_note": note})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def bc_transmission_kml_available() -> bool:
    return BC_TRANSMISSION_KML.exists()
