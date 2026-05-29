from __future__ import annotations

import json
import logging
import re
from html import unescape
from io import BytesIO
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from requests.exceptions import SSLError

from src.area_selection import lookup_municipality_coordinates, lookup_region_coordinates
from src.config import (
    BC_HYDRO_OUTAGE_JSON_URL,
    BC_HYDRO_OUTAGE_RSS_URL,
    bc_hydro_ssl_verify,
    DEMO_DATA_DIR,
    DEMO_OFFLINE_MODE,
)
from src.data_provenance import tag_dataframe

DEMO_OUTAGES_CSV = DEMO_DATA_DIR / "demo_outages.csv"

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 15
RSS_HTML_FIELD_RE = re.compile(r"<td><b>([^:]+):</b></td><td>([^<]*)</td>", re.IGNORECASE)
FALLBACK_SOURCE_MARKER = "fallback:"
SSL_RELAXED_SOURCE_SUFFIX = " (TLS verify relaxed)"
_SSL_RETRY_WARNING_EMITTED = False

LIVE_OUTAGE_COLUMNS = [
    "outage_id",
    "timestamp",
    "updated",
    "region",
    "municipality",
    "customers_affected",
    "cause",
    "status",
    "area",
    "latitude",
    "longitude",
    "out_lat",
    "out_lon",
    "outage_geojson",
    "outage_has_polygon",
    "feed",
]


def _load_demo_outages_tagged(*, source_note: str) -> pd.DataFrame:
    demo = pd.read_csv(DEMO_OUTAGES_CSV)
    demo = _normalize_outage_frame(demo, feed="demo_csv")
    return tag_dataframe(demo, is_synthetic=True, source=source_note)


def _empty_live_outages() -> pd.DataFrame:
    return pd.DataFrame(columns=LIVE_OUTAGE_COLUMNS + ["is_synthetic", "data_provenance", "source"])


def _disable_insecure_request_warnings() -> None:
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:  # noqa: BLE001
        pass


def _public_http_get(url: str) -> tuple[bytes, str | None]:
    """
    GET a public HTTPS URL. When SSL verify is disabled (BC_HYDRO_SSL_VERIFY=0 or
    Windows default), uses verify=False on the first request only. When verify is enabled,
    tries verify=True once; on TLS failure retries once with verify=False and logs once.
    Returns (content, optional_note_for_source_column when auto-retry was used).
    """
    global _SSL_RETRY_WARNING_EMITTED  # noqa: PLW0603

    if not bc_hydro_ssl_verify():
        _disable_insecure_request_warnings()
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, verify=False)
        response.raise_for_status()
        return response.content, None

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, verify=True)
        response.raise_for_status()
        return response.content, None
    except SSLError as exc:
        if not _SSL_RETRY_WARNING_EMITTED:
            LOGGER.warning(
                "Public feed TLS verification failed (%s); retrying with verify=False. "
                "Set BC_HYDRO_SSL_VERIFY=0 before starting Streamlit to skip the verify attempt.",
                exc,
            )
            _SSL_RETRY_WARNING_EMITTED = True
        _disable_insecure_request_warnings()
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, verify=False)
        response.raise_for_status()
        return response.content, SSL_RELAXED_SOURCE_SUFFIX


def _bchydro_http_get(url: str) -> tuple[bytes, str | None]:
    """BC Hydro public URL fetch (same TLS behavior as other public feeds)."""
    return _public_http_get(url)


def _json_payload_to_dataframe(payload: Any) -> pd.DataFrame:
    """Normalize BC Hydro outage JSON payloads to a flat DataFrame."""
    if isinstance(payload, dict):
        items: list[Any] | None = None
        for key in ("outages", "data", "features"):
            if key in payload and isinstance(payload[key], list):
                items = payload[key]
                break
        if items is None:
            return pd.json_normalize(payload)
        return pd.json_normalize(items)
    if isinstance(payload, list):
        return pd.json_normalize(payload)
    raise ValueError("Unexpected outage JSON shape.")


