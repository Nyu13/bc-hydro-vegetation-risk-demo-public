from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.config import (
    DEMO_DATA_DIR,
    DEMO_OFFLINE_MODE,
    DEMO_PILOT_LAT,
    DEMO_PILOT_LON,
    DEMO_PILOT_REGION,
    PROJECT_ROOT,
)
from src.data_provenance import provenance_badge, tag_dataframe
from src.risk_scoring import calculate_weather_severity, normalize_weather_code

LOGGER = logging.getLogger(__name__)
DEMO_WEATHER_CSV = DEMO_DATA_DIR / "demo_weather.csv"
CLIMATE_HOURLY_API = "https://api.weather.gc.ca/collections/climate-hourly/items"
SWOB_REALTIME_API = "https://api.weather.gc.ca/collections/swob-realtime/items"
REQUEST_TIMEOUT_SECONDS = 20
PILOT_WEATHER_PREFERRED_HOURS = 12
PILOT_WEATHER_FALLBACK_HOURS = 24
PILOT_WEATHER_HISTORY_HOURS = 48
PILOT_WEATHER_MAX_AGE_HOURS = 24
PILOT_WEATHER_LIMIT = 250
PILOT_BBOX_PAD = 0.3
SWOB_SORT_DESC = "-obs_date_tm"
HOURLY_SORT_DESC = "-UTC_DATE"
# Probe points near Surrey pilot (lat, lon) for multi-station SWOB attempts
PILOT_NEAR_STATION_PROBES: tuple[tuple[float, float], ...] = (
    (DEMO_PILOT_LAT, DEMO_PILOT_LON),
    (49.1939, -122.8408),
    (49.0254, -122.3605),
    (49.2167, -122.6333),
)


@dataclass(frozen=True)
class WeatherLoadResult:
    df: pd.DataFrame
    data_source: str
    last_updated: str
    detail: str = ""
    is_synthetic: bool = False
    observation_time: str = ""
    freshness_warning: str = ""


def demo_weather_csv_mtime() -> float:
    try:
        return DEMO_WEATHER_CSV.stat().st_mtime
    except OSError:
        return 0.0


def filter_weather_pilot_region(df: pd.DataFrame, *, pilot_region: str = DEMO_PILOT_REGION) -> pd.DataFrame:
    """Default UI filter: pilot region rows when region column is present."""
    if df.empty or "region" not in df.columns:
        return df
    pilot = df[df["region"] == pilot_region]
    return pilot if not pilot.empty else df


def _infer_weather_code(row: pd.Series) -> str:
    gust = float(row.get("wind_gust_kmh", 0) or 0)
    precip = float(row.get("precipitation_mm", 0) or 0)
    temp = float(row.get("temperature_c", 10) or 10)
    if gust >= 90:
        return "WINDSTORM"
    if precip >= 30:
        return "THUNDERSTORM"
    if temp <= 0 and precip >= 10:
        return "FREEZING_RAIN"
    if precip >= 12:
        return "RAIN"
    if temp <= 0 and precip >= 2:
        return "SNOW"
    if precip <= 1:
        return "CLEAR"
    return "CLOUDY"


def _enrich_weather_df(df: pd.DataFrame) -> pd.DataFrame:
    local_df = df.copy()
    if "weather_code" not in local_df.columns:
        local_df["weather_code"] = local_df.apply(_infer_weather_code, axis=1)
    local_df["weather_code"] = local_df["weather_code"].apply(normalize_weather_code)
    if "weather_severity_score" not in local_df.columns:
        local_df["weather_severity_score"] = local_df.apply(
            lambda row: calculate_weather_severity(
                wind_gust_kmh=row["wind_gust_kmh"],
                precipitation_mm=row["precipitation_mm"],
                temperature_c=row["temperature_c"],
                weather_code=row.get("weather_code"),
            ),
            axis=1,
        )
    return local_df


def _empty_weather_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "timestamp",
            "region",
            "wind_gust_kmh",
            "precipitation_mm",
            "temperature_c",
            "weather_code",
            "weather_severity_score",
        ]
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _lookback_datetime_range(hours: int) -> str:
    end = _utc_now()
    start = end - timedelta(hours=hours)
    return (
        f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
        f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )


