#!/usr/bin/env python3
"""
ECCC atmospheric weather stress for Kelowna / Okanagan corridor demo.

Fetches daily MSC GeoMet climate-hourly history from OKANAGAN_HISTORY_START_DATE
through today, aggregates to daily rows plus a period summary for planning.
Atmospheric proxy only — not LST or soil moisture.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.regions import (  # noqa: E402
    OKANAGAN_AOI_BBOX,
    OKANAGAN_HISTORY_START_DATE,
    OKANAGAN_PILOT_LAT,
    OKANAGAN_PILOT_LON,
    OKANAGAN_REGION_NAME,
)
from src.risk_scoring import (  # noqa: E402
    compute_eccc_precipitation_stress_score,
    compute_eccc_short_term_dryness_proxy_score,
    compute_eccc_temperature_stress_score,
    compute_eccc_weather_stress_score,
    compute_eccc_wind_gust_stress_score,
)
from src.weather_loader import (  # noqa: E402
    CLIMATE_HOURLY_API,
    HOURLY_SORT_DESC,
    _parse_timestamp,
    _timestamp_iso,
    _utc_now,
    _wind_kmh_from_props,
)

from _okanagan_pipeline_common import OKANAGAN_PROCESSED_DIR, today_iso, write_csv  # noqa: E402

OUTPUT = OKANAGAN_PROCESSED_DIR / "okanagan_weather_stress_stats.csv"
DAILY_OUTPUT = OKANAGAN_PROCESSED_DIR / "okanagan_weather_stress_daily.csv"
REQUEST_TIMEOUT = 30
FETCH_LIMIT = 5000

# Kelowna Airport (CYLW) approximate — primary station for Okanagan demo
KELOWNA_STATION_NAME = "KELOWNA A"
KELOWNA_STATION_LAT = 49.956
KELOWNA_STATION_LON = -119.378

DAILY_COLUMNS = [
    "date",
    "aoi_id",
    "aoi_name",
    "region",
    "station_name",
    "station_lat",
    "station_lon",
    "eccc_temperature_mean_c",
    "eccc_temperature_max_c",
    "eccc_temperature_min_c",
    "eccc_precip_total_mm",
    "eccc_wind_speed_mean_kmh",
    "eccc_wind_gust_max_kmh",
    "wind_gust_stress_score",
    "precipitation_stress_score",
    "temperature_stress_score",
    "short_term_dryness_proxy_score",
    "eccc_weather_stress_score",
    "hourly_observation_count",
    "data_source",
    "data_status",
    "notes",
]

OUTPUT_COLUMNS = [
    "aoi_id",
    "aoi_name",
    "region",
    "station_name",
    "station_lat",
    "station_lon",
    "period_start",
    "period_end",
    "history_start_date",
    "daily_row_count",
    "eccc_temperature_mean_c",
    "eccc_temperature_max_c",
    "eccc_temperature_min_c",
    "eccc_precip_total_mm",
    "eccc_wind_speed_mean_kmh",
    "eccc_wind_gust_max_kmh",
    "wind_gust_stress_score",
    "precipitation_stress_score",
    "temperature_stress_score",
    "short_term_dryness_proxy_score",
    "eccc_weather_stress_score",
    "data_source",
    "data_status",
    "as_of_date",
    "notes",
]


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__).parse_args()


def _okanagan_bbox(pad: float = 0.35) -> str:
    lon, lat = OKANAGAN_PILOT_LON, OKANAGAN_PILOT_LAT
    return f"{lon - pad},{lat - pad},{lon + pad},{lat + pad}"


def _month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        chunk_end = min(end, next_month - timedelta(days=1))
        ranges.append((cursor, chunk_end))
        cursor = next_month
    return ranges


def _station_distance_sq(props: dict) -> float:
    lat = props.get("LATITUDE_DECIMAL_DEGREES") or props.get("LATITUDE")
    lon = props.get("LONGITUDE_DECIMAL_DEGREES") or props.get("LONGITUDE")
    if lat is None or lon is None:
        return float("inf")
    return (float(lat) - OKANAGAN_PILOT_LAT) ** 2 + (float(lon) - OKANAGAN_PILOT_LON) ** 2


def _fetch_climate_hourly_chunk(chunk_start: date, chunk_end: date) -> list[dict]:
    params = {
        "f": "json",
        "limit": FETCH_LIMIT,
        "bbox": _okanagan_bbox(),
        "datetime": (
            f"{chunk_start.isoformat()}T00:00:00Z/"
            f"{chunk_end.isoformat()}T23:59:59Z"
        ),
        "sortby": HOURLY_SORT_DESC,
    }
    response = requests.get(CLIMATE_HOURLY_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    rows: list[dict] = []
    for feature in response.json().get("features", []):
        props = feature.get("properties", {})
        timestamp = props.get("UTC_DATE")
        parsed = _parse_timestamp(timestamp)
        if parsed is None:
            continue
        rows.append(
            {
                "timestamp": _timestamp_iso(parsed),
                "station_name": str(props.get("STATION_NAME", "unknown")),
                "temperature_c": float(props.get("TEMP") or 0),
                "precipitation_mm": float(props.get("PRECIP_AMOUNT") or 0),
                "wind_gust_kmh": _wind_kmh_from_props(props),
                "_dist": _station_distance_sq(props),
            }
        )
    return rows


def _pick_kelowna_station(hourly_rows: list[dict]) -> str:
    if not hourly_rows:
        return KELOWNA_STATION_NAME

    by_station: dict[str, list[dict]] = {}
    for row in hourly_rows:
        by_station.setdefault(row["station_name"], []).append(row)

    def station_rank(name: str) -> tuple[int, int, float]:
        rows = by_station[name]
        wind_count = sum(1 for row in rows if float(row.get("wind_gust_kmh") or 0) > 0)
        is_ubco = 1 if "UBCO" in name.upper() else 0
        return (-wind_count, is_ubco, rows[0]["_dist"])

    kelowna_stations = [name for name in by_station if "KELOWNA" in name.upper()]
    if kelowna_stations:
        return min(kelowna_stations, key=station_rank)
    return min(by_station, key=station_rank)


def _aggregate_daily_rows(hourly_df: pd.DataFrame, station_name: str) -> pd.DataFrame:
    if hourly_df.empty:
        return pd.DataFrame(columns=DAILY_COLUMNS)

    work = hourly_df.copy()
    work["obs_day"] = work["timestamp"].map(
        lambda value: _parse_timestamp(value).strftime("%Y-%m-%d") if _parse_timestamp(value) else None
    )
    work = work.dropna(subset=["obs_day"])
    work = work.loc[work["obs_day"] >= OKANAGAN_HISTORY_START_DATE]

    daily_rows: list[dict] = []
    for obs_day, grp in work.groupby("obs_day"):
        temps = pd.to_numeric(grp["temperature_c"], errors="coerce")
        precip = pd.to_numeric(grp["precipitation_mm"], errors="coerce")
        gust = pd.to_numeric(grp["wind_gust_kmh"], errors="coerce")
        wind_score = compute_eccc_wind_gust_stress_score(float(gust.max()) if gust.notna().any() else None)
        precip_total = float(precip.fillna(0).sum()) if precip.notna().any() else None
        precip_score = compute_eccc_precipitation_stress_score(precip_total)
        temp_mean = float(temps.mean()) if temps.notna().any() else None
        temp_score = compute_eccc_temperature_stress_score(temp_mean)
        dryness_score = compute_eccc_short_term_dryness_proxy_score(precip_total)
        composite = compute_eccc_weather_stress_score(
            wind_gust_stress_score=wind_score,
            precipitation_stress_score=precip_score,
            temperature_stress_score=temp_score,
            short_term_dryness_proxy_score=dryness_score,
        )
        daily_rows.append(
            {
                "date": obs_day,
                "aoi_id": "okanagan_corridor",
                "aoi_name": OKANAGAN_REGION_NAME,
                "region": OKANAGAN_REGION_NAME,
                "station_name": station_name,
                "station_lat": KELOWNA_STATION_LAT,
                "station_lon": KELOWNA_STATION_LON,
                "eccc_temperature_mean_c": round(temp_mean, 2) if temp_mean is not None else None,
                "eccc_temperature_max_c": round(float(temps.max()), 2) if temps.notna().any() else None,
                "eccc_temperature_min_c": round(float(temps.min()), 2) if temps.notna().any() else None,
                "eccc_precip_total_mm": round(precip_total, 2) if precip_total is not None else None,
                "eccc_wind_speed_mean_kmh": round(float(gust.mean()), 2) if gust.notna().any() else None,
                "eccc_wind_gust_max_kmh": round(float(gust.max()), 2) if gust.notna().any() else None,
                "wind_gust_stress_score": wind_score if wind_score is not None else 50.0,
                "precipitation_stress_score": precip_score if precip_score is not None else 50.0,
                "temperature_stress_score": temp_score if temp_score is not None else 50.0,
                "short_term_dryness_proxy_score": dryness_score if dryness_score is not None else 50.0,
                "eccc_weather_stress_score": composite if composite is not None else 50.0,
                "hourly_observation_count": int(len(grp)),
                "data_source": "ECCC/MSC GeoMet climate-hourly",
                "data_status": "open_free_processed",
                "notes": f"Daily aggregate from climate-hourly near Kelowna ({station_name}).",
            }
        )

    return pd.DataFrame(daily_rows, columns=DAILY_COLUMNS).sort_values("date")


def _fetch_okanagan_daily_history() -> tuple[pd.DataFrame, str]:
    start = datetime.strptime(OKANAGAN_HISTORY_START_DATE, "%Y-%m-%d").date()
    end = _utc_now().date()
    hourly_rows: list[dict] = []
    errors: list[str] = []

    for chunk_start, chunk_end in _month_ranges(start, end):
        try:
            hourly_rows.extend(_fetch_climate_hourly_chunk(chunk_start, chunk_end))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{chunk_start}..{chunk_end}: {exc}")

    if not hourly_rows:
        raise ValueError(f"No MSC climate-hourly features near Okanagan: {'; '.join(errors)}")

    station_name = _pick_kelowna_station(hourly_rows)
    station_df = pd.DataFrame(hourly_rows)
    station_df = station_df.loc[station_df["station_name"] == station_name].drop_duplicates(
        subset=["timestamp"], keep="last"
    )
    daily_df = _aggregate_daily_rows(station_df, station_name)
    if daily_df.empty:
        raise ValueError(
            f"No daily weather rows on/after {OKANAGAN_HISTORY_START_DATE} for station {station_name}."
        )
    return daily_df, station_name


def _aggregate_period(daily_df: pd.DataFrame, station_name: str) -> dict:
    temps_mean = pd.to_numeric(daily_df["eccc_temperature_mean_c"], errors="coerce")
    temps_max = pd.to_numeric(daily_df["eccc_temperature_max_c"], errors="coerce")
    temps_min = pd.to_numeric(daily_df["eccc_temperature_min_c"], errors="coerce")
    precip = pd.to_numeric(daily_df["eccc_precip_total_mm"], errors="coerce")
    gust = pd.to_numeric(daily_df["eccc_wind_gust_max_kmh"], errors="coerce")
    period_start = daily_df["date"].min()
    period_end = daily_df["date"].max()

    wind_score = compute_eccc_wind_gust_stress_score(float(gust.max()) if gust.notna().any() else None)
    precip_total = float(precip.fillna(0).sum()) if precip.notna().any() else None
    precip_score = compute_eccc_precipitation_stress_score(precip_total)
    temp_mean = float(temps_mean.mean()) if temps_mean.notna().any() else None
    temp_score = compute_eccc_temperature_stress_score(temp_mean)
    dryness_score = compute_eccc_short_term_dryness_proxy_score(precip_total)
    composite = compute_eccc_weather_stress_score(
        wind_gust_stress_score=wind_score,
        precipitation_stress_score=precip_score,
        temperature_stress_score=temp_score,
        short_term_dryness_proxy_score=dryness_score,
    )

    return {
        "aoi_id": "okanagan_corridor",
        "aoi_name": OKANAGAN_REGION_NAME,
        "region": OKANAGAN_REGION_NAME,
        "station_name": station_name,
        "station_lat": KELOWNA_STATION_LAT,
        "station_lon": KELOWNA_STATION_LON,
        "period_start": period_start,
        "period_end": period_end,
        "history_start_date": OKANAGAN_HISTORY_START_DATE,
        "daily_row_count": int(len(daily_df)),
        "eccc_temperature_mean_c": round(temp_mean, 2) if temp_mean is not None else None,
        "eccc_temperature_max_c": round(float(temps_max.max()), 2) if temps_max.notna().any() else None,
        "eccc_temperature_min_c": round(float(temps_min.min()), 2) if temps_min.notna().any() else None,
        "eccc_precip_total_mm": round(precip_total, 2) if precip_total is not None else None,
        "eccc_wind_speed_mean_kmh": round(float(gust.mean()), 2) if gust.notna().any() else None,
        "eccc_wind_gust_max_kmh": round(float(gust.max()), 2) if gust.notna().any() else None,
        "wind_gust_stress_score": wind_score if wind_score is not None else 50.0,
        "precipitation_stress_score": precip_score if precip_score is not None else 50.0,
        "temperature_stress_score": temp_score if temp_score is not None else 50.0,
        "short_term_dryness_proxy_score": dryness_score if dryness_score is not None else 50.0,
        "eccc_weather_stress_score": composite if composite is not None else 50.0,
        "data_source": "ECCC/MSC GeoMet climate-hourly (daily history)",
        "data_status": "open_free_processed",
        "as_of_date": today_iso(),
        "notes": (
            f"Nearest Kelowna-area MSC station: {station_name}. "
            f"Daily history from {OKANAGAN_HISTORY_START_DATE} through {period_end} "
            f"({len(daily_df)} days with observations). "
            "ECCC atmospheric weather stress proxy (not LST/SWC). "
            f"AOI bbox WGS84: {OKANAGAN_AOI_BBOX}."
        ),
    }


def _stub_row(notes: str) -> dict:
    row = {col: None for col in OUTPUT_COLUMNS}
    row.update(
        {
            "aoi_id": "okanagan_corridor",
            "aoi_name": OKANAGAN_REGION_NAME,
            "region": OKANAGAN_REGION_NAME,
            "station_name": KELOWNA_STATION_NAME,
            "station_lat": KELOWNA_STATION_LAT,
            "station_lon": KELOWNA_STATION_LON,
            "history_start_date": OKANAGAN_HISTORY_START_DATE,
            "daily_row_count": 0,
            "data_source": "ECCC/MSC GeoMet",
            "data_status": "unavailable_neutral_default",
            "as_of_date": today_iso(),
            "notes": notes,
            "eccc_weather_stress_score": 50.0,
            "wind_gust_stress_score": 50.0,
            "precipitation_stress_score": 50.0,
            "temperature_stress_score": 50.0,
            "short_term_dryness_proxy_score": 50.0,
        }
    )
    return row


def main() -> int:
    parse_args()
    try:
        daily_df, station_name = _fetch_okanagan_daily_history()
        row = _aggregate_period(daily_df, station_name)
        write_csv(daily_df, DAILY_OUTPUT)
        print(
            f"Wrote {DAILY_OUTPUT} ({len(daily_df)} daily rows, "
            f"{daily_df['date'].min()} .. {daily_df['date'].max()})"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: weather fetch failed ({exc}); writing neutral default score 50.")
        row = _stub_row(
            f"Live MSC GeoMet unavailable ({exc}). Neutral default score 50 applied. "
            f"Requested daily history from {OKANAGAN_HISTORY_START_DATE}. "
            "Atmospheric proxy only — not LST or soil moisture."
        )
        write_csv(pd.DataFrame(columns=DAILY_COLUMNS), DAILY_OUTPUT)

    write_csv(pd.DataFrame([row], columns=OUTPUT_COLUMNS), OUTPUT)
    print(
        f"Wrote {OUTPUT} (stress={row.get('eccc_weather_stress_score')}, "
        f"status={row.get('data_status')}, period={row.get('period_start')}..{row.get('period_end')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