def _epoch_ms_to_iso(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_json_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _has_usable_value(value: Any) -> bool:
    """Safe non-null check that avoids ambiguous truth-value evaluation."""
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    try:
        # Handles NaN/NA scalars without evaluating array-like truthiness.
        return not bool(pd.isna(value))
    except Exception:  # noqa: BLE001
        return True


def _as_sequence(value: Any) -> list[Any] | None:
    """Convert list-like coordinate payloads to plain Python lists."""
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "tolist"):
        try:
            converted = value.tolist()
            return converted if isinstance(converted, list) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _flat_pairs_to_ring(flat: list[Any]) -> list[list[float]] | None:
    """BC Hydro polygon field: flat [lon, lat, lon, lat, ...] -> GeoJSON ring."""
    nums: list[float] = []
    for item in flat:
        try:
            nums.append(float(item))
        except (TypeError, ValueError):
            return None
    if len(nums) < 6 or len(nums) % 2 != 0:
        return None
    return [[nums[i], nums[i + 1]] for i in range(0, len(nums), 2)]


def _normalize_polygon_coordinates(coords: Any) -> list[list[list[float]]] | None:
    """
    Normalize to GeoJSON Polygon coordinates: list of rings, each ring [[lon, lat], ...].
    Accepts BC Hydro flat arrays, a single ring of pairs, or already-nested rings.
    """
    seq = _as_sequence(coords)
    if not seq:
        return None
    if isinstance(seq[0], (int, float)):
        ring = _flat_pairs_to_ring(seq)
        return [ring] if ring else None
    if isinstance(seq[0], list):
        if seq[0] and isinstance(seq[0][0], (int, float)):
            return [seq]  # type: ignore[list-item]
        if seq[0] and isinstance(seq[0][0], list):
            return seq  # type: ignore[return-value]
    return None


def _parse_wgs84_pair(lat_val: Any, lon_val: Any) -> tuple[float, float] | None:
    """Return (lat, lon) for BC; swap if feed columns appear reversed."""
    try:
        a = float(lat_val)
        b = float(lon_val)
    except (TypeError, ValueError):
        return None
    if 48.0 <= a <= 60.5 and -139.5 <= b <= -114.0:
        return a, b
    if 48.0 <= b <= 60.5 and -139.5 <= a <= -114.0:
        return b, a
    return None


def _extract_geometry_dict(row: pd.Series) -> dict[str, Any] | None:
    direct_candidates = (
        "geometry",
        "geojson",
        "shape",
        "outage_geojson",
        "feature.geometry",
        "properties.geometry",
    )
    for col in direct_candidates:
        if col in row and _has_usable_value(row[col]):
            value = _coerce_json_value(row[col])
            if isinstance(value, dict) and value.get("type"):
                return value
            if isinstance(value, dict) and isinstance(value.get("geometry"), dict):
                geom = value.get("geometry")
                if isinstance(geom, dict) and geom.get("type"):
                    return geom

    if {"geometry.type", "geometry.coordinates"}.issubset(row.index):
        gtype = row.get("geometry.type")
        coords = _coerce_json_value(row.get("geometry.coordinates"))
        seq_coords = _as_sequence(coords)
        if _has_usable_value(gtype) and seq_coords is not None:
            return {"type": str(gtype), "coordinates": seq_coords}

    if "polygon" in row and _has_usable_value(row["polygon"]):
        coords = _as_sequence(_coerce_json_value(row["polygon"]))
        normalized = _normalize_polygon_coordinates(coords)
        if normalized is not None:
            return {"type": "Polygon", "coordinates": normalized}

    if "coordinates" in row and _has_usable_value(row["coordinates"]):
        coords = _as_sequence(_coerce_json_value(row["coordinates"]))
        gtype = row.get("type") if "type" in row else None
        if isinstance(gtype, str) and gtype in {"Polygon", "MultiPolygon"} and coords is not None:
            return {"type": gtype, "coordinates": coords}
    return None


