"""Lightweight GeoJSON + pydeck helpers shared by leaflet and pydeck map modules."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from pydeck.types import String

from src.config import BC_TRANSMISSION_LINES_GEOJSON, BC_TRANSMISSION_OVERLAY_CANDIDATES

LOGGER = logging.getLogger(__name__)


def load_geojson_features(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to read GeoJSON %s: %s", path, exc)
        return []
    return payload.get("features") or []


def resolve_bc_transmission_geojson() -> Path:
    """Province-wide transmission lines for map context (no region AOI clip)."""
    for path in BC_TRANSMISSION_OVERLAY_CANDIDATES:
        if path.is_file():
            return path
    return BC_TRANSMISSION_LINES_GEOJSON


def fwi_png_to_pydeck_image(png_bytes: bytes) -> String:
    """Encode WMS PNG for pydeck BitmapLayer (base64 data URL, not raw ndarray)."""
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return String(f"data:image/png;base64,{encoded}", quote_type='"')
