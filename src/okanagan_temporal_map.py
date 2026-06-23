"""Date-scoped map data for Kelowna / Okanagan demo (FWI raster, fires, outage archive)."""

from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urlencode

import pandas as pd
from pydeck.types import String

from src.cwfis_fwi import (
    CWFIS_FWI_SOURCE_LABEL,
    fetch_fwi_wms_png,
)
from src.outage_loader import _public_http_get
from src.region_history_loader import _load_history_parquet
from src.regions import (
    OKANAGAN_AOI_BBOX,
    OKANAGAN_BC_HYDRO_REGION,
    OKANAGAN_HISTORY_START_DATE,
)

LOGGER = logging.getLogger(__name__)

CWFIF_WFS = "https://geoserver.cwfif.nrcan.gc.ca/geoserver/ows"
CWFIF_ACTIVE_LAYER = "public:cwfif_national_activefires"
OKANAGAN_OUTAGE_ARCHIVE_LABEL = (
    "Unofficial BC Hydro public outage archive proxy — not operational history"
)
CWFIF_FIRE_SOURCE_LABEL = "CWFIF WFS public:cwfif_national_activefires (BC, date-filtered)"


def okanagan_map_date_bounds() -> tuple[date, date, date]:
    """Return (min_date, max_date, default_date) for the 2026 temporal map picker."""
    min_date = datetime.strptime(OKANAGAN_HISTORY_START_DATE, "%Y-%m-%d").date()
    today = date.today()
    cap = min(today, date(2026, 12, 31))
    max_date = cap
    history = _load_history_parquet()
    if history is not None and not history.empty:
        ok = _filter_okanagan_history(history)
        if not ok.empty and "snapshot_date" in ok.columns:
            parsed = pd.to_datetime(ok["snapshot_date"], errors="coerce").dropna()
            if not parsed.empty:
                archive_max = parsed.max().date()
                max_date = min(cap, archive_max)
    default_date = min(today, max_date) if today.year == 2026 else max_date
    if default_date < min_date:
        default_date = min_date
    return min_date, max_date, default_date


def _filter_okanagan_history(history: pd.DataFrame) -> pd.DataFrame:
    region_col = "region_name" if "region_name" in history.columns else "region"
    if region_col not in history.columns:
        return pd.DataFrame()
    work = history.loc[history[region_col].astype(str) == OKANAGAN_BC_HYDRO_REGION].copy()
    if "municipality" not in work.columns:
        return pd.DataFrame()
    work["municipality"] = work["municipality"].astype(str).str.strip()
    return work.loc[work["municipality"].str.len() > 0]


def _parse_outage_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    text = str(value).strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def _nearest_snapshot_date(history_df: pd.DataFrame, scene_date: str) -> str | None:
    dates = sorted(history_df["snapshot_date"].dropna().astype(str).unique())
    prior = [d for d in dates if d <= scene_date]
    if prior:
        return prior[-1]
    return dates[0] if dates else None


def _outage_rows_for_scene_date(history_df: pd.DataFrame, scene_date: str) -> tuple[pd.DataFrame, str]:
    """Snapshot on scene_date, else nearest snapshot with outages active on scene_date."""
    if "snapshot_date" not in history_df.columns:
        return pd.DataFrame(), "missing_snapshot_date"
    exact = history_df[history_df["snapshot_date"].astype(str) == scene_date]
    if not exact.empty:
        subset = exact.drop_duplicates(subset=["outage_id"], keep="last")
        return subset, "snapshot_exact"

    snap_date = _nearest_snapshot_date(history_df, scene_date)
    if snap_date is None:
        return pd.DataFrame(), "no_snapshot_dates"

    day_start = pd.Timestamp(f"{scene_date}T00:00:00+00:00")
    day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    snap = history_df[history_df["snapshot_date"].astype(str) == snap_date].drop_duplicates(
        subset=["outage_id"], keep="last"
    )
    active_rows: list[pd.Series] = []
    for _, row in snap.iterrows():
        off = _parse_outage_timestamp(row.get("date_off"))
        on = _parse_outage_timestamp(row.get("date_on"))
        if off is None:
            continue
        if off <= day_end and (on is None or on >= day_start):
            active_rows.append(row)
    if active_rows:
        return pd.DataFrame(active_rows), f"snapshot_nearest_active:{snap_date}"
    return pd.DataFrame(), f"snapshot_nearest_no_active:{snap_date}"