def _geometry_to_polygonal(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if geometry is None or not isinstance(geometry, dict):
        return None
    gtype = str(geometry.get("type", ""))
    coords = geometry.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list):
        normalized = _normalize_polygon_coordinates(coords)
        if normalized is not None:
            return {"type": "Polygon", "coordinates": normalized}
    if gtype == "MultiPolygon" and isinstance(coords, list):
        return {"type": "MultiPolygon", "coordinates": coords}
    return None


def outage_has_polygon_row(row: pd.Series) -> bool:
    """True when the row has polygonal outage geometry (not a centroid-only marker)."""
    if "outage_has_polygon" in row.index:
        flag = row.get("outage_has_polygon")
        if flag is True or (isinstance(flag, str) and flag.strip().lower() in {"true", "1", "yes"}):
            return True
    feature = row.get("outage_geojson")
    if not isinstance(feature, dict):
        return False
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) and feature.get("type") == "Feature":
        geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return False
    return geometry.get("type") in {"Polygon", "MultiPolygon"}


def _polygon_centroid(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    if geometry is None or not isinstance(geometry, dict):
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    ring: list[list[float]] | None = None
    if gtype == "Polygon" and isinstance(coords, list):
        normalized = _normalize_polygon_coordinates(coords)
        if normalized and normalized[0]:
            ring = normalized[0]
    elif (
        gtype == "MultiPolygon"
        and isinstance(coords, list)
        and coords
        and isinstance(coords[0], list)
        and coords[0]
        and isinstance(coords[0][0], list)
    ):
        ring = coords[0][0]
    if ring is None or len(ring) == 0:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for pt in ring:
        if not isinstance(pt, list) or len(pt) < 2:
            continue
        try:
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))
        except (TypeError, ValueError):
            continue
    if not xs or not ys:
        return None
    return (sum(ys) / len(ys), sum(xs) / len(xs))


def _attach_map_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    local = df.copy()
    local["outage_geojson"] = None
    local["outage_has_polygon"] = False

    for idx in local.index:
        geom = _geometry_to_polygonal(_extract_geometry_dict(local.loc[idx]))
        if geom is None:
            continue
        local.at[idx, "outage_geojson"] = {
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "outage_id": str(local.at[idx, "outage_id"]) if "outage_id" in local.columns else str(idx),
                "region": str(local.at[idx, "region"]) if "region" in local.columns else "",
                "municipality": str(local.at[idx, "municipality"]) if "municipality" in local.columns else "",
                "status": str(local.at[idx, "status"]) if "status" in local.columns else "",
                "cause": str(local.at[idx, "cause"]) if "cause" in local.columns else "",
                "updated": str(local.at[idx, "updated"]) if "updated" in local.columns else "",
                "customers_affected": (
                    int(pd.to_numeric(local.at[idx, "customers_affected"], errors="coerce"))
                    if "customers_affected" in local.columns and pd.notna(local.at[idx, "customers_affected"])
                    else 0
                ),
            },
        }
        local.at[idx, "outage_has_polygon"] = True

    if "latitude" in local.columns and "longitude" in local.columns:
        parsed_lat: list[Any] = []
        parsed_lon: list[Any] = []
        for idx in local.index:
            pair = _parse_wgs84_pair(local.at[idx, "latitude"], local.at[idx, "longitude"])
            if pair is None:
                parsed_lat.append(pd.NA)
                parsed_lon.append(pd.NA)
            else:
                parsed_lat.append(pair[0])
                parsed_lon.append(pair[1])
        local["out_lat"] = parsed_lat
        local["out_lon"] = parsed_lon
    elif "latitude" in local.columns:
        local["out_lat"] = pd.to_numeric(local["latitude"], errors="coerce")
    elif "longitude" in local.columns:
        local["out_lon"] = pd.to_numeric(local["longitude"], errors="coerce")

    if "out_lat" not in local.columns:
        local["out_lat"] = pd.NA
    if "out_lon" not in local.columns:
        local["out_lon"] = pd.NA

    missing = local["out_lat"].isna() | local["out_lon"].isna()
    if missing.any():
        for idx in local.index[missing]:
            geom = local.at[idx, "outage_geojson"] if "outage_geojson" in local.columns else None
            centroid = _polygon_centroid(geom.get("geometry") if isinstance(geom, dict) else None)
            if centroid is not None:
                local.at[idx, "out_lat"] = centroid[0]
                local.at[idx, "out_lon"] = centroid[1]

    missing = local["out_lat"].isna() | local["out_lon"].isna()
    if missing.any() and "municipality" in local.columns:
        for idx in local.index[missing]:
            municipality = str(local.at[idx, "municipality"] or "").strip()
            if not municipality:
                continue
            coords = lookup_municipality_coordinates(municipality)
            if coords is None and "region" in local.columns:
                coords = lookup_region_coordinates(str(local.at[idx, "region"] or ""))
            if coords is None:
                continue
            local.at[idx, "out_lat"] = coords[0]
            local.at[idx, "out_lon"] = coords[1]
    return local