def _pilot_bbox() -> str:
    return (
        f"{DEMO_PILOT_LON - PILOT_BBOX_PAD},{DEMO_PILOT_LAT - PILOT_BBOX_PAD},"
        f"{DEMO_PILOT_LON + PILOT_BBOX_PAD},{DEMO_PILOT_LAT + PILOT_BBOX_PAD}"
    )


def _probe_bbox(lat: float, lon: float, pad: float = 0.08) -> str:
    return f"{lon - pad},{lat - pad},{lon + pad},{lat + pad}"


def _max_observation_time(df: pd.DataFrame) -> datetime | None:
    if df.empty or "timestamp" not in df.columns:
        return None
    parsed = [_parse_timestamp(value) for value in df["timestamp"]]
    valid = [dt for dt in parsed if dt is not None]
    return max(valid) if valid else None


def _observation_age_hours(obs_time: datetime | None) -> float | None:
    if obs_time is None:
        return None
    return (_utc_now() - obs_time).total_seconds() / 3600.0


def _filter_rows_within_hours(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    if df.empty or "timestamp" not in df.columns:
        return df
    cutoff = _utc_now() - timedelta(hours=hours)
    parsed = df["timestamp"].map(_parse_timestamp)
    mask = parsed.map(lambda dt: dt is not None and dt >= cutoff)
    return df.loc[mask].copy()


def _apply_freshness_window(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Prefer observations from the last 12h; widen to 24h with a UI warning if needed."""
    preferred = _filter_rows_within_hours(df, PILOT_WEATHER_PREFERRED_HOURS)
    if not preferred.empty:
        return preferred, ""
    fallback = _filter_rows_within_hours(df, PILOT_WEATHER_FALLBACK_HOURS)
    if not fallback.empty:
        warning = (
            f"No observations in the last {PILOT_WEATHER_PREFERRED_HOURS} hours; "
            f"showing the last {PILOT_WEATHER_FALLBACK_HOURS} hours."
        )
        return fallback, warning
    return df, (
        f"No observations in the last {PILOT_WEATHER_FALLBACK_HOURS} hours; "
        f"showing all loaded rows."
    )


def _station_distance_sq(props: dict[str, Any]) -> float:
    lat = props.get("LATITUDE_DECIMAL_DEGREES")
    lon = props.get("LONGITUDE_DECIMAL_DEGREES")
    if lat is None or lon is None:
        lat = props.get("lat-value") or props.get("lat")
        lon = props.get("lon-value") or props.get("lon")
    if lat is None or lon is None:
        return float("inf")
    return (float(lat) - DEMO_PILOT_LAT) ** 2 + (float(lon) - DEMO_PILOT_LON) ** 2


def _swob_station_key(props: dict[str, Any]) -> str:
    for key in ("stn_nam-value", "stn_nam", "stn_id-value", "stn_id"):
        if props.get(key):
            return str(props[key])
    lat = props.get("lat-value") or props.get("lat")
    lon = props.get("lon-value") or props.get("lon")
    if lat is not None and lon is not None:
        return f"{lat},{lon}"
    return "unknown"


def _swob_props_timestamp(props: dict[str, Any]) -> datetime | None:
    for key in ("obs_date_tm", "date_tm-value", "date_tm"):
        parsed = _parse_timestamp(props.get(key))
        if parsed is not None:
            return parsed
    return None


def _wind_kmh_from_props(props: dict[str, Any]) -> float:
    for key in (
        "max_wnd_spd_10m_pst1hr",
        "max_wnd_spd_10m_pst10mts",
        "avg_wnd_spd_10m_pst1hr",
        "avg_wnd_spd_10m_pst1mt",
        "WIND_SPEED",
    ):
        raw = props.get(key)
        if raw is None:
            continue
        try:
            speed = float(raw)
        except (TypeError, ValueError):
            continue
        uom_key = f"{key}-uom"
        uom = str(props.get(uom_key, "")).lower()
        if "m/s" in uom or uom == "m s-1":
            speed *= 3.6
        return speed
    return 0.0


def _precip_mm_from_props(props: dict[str, Any]) -> float:
    for key in ("pcpn_amt_pst1hr", "pcpn_amt_pst10mts", "PRECIP_AMOUNT", "avg_cum_pcpn_gag_wt_fltrd_pst5mts"):
        raw = props.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _feature_timestamp(props: dict[str, Any]) -> str | None:
    parsed = _parse_timestamp(props.get("UTC_DATE"))
    if parsed is not None:
        return _timestamp_iso(parsed)
    return None


def _fetch_collection_features(
    api_url: str,
    *,
    bbox: str,
    lookback_hours: int,
    sortby: str | None,
    limit: int = PILOT_WEATHER_LIMIT,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "f": "json",
        "limit": limit,
        "bbox": bbox,
        "datetime": _lookback_datetime_range(lookback_hours),
    }
    if sortby:
        params["sortby"] = sortby
    response = requests.get(api_url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json().get("features", [])


def _swob_row_from_props(props: dict[str, Any], ts: datetime) -> dict[str, Any]:
    return {
        "timestamp": _timestamp_iso(ts),
        "region": DEMO_PILOT_REGION,
        "wind_gust_kmh": _wind_kmh_from_props(props),
        "precipitation_mm": _precip_mm_from_props(props),
        "temperature_c": float(props.get("air_temp") or 10),
        "_ts": ts,
        "_dist": _station_distance_sq(
            {
                "LATITUDE_DECIMAL_DEGREES": props.get("lat-value") or props.get("lat"),
                "LONGITUDE_DECIMAL_DEGREES": props.get("lon-value") or props.get("lon"),
            }
        ),
    }


def _pick_best_station_rows(
    by_station: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str]:
    if not by_station:
        raise ValueError("No station rows to select.")

    def station_latest(station_rows: list[dict[str, Any]]) -> datetime:
        return max(row["_ts"] for row in station_rows)

    station_name = min(
        by_station,
        key=lambda name: (-station_latest(by_station[name]).timestamp(), by_station[name][0]["_dist"]),
    )
    rows = sorted(by_station[station_name], key=lambda row: row["_ts"])
    return rows, station_name


def _ingest_swob_features(features: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        props = feature.get("properties", {})
        ts = _swob_props_timestamp(props)
        if ts is None:
            continue
        by_station.setdefault(_swob_station_key(props), []).append(_swob_row_from_props(props, ts))
    return by_station


def _fetch_swob_pilot() -> tuple[pd.DataFrame, str]:
    errors: list[str] = []
    bboxes = [_pilot_bbox(), *(_probe_bbox(lat, lon) for lat, lon in PILOT_NEAR_STATION_PROBES)]
    seen_bbox: set[str] = set()
    for lookback_hours in (PILOT_WEATHER_PREFERRED_HOURS, PILOT_WEATHER_FALLBACK_HOURS, PILOT_WEATHER_HISTORY_HOURS):
        merged_by_station: dict[str, list[dict[str, Any]]] = {}
        for bbox in bboxes:
            if bbox in seen_bbox:
                continue
            seen_bbox.add(bbox)
            try:
                features = _fetch_collection_features(
                    SWOB_REALTIME_API,
                    bbox=bbox,
                    lookback_hours=lookback_hours,
                    sortby=SWOB_SORT_DESC,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{bbox} ({lookback_hours}h): {exc}")
                continue
            for station, rows in _ingest_swob_features(features).items():
                merged_by_station.setdefault(station, []).extend(rows)

        if merged_by_station:
            rows, station_name = _pick_best_station_rows(merged_by_station)
            raw_df = pd.DataFrame({k: v for k, v in row.items() if not k.startswith("_")} for row in rows)
            return raw_df.drop_duplicates(subset=["timestamp"], keep="last"), station_name

    raise ValueError(
        "No swob-realtime features returned near Surrey pilot. "
        + ("; ".join(errors) if errors else "")
    )


def _ingest_hourly_features(features: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_station: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        props = feature.get("properties", {})
        timestamp = _feature_timestamp(props)
        if not timestamp:
            continue
        parsed = _parse_timestamp(timestamp)
        if parsed is None:
            continue
        station = str(props.get("STATION_NAME", "pilot station"))
        by_station.setdefault(station, []).append(
            {
                "timestamp": timestamp,
                "region": DEMO_PILOT_REGION,
                "wind_gust_kmh": float(props.get("WIND_SPEED") or 0),
                "precipitation_mm": float(props.get("PRECIP_AMOUNT") or 0),
                "temperature_c": float(props.get("TEMP") or 10),
                "_ts": parsed,
                "_dist": _station_distance_sq(props),
            }
        )
    return by_station


def _fetch_climate_hourly_pilot() -> tuple[pd.DataFrame, str]:
    features = _fetch_collection_features(
        CLIMATE_HOURLY_API,
        bbox=_pilot_bbox(),
        lookback_hours=PILOT_WEATHER_HISTORY_HOURS,
        sortby=HOURLY_SORT_DESC,
    )
    if not features:
        raise ValueError("No climate-hourly features returned for pilot bbox.")

    by_station = _ingest_hourly_features(features)
    if not by_station:
        raise ValueError("climate-hourly features lacked usable observation times.")

    rows, station_name = _pick_best_station_rows(by_station)
    raw_df = pd.DataFrame({k: v for k, v in row.items() if not k.startswith("_")} for row in rows)
    return raw_df.drop_duplicates(subset=["timestamp"], keep="last"), station_name


def _merge_weather_frames(swob_df: pd.DataFrame | None, hourly_df: pd.DataFrame | None) -> pd.DataFrame:
    frames = [df for df in (swob_df, hourly_df) if df is not None and not df.empty]
    if not frames:
        return _empty_weather_df()
    merged = pd.concat(frames, ignore_index=True)
    merged["_parsed_ts"] = merged["timestamp"].map(_parse_timestamp)
    merged = merged.dropna(subset=["_parsed_ts"]).sort_values("_parsed_ts")
    merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
    return merged.drop(columns=["_parsed_ts"])


def _history_window_df(df: pd.DataFrame) -> pd.DataFrame:
    return _filter_rows_within_hours(df, PILOT_WEATHER_HISTORY_HOURS)


def _demo_csv_max_observation() -> datetime | None:
    if not DEMO_WEATHER_CSV.exists():
        return None
    try:
        raw = pd.read_csv(DEMO_WEATHER_CSV, usecols=["timestamp"])
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None
    return _max_observation_time(raw)


def _load_demo_weather_csv(*, source_note: str | None = None) -> WeatherLoadResult:
    raw = _enrich_weather_df(pd.read_csv(DEMO_WEATHER_CSV))
    obs_time = _max_observation_time(raw)
    observation_time = _timestamp_iso(obs_time) if obs_time else _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    note = source_note or "demo_weather.csv"
    df = tag_dataframe(raw, is_synthetic=True, source=note)
    return WeatherLoadResult(
        df=df,
        data_source="Synthetic demo CSV",
        last_updated=observation_time,
        observation_time=observation_time,
        detail=str(DEMO_WEATHER_CSV.relative_to(PROJECT_ROOT)),
        is_synthetic=True,
    )


def _live_is_fresh_enough(obs_time: datetime | None) -> bool:
    age = _observation_age_hours(obs_time)
    return age is not None and age <= PILOT_WEATHER_MAX_AGE_HOURS


def _fetch_live_pilot_weather() -> WeatherLoadResult:
    swob_df: pd.DataFrame | None = None
    hourly_df: pd.DataFrame | None = None
    swob_station = ""
    hourly_station = ""
    swob_error: str | None = None
    hourly_error: str | None = None

    try:
        swob_df, swob_station = _fetch_swob_pilot()
    except Exception as exc:  # noqa: BLE001
        swob_error = str(exc)
        LOGGER.info("swob-realtime unavailable: %s", exc)

    try:
        hourly_df, hourly_station = _fetch_climate_hourly_pilot()
    except Exception as exc:  # noqa: BLE001
        hourly_error = str(exc)
        LOGGER.info("climate-hourly unavailable: %s", exc)

    if swob_df is None and hourly_df is None:
        raise ValueError(
            f"No live weather: swob={swob_error or 'ok'}; hourly={hourly_error or 'ok'}"
        )

    merged = _history_window_df(_merge_weather_frames(swob_df, hourly_df))
    if merged.empty:
        raise ValueError("Live weather rows were empty after history-window filter.")

    display_df, freshness_warning = _apply_freshness_window(merged)
    if display_df.empty:
        display_df = merged
        freshness_warning = (
            f"No observations in the last {PILOT_WEATHER_FALLBACK_HOURS} hours; "
            "showing the newest available MSC rows."
        )

    df = _enrich_weather_df(display_df)
    sources: list[str] = []
    if swob_df is not None and not swob_df.empty:
        sources.append("MSC GeoMet swob-realtime")
    if hourly_df is not None and not hourly_df.empty:
        sources.append("MSC GeoMet climate-hourly")
    source_label = " + ".join(sources)
    detail_parts = [
        f"{DEMO_PILOT_REGION} pilot ({DEMO_PILOT_LAT:.2f}°N, {DEMO_PILOT_LON:.2f}°W)",
        f"preferred last {PILOT_WEATHER_PREFERRED_HOURS}h",
    ]
    if swob_station:
        detail_parts.append(f"swob station: {swob_station}")
    if hourly_station:
        detail_parts.append(f"hourly station: {hourly_station}")
    if swob_error:
        detail_parts.append(f"swob note: {swob_error}")
    if hourly_error:
        detail_parts.append(f"hourly note: {hourly_error}")

    obs_dt = _max_observation_time(merged)
    observation_time = _timestamp_iso(obs_dt) if obs_dt else _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    age_hours = _observation_age_hours(obs_dt)
    if age_hours is not None and age_hours > PILOT_WEATHER_PREFERRED_HOURS and not freshness_warning:
        freshness_warning = (
            f"Latest observation is {age_hours:.1f} hours old (climate-hourly can lag real time)."
        )

    df = tag_dataframe(df, is_synthetic=False, source=source_label)
    return WeatherLoadResult(
        df=df,
        data_source=f"Environment Canada / MSC GeoMet ({source_label})",
        last_updated=observation_time,
        observation_time=observation_time,
        detail=" — ".join(detail_parts),
        is_synthetic=False,
        freshness_warning=freshness_warning,
    )


def load_weather_demo(allow_synthetic_fallback: bool = True) -> WeatherLoadResult:
    """
    Load pilot-region weather: MSC GeoMet swob-realtime + climate-hourly when online,
    else demo CSV on offline mode or fetch failure.
    """
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_weather.csv.")
        return _load_demo_weather_csv(source_note="demo_weather.csv (offline mode)")

    live_error: str | None = None
    live_result: WeatherLoadResult | None = None
    try:
        live_result = _fetch_live_pilot_weather()
        obs_dt = _parse_timestamp(live_result.observation_time)
        if _live_is_fresh_enough(obs_dt):
            return live_result
        live_error = (
            f"Live observation {live_result.observation_time} is older than "
            f"{PILOT_WEATHER_MAX_AGE_HOURS}h"
        )
        LOGGER.info("Live weather stale: %s", live_error)
    except Exception as exc:  # noqa: BLE001
        live_error = str(exc)
        LOGGER.info("Weather API unavailable: %s", exc)

    demo_obs = _demo_csv_max_observation()
    live_obs = _parse_timestamp(live_result.observation_time) if live_result else None
    if live_result is not None and live_obs is not None and (
        demo_obs is None or live_obs >= demo_obs
    ):
        warning = live_result.freshness_warning
        if live_error:
            warning = f"{warning} {live_error}".strip() if warning else live_error
        return WeatherLoadResult(
            df=live_result.df,
            data_source=live_result.data_source,
            last_updated=live_result.observation_time,
            observation_time=live_result.observation_time,
            detail=live_result.detail,
            is_synthetic=False,
            freshness_warning=warning,
        )

    if allow_synthetic_fallback:
        LOGGER.info("Weather API unavailable or stale; using demo weather CSV. Details: %s", live_error)
        demo = _load_demo_weather_csv(source_note=f"demo_weather.csv (weather API fallback: {live_error})")
        return WeatherLoadResult(
            df=demo.df,
            data_source=f"{demo.data_source} (live feed fallback)",
            last_updated=demo.observation_time,
            observation_time=demo.observation_time,
            detail=f"{demo.detail} — {live_error}",
            is_synthetic=True,
            freshness_warning="Using synthetic demo CSV because live MSC data was unavailable or stale.",
        )

    LOGGER.info("Weather API unavailable; synthetic fallback disabled. Details: %s", live_error)
    now_iso = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return WeatherLoadResult(
        df=_empty_weather_df(),
        data_source="No data (live public only)",
        last_updated=now_iso,
        observation_time=now_iso,
        detail=live_error or "",
        is_synthetic=False,
    )


def weather_provenance_caption(result: WeatherLoadResult) -> str:
    return f"{provenance_badge(result.is_synthetic)} — {result.data_source}"
