from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.config import (
    DEMO_DATA_DIR,
    MONTREAL_TRANSMISSION_GEOJSON,
    MONTREAL_TRANSMISSION_GPKG,
)

LOGGER = logging.getLogger(__name__)

MONTREAL_TRANSMISSION_LAYER = "carto_ser_ele_tel_aerien"
MONTREAL_TRANSMISSION_UI_LABEL = (
    "Show Montréal HV transmission lines (Ville de Montréal 2020 — Québec, not BC)"
)


def load_transmission_lines() -> pd.DataFrame:
    """
    Load demo corridor segments derived from public transmission-line proxy.
    """
    try:
        df = pd.read_csv(DEMO_DATA_DIR / "demo_corridors.csv")
        return df
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to load demo corridor data: %s", exc)
        return pd.DataFrame()


def _coords_to_path(coords: list) -> list[list[float]]:
    """GeoJSON coordinate list -> pydeck path [[lon, lat], ...]."""
    path: list[list[float]] = []
    for pt in coords:
        if len(pt) >= 2:
            path.append([float(pt[0]), float(pt[1])])
    return path


def _geometry_to_paths(geom: dict) -> list[list[list[float]]]:
    """Split MultiLineString / LineString into pydeck path lists."""
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


def load_montreal_transmission_paths() -> pd.DataFrame:
    """
    Load bundled Montréal metro HV line paths for optional map overlay.

    Returns DataFrame columns: path (list of [lon, lat]), line_id, dataset_note.
    Geographic coverage: Montréal CMM 2020 photogrammetry — not BC Hydro assets.
    """
    geojson_path = MONTREAL_TRANSMISSION_GEOJSON
    if not geojson_path.exists():
        LOGGER.warning("Montréal transmission sample missing: %s", geojson_path)
        return pd.DataFrame()

    try:
        with geojson_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to read Montréal transmission GeoJSON: %s", exc)
        return pd.DataFrame()

    rows: list[dict] = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        line_id = props.get("line_id", props.get("ID"))
        note = props.get(
            "dataset_note",
            "Ville de Montréal 2020 — Montréal metro only (not BC Hydro).",
        )
        for path in _geometry_to_paths(geom):
            rows.append({"path": path, "line_id": line_id, "dataset_note": note})

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def montreal_transmission_gpkg_available() -> bool:
    return MONTREAL_TRANSMISSION_GPKG.exists()


def export_montreal_transmission_sample_from_gpkg(
    *,
    gpkg_path: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """
    Regenerate bundled demo GeoJSON from a local GPKG (developer utility).
    """
    import geopandas as gpd

    src = gpkg_path or MONTREAL_TRANSMISSION_GPKG
    dest = out_path or MONTREAL_TRANSMISSION_GEOJSON
    if not src.exists():
        raise FileNotFoundError(src)

    gdf = gpd.read_file(src, layer=MONTREAL_TRANSMISSION_LAYER)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:2950")
    gdf = gdf.to_crs(4326)
    if "ID" in gdf.columns:
        gdf = gdf.rename(columns={"ID": "line_id"})
    keep = [c for c in ("line_id", "SOURCE", "DIFFUSEUR", "VERSION") if c in gdf.columns]
    gdf = gdf[keep + ["geometry"]]
    gdf["dataset_note"] = (
        "Ville de Montréal open data 2020 — aerial HV lines (Montréal metro only, not BC Hydro)."
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(dest, driver="GeoJSON")
    return dest