def _normalize_outage_frame(df: pd.DataFrame, *, feed: str) -> pd.DataFrame:
    if df.empty:
        return _empty_live_outages()

    local = pd.json_normalize(df.to_dict(orient="records")) if not isinstance(df, pd.DataFrame) else df.copy()

    rename_map = {
        "id": "outage_id",
        "guid": "outage_id",
        "regionName": "region",
        "numCustomersOut": "customers_affected",
        "num_customers_out": "customers_affected",
    }
    local = local.rename(columns={k: v for k, v in rename_map.items() if k in local.columns})

    if "outage_id" not in local.columns:
        local["outage_id"] = local.index.astype(str)
    if "timestamp" not in local.columns:
        for ts_col in ("lastUpdated", "pubDate", "pub_date", "dateOff"):
            if ts_col in local.columns:
                local["timestamp"] = local[ts_col]
                break
    if "timestamp" in local.columns:
        local["timestamp"] = local["timestamp"].apply(
            lambda v: _epoch_ms_to_iso(v) if str(v).strip().isdigit() else v
        )
    if "updated" not in local.columns:
        local["updated"] = local["timestamp"] if "timestamp" in local.columns else ""
    drop_ts_aliases = [c for c in ("lastUpdated", "pubDate", "pub_date", "dateOff") if c in local.columns]
    if drop_ts_aliases:
        local = local.drop(columns=drop_ts_aliases)
    local = local.loc[:, ~local.columns.duplicated()]
    for col in ("region", "municipality", "cause", "status", "area"):
        if col not in local.columns:
            local[col] = ""
    if "customers_affected" not in local.columns:
        local["customers_affected"] = 0
    local["customers_affected"] = pd.to_numeric(local["customers_affected"], errors="coerce").fillna(0)

    if "title" in local.columns and "status" not in local.columns:
        local["status"] = local["title"].astype(str).apply(
            lambda t: "Active" if "current" in t.lower() else ("Restored" if "restored" in t.lower() else "")
        )

    local["feed"] = feed
    local = _attach_map_coordinates(local)

    keep = [c for c in LIVE_OUTAGE_COLUMNS if c in local.columns]
    extra = [c for c in local.columns if c not in keep and c not in LIVE_OUTAGE_COLUMNS]
    return local[keep + extra]


