"""CWFIS Fire Weather Index (FWI) fetch and sampling — NRCan open data, not operational."""

from __future__ import annotations

import io
import logging
from urllib.parse import urlencode

import numpy as np

from src.outage_loader import _public_http_get

LOGGER = logging.getLogger(__name__)

CWFIS_WCS_URL = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wcs"
CWFIS_WMS_URL = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wms"
CWFIS_FWI_COVERAGE = "public:fwi"
CWFIS_FWI_LAYER = "public:fwi"
CWFIS_FWI_STYLE = "cffdrs_fwi_col"
CWFIS_FWI_SOURCE_LABEL = (
    "CWFIS Fire Weather Index (NRCan open data — illustrative context, not operational)"
)

# Approximate CWFIS cffdrs_fwi_col legend (low → extreme).
FWI_LEGEND_STOPS: tuple[tuple[str, str], ...] = (
    ("0–5", "#2ecc71"),
    ("5–10", "#f1c40f"),
    ("10–20", "#e67e22"),
    ("20–30", "#c0392b"),
    ("30+", "#8e44ad"),
)


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()[:10]


def fetch_fwi_geotiff(
    bbox: tuple[float, float, float, float],
    *,
    width: int = 400,
    height: int = 400,
    time: str | None = None,
) -> bytes | None:
    """Fetch FWI raster for WGS84 bbox via CWFIS WCS 1.0.0."""
    min_lon, min_lat, max_lon, max_lat = bbox
    params: dict[str, str] = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": CWFIS_FWI_COVERAGE,
        "format": "GeoTIFF",
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "width": str(width),
        "height": str(height),
        "crs": "EPSG:4326",
    }
    iso = _iso_date(time)
    if iso:
        params["time"] = iso
    url = f"{CWFIS_WCS_URL}?{urlencode(params)}"
    try:
        content, _ = _public_http_get(url)
        if len(content) < 500:
            return None
        return content
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("CWFIS FWI WCS fetch failed: %s", exc)
        return None


def fetch_fwi_wms_png(
    bbox: tuple[float, float, float, float],
    *,
    time: str | None = None,
    width: int = 512,
    height: int = 512,
) -> bytes | None:
    """Fetch styled FWI PNG (cffdrs_fwi_col) for pydeck BitmapLayer overlay."""
    min_lon, min_lat, max_lon, max_lat = bbox
    params: dict[str, str] = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetMap",
        "layers": CWFIS_FWI_LAYER,
        "styles": CWFIS_FWI_STYLE,
        "crs": "EPSG:4326",
        "bbox": f"{min_lat},{min_lon},{max_lat},{max_lon}",
        "width": str(width),
        "height": str(height),
        "format": "image/png",
        "transparent": "true",
    }
    iso = _iso_date(time)
    if iso:
        params["TIME"] = iso
    url = f"{CWFIS_WMS_URL}?{urlencode(params)}"
    try:
        content, _ = _public_http_get(url)
        if len(content) < 500:
            return None
        return content
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("CWFIS FWI WMS fetch failed: %s", exc)
        return None


def sample_fwi_from_geotiff(
    geotiff_bytes: bytes,
    lons: list[float] | np.ndarray,
    lats: list[float] | np.ndarray,
) -> list[float | None]:
    """Sample FWI at lon/lat points from in-memory GeoTIFF bytes."""
    try:
        import rasterio
        from rasterio.transform import rowcol
    except ImportError:
        return [None] * len(lons)

    values: list[float | None] = []
    with rasterio.open(io.BytesIO(geotiff_bytes)) as src:
        arr = src.read(1)
        nodata = src.nodata
        for lon, lat in zip(lons, lats, strict=True):
            try:
                row, col = rowcol(src.transform, float(lon), float(lat))
            except Exception:  # noqa: BLE001
                values.append(None)
                continue
            if not (0 <= row < arr.shape[0] and 0 <= col < arr.shape[1]):
                values.append(None)
                continue
            val = float(arr[row, col])
            if not np.isfinite(val):
                values.append(None)
            elif nodata is not None and val == nodata:
                values.append(None)
            elif val <= 0:
                values.append(None)
            else:
                values.append(round(val, 2))
    return values


# RGB anchors for smooth FWI segment coloring (matches CWFIS cffdrs_fwi_col stops).
_FWI_RGB_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (46, 204, 113)),
    (5.0, (241, 196, 15)),
    (10.0, (230, 126, 34)),
    (20.0, (192, 57, 43)),
    (30.0, (142, 68, 173)),
)


def fwi_to_rgba(value: float | None) -> list[int]:
    """Map FWI value to pydeck RGBA color (Canadian FWI scale approximation)."""
    if value is None or not np.isfinite(value):
        return [180, 180, 180, 120]
    if value < 5:
        return [46, 204, 113, 200]
    if value < 10:
        return [241, 196, 15, 210]
    if value < 20:
        return [230, 126, 34, 220]
    if value < 30:
        return [192, 57, 43, 230]
    return [142, 68, 173, 240]


def fwi_to_rgba_continuous(value: float | None, *, alpha: int = 220) -> list[int]:
    """Smooth green→red FWI ramp for per-segment corridor coloring."""
    if value is None or not np.isfinite(value):
        return [180, 180, 180, 120]
    v = max(0.0, float(value))
    stops = _FWI_RGB_STOPS
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


def fwi_risk_band_label(value: float | None) -> str:
    """Human-readable CWFIS-style FWI band label."""
    if value is None or not np.isfinite(value):
        return "n/a"
    if value < 5:
        return "Low"
    if value < 10:
        return "Moderate"
    if value < 20:
        return "High"
    if value < 30:
        return "Very high"
    return "Extreme"


def bbox_for_points(
    lons: list[float] | np.ndarray,
    lats: list[float] | np.ndarray,
    *,
    padding_deg: float = 0.08,
    fallback: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float, float]:
    """WGS84 bbox covering sample points with padding (for WCS GetCoverage)."""
    if len(lons) == 0 or len(lats) == 0:
        if fallback is not None:
            return fallback
        raise ValueError("bbox_for_points requires at least one lon/lat pair")
    min_lon = float(np.min(lons)) - padding_deg
    max_lon = float(np.max(lons)) + padding_deg
    min_lat = float(np.min(lats)) - padding_deg
    max_lat = float(np.max(lats)) + padding_deg
    return (min_lon, min_lat, max_lon, max_lat)


def fetch_fwi_samples(
    bbox: tuple[float, float, float, float] | None,
    lons: list[float],
    lats: list[float],
    *,
    auto_bbox: bool = False,
    fallback_bbox: tuple[float, float, float, float] | None = None,
    time: str | None = None,
) -> tuple[list[float | None], str]:
    """Fetch raster and sample FWI at points. Returns values and status label."""
    if not lons:
        return [], "empty"
    sample_bbox = bbox
    if auto_bbox or sample_bbox is None:
        sample_bbox = bbox_for_points(lons, lats, fallback=fallback_bbox)
    geotiff = fetch_fwi_geotiff(sample_bbox, time=time)
    if geotiff is None:
        return [None] * len(lons), "fetch_failed"
    values = sample_fwi_from_geotiff(geotiff, lons, lats)
    if all(v is None for v in values):
        return values, "no_valid_samples"
    return values, "cwfis_live"