def _coord_in_okanagan_bbox(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _outage_archive_tooltip(row: pd.Series, *, match_status: str) -> str:
    lines = [
        f"Outage: {row.get('outage_id', '')}",
        f"Source: {OKANAGAN_OUTAGE_ARCHIVE_LABEL}",
        f"Archive match: {match_status}",
    ]
    for label, key in (
        ("Municipality", "municipality"),
        ("Area", "area"),
        ("Customers", "num_customers_out"),
        ("Cause", "cause"),
        ("Date off", "date_off"),
        ("Date on", "date_on"),
    ):
        value = row.get(key, "")
        if value is not None and str(value).strip():
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def load_outages_for_date(selected_date: date | str) -> tuple[pd.DataFrame, str]:
    """Point outages from unofficial archive for Okanagan/Kootenay on selected date."""
    history = _load_history_parquet()
    if history is None or history.empty:
        return pd.DataFrame(), "archive_missing"

    ok = _filter_okanagan_history(history)
    if ok.empty:
        return pd.DataFrame(), "archive_no_okanagan_rows"

    scene_date = selected_date.isoformat() if isinstance(selected_date, date) else str(selected_date)[:10]
    rows, status = _outage_rows_for_scene_date(ok, scene_date)
    if rows.empty:
        return pd.DataFrame(), status

    points = rows.copy()
    points["out_lat"] = pd.to_numeric(points.get("latitude"), errors="coerce")
    points["out_lon"] = pd.to_numeric(points.get("longitude"), errors="coerce")
    points = points.dropna(subset=["out_lat", "out_lon"])
    if points.empty:
        return pd.DataFrame(), f"{status}_no_coordinates"

    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    points = points.loc[
        (points["out_lat"] >= min_lat)
        & (points["out_lat"] <= max_lat)
        & (points["out_lon"] >= min_lon)
        & (points["out_lon"] <= max_lon)
    ].copy()
    if points.empty:
        return pd.DataFrame(), f"{status}_outside_aoi"

    points["tooltip_text"] = points.apply(
        lambda row: _outage_archive_tooltip(row, match_status=status),
        axis=1,
    )
    return points, status


def _fire_tooltip(props: dict[str, Any]) -> str:
    lines = [
        f"Fire: {props.get('agency_fire_id') or props.get('national_fire_id', '')}",
        f"Source: {CWFIF_FIRE_SOURCE_LABEL}",
    ]
    for label, key in (
        ("Size (ha)", "fire_size"),
        ("Contained %", "percent_contained"),
        ("Cause", "national_fire_cause"),
        ("Start", "record_start"),
        ("End", "record_end"),
    ):
        value = props.get(key, "")
        if value is not None and str(value).strip():
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def load_fires_for_date(selected_date: date | str) -> tuple[pd.DataFrame, str]:
    """BC wildland fires active on selected date from CWFIF WFS."""
    scene_date = selected_date.isoformat() if isinstance(selected_date, date) else str(selected_date)[:10]
    ts = f"{scene_date}T12:00:00Z"
    cql = f"agency_code='BC' AND '{ts}'>=record_start AND '{ts}'<=record_end"
    params = urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": CWFIF_ACTIVE_LAYER,
            "outputFormat": "application/json",
            "CQL_FILTER": cql,
            "count": "500",
        }
    )
    url = f"{CWFIF_WFS}?{params}"
    try:
        content, _ = _public_http_get(url)
        payload = json.loads(content.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("CWFIF fire fetch failed: %s", exc)
        return pd.DataFrame(), "fetch_failed"

    features = payload.get("features") or []
    if not features:
        return pd.DataFrame(), "no_fires"

    rows: list[dict[str, Any]] = []
    for feat in features:
        props = feat.get("properties") or {}
        lat = props.get("latitude")
        lon = props.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not _coord_in_okanagan_bbox(lat_f, lon_f):
            continue
        size = props.get("fire_size")
        try:
            marker_radius = max(800.0, min(float(size or 1) * 120.0, 8000.0))
        except (TypeError, ValueError):
            marker_radius = 1200.0
        rows.append(
            {
                "fire_lat": lat_f,
                "fire_lon": lon_f,
                "fire_size": size,
                "marker_radius_m": marker_radius,
                "fire_color": [220, 53, 69, 210],
                "tooltip_text": _fire_tooltip(props),
            }
        )
    if not rows:
        return pd.DataFrame(), "no_fires_in_aoi"
    return pd.DataFrame(rows), "cwfif_live"


def fetch_fwi_raster_for_date(
    selected_date: date | str,
    bbox: tuple[float, float, float, float] | None = None,
    *,
    width: int = 1024,
    height: int = 1024,
) -> tuple[bytes | None, tuple[float, float, float, float], str]:
    """Styled FWI PNG and bounds for BitmapLayer."""
    scene_date = selected_date.isoformat() if isinstance(selected_date, date) else str(selected_date)[:10]
    raster_bbox = bbox or OKANAGAN_AOI_BBOX
    png = fetch_fwi_wms_png(raster_bbox, time=scene_date, width=width, height=height)
    if png is None:
        return None, raster_bbox, "fetch_failed"
    return png, raster_bbox, "cwfis_live"


def fwi_png_to_rgba_array(png_bytes: bytes) -> Any:
    """Convert WMS PNG bytes to RGBA numpy array (diagnostics / tests)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow and numpy required for FWI raster overlay") from exc
    image = Image.open(BytesIO(png_bytes)).convert("RGBA")
    return np.array(image, dtype=np.uint8)


def fwi_png_to_pydeck_image(png_bytes: bytes) -> String:
    """Encode WMS PNG for pydeck BitmapLayer (base64 data URL, not raw ndarray)."""
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return String(f"data:image/png;base64,{encoded}", quote_type='"')

def fwi_source_caption(selected_date: date | str) -> str:
    scene_date = selected_date.isoformat() if isinstance(selected_date, date) else str(selected_date)[:10]
    return f"{CWFIS_FWI_SOURCE_LABEL} — map date {scene_date}"