def _parse_rss_description(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for label, value in RSS_HTML_FIELD_RE.findall(html or ""):
        fields[label.strip().rstrip(":")] = unescape(value.strip())
    return fields


def _rss_items_to_frame(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title", ""))
        desc = _parse_rss_description(str(item.get("description", "")))
        rows.append(
            {
                "outage_id": item.get("guid") or item.get("link") or title,
                "timestamp": item.get("pub_date") or desc.get("Last Updated") or desc.get("Time Off"),
                "region": desc.get("Region", ""),
                "municipality": desc.get("Municipality", ""),
                "customers_affected": desc.get("# Customers Affected", 0),
                "cause": desc.get("Outage Type/Cause", ""),
                "status": "Active" if "current" in title.lower() else "Restored",
                "area": desc.get("Approx. Area Affected", title.replace("Current Outage - ", "").replace("Restored Outage - ", "")),
                "title": title,
                "link": item.get("link", ""),
            }
        )
    return _normalize_outage_frame(pd.DataFrame(rows), feed="bchydro_rss")


def load_bchydro_outage_json(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """Load current outage map JSON; fallback to demo CSV on failure."""
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_outages.csv for outage JSON.")
        return _load_demo_outages_tagged(source_note="demo_outages.csv (offline mode)")

    try:
        content, ssl_note = _bchydro_http_get(BC_HYDRO_OUTAGE_JSON_URL)
        payload = json.loads(content)
        df = _json_payload_to_dataframe(payload)
        normalized = _normalize_outage_frame(df, feed="bchydro_json")
        source_label = "BC Hydro outages-map-data.json (public)"
        if ssl_note:
            source_label += ssl_note
        return tag_dataframe(
            normalized,
            is_synthetic=False,
            source=source_label,
        )
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Outage JSON unavailable; using demo fallback. Details: %s", exc)
            return _load_demo_outages_tagged(
                source_note=f"demo_outages.csv ({FALLBACK_SOURCE_MARKER} JSON: {exc})",
            )
        LOGGER.info("Outage JSON unavailable; synthetic fallback disabled. Details: %s", exc)
        return _empty_live_outages()


def load_bchydro_rss(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """Load public outage RSS; fallback to demo outages on failure."""
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_outages.csv for outage RSS.")
        demo = _load_demo_outages_tagged(source_note="demo_outages.csv (offline mode, RSS view)")
        demo["feed"] = "demo_csv_rss_view"
        return demo

    try:
        content, ssl_note = _bchydro_http_get(BC_HYDRO_OUTAGE_RSS_URL)
        root = ET.parse(BytesIO(content)).getroot()

        items: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            items.append(
                {
                    "title": _safe_xml_text(item, "title"),
                    "description": _safe_xml_text(item, "description"),
                    "pub_date": _safe_xml_text(item, "pubDate"),
                    "link": _safe_xml_text(item, "link"),
                    "guid": _safe_xml_text(item, "guid"),
                }
            )

        if not items:
            raise ValueError("RSS returned no items.")
        normalized = _rss_items_to_frame(items)
        source_label = "BC Hydro outage RSS (public)"
        if ssl_note:
            source_label += ssl_note
        return tag_dataframe(
            normalized,
            is_synthetic=False,
            source=source_label,
        )
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Outage RSS unavailable; using demo fallback. Details: %s", exc)
            demo = _load_demo_outages_tagged(
                source_note=f"demo_outages.csv ({FALLBACK_SOURCE_MARKER} RSS: {exc})",
            )
            demo["feed"] = "demo_csv_rss_view"
            return demo
        LOGGER.info("Outage RSS unavailable; synthetic fallback disabled. Details: %s", exc)
        return _empty_live_outages()


def combine_live_outage_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    """Merge JSON + RSS live frames for dashboard metrics (dedupe by outage_id when possible)."""
    parts: list[pd.DataFrame] = []
    for frame in frames:
        if frame is None or frame.empty:
            continue
        clean = frame.loc[:, ~frame.columns.duplicated()].copy()
        parts.append(clean)
    if not parts:
        return _empty_live_outages()
    merged = pd.concat(parts, ignore_index=True)
    if "outage_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["outage_id"], keep="first")
    return merged


def live_outage_metrics(df: pd.DataFrame) -> dict[str, int]:
    count = int(len(df))
    customer_col = next(
        (
            col
            for col in ("customers_affected", "customersAffected", "numCustomersOut", "custA")
            if col in df.columns
        ),
        None,
    )
    customers = (
        int(pd.to_numeric(df[customer_col], errors="coerce").fillna(0).sum()) if customer_col else 0
    )
    active = 0
    if "status" in df.columns:
        active = int(df["status"].astype(str).str.contains("active", case=False, na=False).sum())
    return {"count": count, "customers": customers, "active": active}


def _safe_xml_text(parent: ET.Element, tag: str) -> str:
    node = parent.find(tag)
    return node.text.strip() if node is not None and node.text else ""
