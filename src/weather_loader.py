from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from src.config import DEMO_DATA_DIR, DEMO_OFFLINE_MODE
from src.risk_scoring import calculate_weather_severity, normalize_weather_code

LOGGER = logging.getLogger(__name__)
GEOMET_API = "https://api.weather.gc.ca/collections/climate-stations/items"
REQUEST_TIMEOUT_SECONDS = 15


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


def load_weather_demo(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """
    Attempt light public weather call; if unavailable, use local demo weather.
    """
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_weather.csv.")
        df = pd.read_csv(DEMO_DATA_DIR / "demo_weather.csv")
        return _enrich_weather_df(df)
    try:
        response = requests.get(GEOMET_API, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        features = payload.get("features", [])
        if not features:
            raise ValueError("No features in GeoMet response.")

        # Keep this simple for demo: still use local records for consistent dashboard.
        df = pd.read_csv(DEMO_DATA_DIR / "demo_weather.csv")
        return _enrich_weather_df(df)
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Weather API unavailable; using demo weather CSV. Details: %s", exc)
            df = pd.read_csv(DEMO_DATA_DIR / "demo_weather.csv")
            return _enrich_weather_df(df)
        LOGGER.info("Weather API unavailable; synthetic fallback disabled. Details: %s", exc)
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

