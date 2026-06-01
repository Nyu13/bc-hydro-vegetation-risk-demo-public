#!/usr/bin/env python3
"""ECCC atmospheric weather stress proxy for Surrey corridor (not LST or soil moisture)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _surrey_pipeline_common import DEFAULT_AOI, DEFAULT_OUT_DIR, load_aoi, today_iso, write_csv  # noqa: E402
from src.risk_scoring import (  # noqa: E402
    compute_eccc_precipitation_stress_score,
    compute_eccc_short_term_dryness_proxy_score,
    compute_eccc_temperature_stress_score,
    compute_eccc_weather_stress_score,
    compute_eccc_wind_gust_stress_score,
)
from src.weather_loader import (  # noqa: E402
    WeatherLoadResult,
    filter_weather_pilot_region,
    load_weather_demo,
)

OUTPUT_COLUMNS = [
    "aoi_id",
    "aoi_name",
    "period_start",
    "period_end",
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

AOI_NAME_BY_ID = {
    "SURREY-TX-BUF-200M": "Surrey transmission corridor 200 m buffer",
    "surrey_buffer_200m": "Surrey transmission corridor 200 m buffer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Surrey ECCC weather stress proxy stats.")
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def _aoi_name(aoi_id: str) -> str:
    return AOI_NAME_BY_ID.get(aoi_id, aoi_id.replace("-", " ").replace("_", " ").title())


def _parse_timestamp(value: object) -> datetime | None:
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


def _aggregate_weather(df: pd.DataFrame) -> dict[str, float | str | None]:
    if df.empty:
        return {
            "period_start": None,
            "period_end": None,
            "eccc_temperature_mean_c": None,
            "eccc_temperature_max_c": None,
            "eccc_temperature_min_c": None,
            "eccc_precip_total_mm": None,
            "eccc_wind_speed_mean_kmh": None,
            "eccc_wind_gust_max_kmh": None,
        }

    work = df.copy()
    parsed = work["timestamp"].map(_parse_timestamp) if "timestamp" in work.columns else pd.Series(dtype=object)
    valid = parsed.notna()
    period_start = _timestamp_iso(parsed[valid].min()) if valid.any() else None
    period_end = _timestamp_iso(parsed[valid].max()) if valid.any() else None

    temps = pd.to_numeric(work.get("temperature_c"), errors="coerce")
    precip = pd.to_numeric(work.get("precipitation_mm"), errors="coerce")
    gust = pd.to_numeric(work.get("wind_gust_kmh"), errors="coerce")

    return {
        "period_start": period_start,
        "period_end": period_end,
        "eccc_temperature_mean_c": round(float(temps.mean()), 2) if temps.notna().any() else None,
        "eccc_temperature_max_c": round(float(temps.max()), 2) if temps.notna().any() else None,
        "eccc_temperature_min_c": round(float(temps.min()), 2) if temps.notna().any() else None,
        "eccc_precip_total_mm": round(float(precip.sum()), 2) if precip.notna().any() else None,
        "eccc_wind_speed_mean_kmh": round(float(gust.mean()), 2) if gust.notna().any() else None,
        "eccc_wind_gust_max_kmh": round(float(gust.max()), 2) if gust.notna().any() else None,
    }


def _notes_for_result(result: WeatherLoadResult) -> str:
    base = (
        "ECCC atmospheric weather stress proxy from air temperature, wind gust, and precipitation. "
        "Not land surface temperature (LST) or soil water content (SWC)."
    )
    if result.is_synthetic:
        return f"{base} demo_weather.csv fallback: {result.detail}"
    return f"{base} Live MSC GeoMet pilot fetch: {result.detail}"


def _build_row(*, aoi_id: str, weather_result: WeatherLoadResult) -> dict[str, object]:
    pilot_df = filter_weather_pilot_region(weather_result.df)
    agg = _aggregate_weather(pilot_df)

    wind_score = compute_eccc_wind_gust_stress_score(agg["eccc_wind_gust_max_kmh"])
    precip_score = compute_eccc_precipitation_stress_score(agg["eccc_precip_total_mm"])
    temp_score = compute_eccc_temperature_stress_score(agg["eccc_temperature_mean_c"])
    dryness_score = compute_eccc_short_term_dryness_proxy_score(agg["eccc_precip_total_mm"])
    composite = compute_eccc_weather_stress_score(
        wind_gust_stress_score=wind_score,
        precipitation_stress_score=precip_score,
        temperature_stress_score=temp_score,
        short_term_dryness_proxy_score=dryness_score,
    )

    if composite is None:
        return _stub_row(aoi_id=aoi_id, notes="Weather rows present but insufficient for stress scoring.")

    data_status = "open_free_processed"
    data_source = "ECCC/MSC GeoMet"
    if weather_result.is_synthetic:
        data_source = "ECCC/MSC GeoMet (demo_weather.csv fallback)"

    return {
        "aoi_id": aoi_id,
        "aoi_name": _aoi_name(aoi_id),
        **agg,
        "wind_gust_stress_score": wind_score,
        "precipitation_stress_score": precip_score,
        "temperature_stress_score": temp_score,
        "short_term_dryness_proxy_score": dryness_score,
        "eccc_weather_stress_score": composite,
        "data_source": data_source,
        "data_status": data_status,
        "as_of_date": today_iso(),
        "notes": _notes_for_result(weather_result),
    }


def _stub_row(*, aoi_id: str, notes: str) -> dict[str, object]:
    row: dict[str, object] = {
        "aoi_id": aoi_id,
        "aoi_name": _aoi_name(aoi_id),
        "period_start": "",
        "period_end": "",
        "data_source": "ECCC/MSC GeoMet",
        "data_status": "unavailable",
        "as_of_date": today_iso(),
        "notes": notes,
    }
    for col in OUTPUT_COLUMNS:
        if col not in row:
            row[col] = None
    return row


def main() -> int:
    args = parse_args()
    _, aoi_id = load_aoi(args.aoi)

    weather_result = load_weather_demo(allow_synthetic_fallback=True)
    pilot_df = filter_weather_pilot_region(weather_result.df)

    if pilot_df.empty:
        row = _stub_row(
            aoi_id=aoi_id,
            notes=(
                "No weather data available from live ECCC/MSC GeoMet or demo_weather.csv fallback. "
                "Atmospheric proxy only — not LST or SWC."
            ),
        )
    else:
        row = _build_row(aoi_id=aoi_id, weather_result=weather_result)

    df = pd.DataFrame([row], columns=OUTPUT_COLUMNS)
    out = args.out_dir / "surrey_eccc_weather_stress_stats.csv"
    write_csv(df, out)
    print(
        f"Wrote {out} (status={row['data_status']}, "
        f"stress={row.get('eccc_weather_stress_score')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
