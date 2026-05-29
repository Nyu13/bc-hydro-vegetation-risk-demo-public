from __future__ import annotations

import numpy as np
import pandas as pd


WEATHER_CODE_ADJUSTMENTS = {
    "CLEAR": 0.0,
    "CLOUDY": 2.0,
    "RAIN": 6.0,
    "SNOW": 8.0,
    "THUNDERSTORM": 12.0,
    "WINDSTORM": 14.0,
    "FREEZING_RAIN": 15.0,
}


def normalize_weather_code(code: str | None) -> str:
    if not code:
        return "CLEAR"
    normalized = str(code).strip().upper().replace(" ", "_").replace("-", "_")
    return normalized if normalized in WEATHER_CODE_ADJUSTMENTS else "CLOUDY"


def weather_code_risk_adjustment(code: str | None) -> float:
    return float(WEATHER_CODE_ADJUSTMENTS.get(normalize_weather_code(code), 2.0))


def normalize_score(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    if max_value <= min_value:
        return 0.0
    clipped = min(max(value, min_value), max_value)
    return float(((clipped - min_value) / (max_value - min_value)) * 100.0)


def calculate_weather_severity(
    wind_gust_kmh: float,
    precipitation_mm: float,
    temperature_c: float,
    weather_code: str | None = None,
) -> float:
    wind_component = normalize_score(wind_gust_kmh, 0, 120)
    precipitation_component = normalize_score(precipitation_mm, 0, 100)
    temp_stress = abs(temperature_c - 10.0) * 2.0
    temp_component = normalize_score(temp_stress, 0, 40)
    code_component = weather_code_risk_adjustment(weather_code)
    score = 0.55 * wind_component + 0.25 * precipitation_component + 0.1 * temp_component + 0.1 * code_component * 5
    return round(float(np.clip(score, 0, 100)), 2)


# PoC composite (0–100): 40% live weather severity + 30% corridor exposure proxy
# (demo_corridors forest/historical scores) + 20% Surrey live outage density (map JSON,
# same pilot filter as Risk Map) + 10% terrain/access from demo corridors.
POC_OUTAGE_COUNT_CAP = 20
POC_OUTAGE_CUSTOMERS_CAP = 75_000


def calculate_live_outage_density_score(
    outage_count: int,
    customers_affected: int,
    *,
    count_cap: int = POC_OUTAGE_COUNT_CAP,
    customers_cap: int = POC_OUTAGE_CUSTOMERS_CAP,
) -> float:
    """Normalize Surrey pilot outage count and customers to 0–100."""
    count_component = normalize_score(float(outage_count), 0, float(count_cap))
    customers_component = normalize_score(float(customers_affected), 0, float(customers_cap))
    score = 0.6 * count_component + 0.4 * customers_component
    return round(float(np.clip(score, 0, 100)), 2)


def calculate_corridor_exposure_score(
    forest_exposure_score: float,
    historical_outage_proxy_score: float,
    overhead_length_km: float = 0.0,
) -> float:
    """Illustrative corridor / transmission-row exposure from bundled demo attributes."""
    length_component = normalize_score(overhead_length_km, 0, 40)
    base = 0.55 * forest_exposure_score + 0.45 * historical_outage_proxy_score
    score = 0.85 * base + 0.15 * length_component
    return round(float(np.clip(score, 0, 100)), 2)


def calculate_demo_risk_score(
    weather_severity_score: float,
    vegetation_exposure_score: float,
    public_outage_history_score: float,
    terrain_access_score: float,
) -> float:
    score = (
        0.40 * weather_severity_score
        + 0.30 * vegetation_exposure_score
        + 0.20 * public_outage_history_score
        + 0.10 * terrain_access_score
    )
    return round(float(np.clip(score, 0, 100)), 2)


def assign_risk_level(risk_score: float) -> str:
    if risk_score >= 70:
        return "High"
    if risk_score >= 40:
        return "Medium"
    return "Low"


def identify_top_risk_driver(row: pd.Series) -> str:
    outage_label = (
        "Live Surrey outage density"
        if row.get("live_outage_density_applied")
        else "Public outage history proxy"
    )
    driver_map = {
        "weather_severity_score": "Wind gust / weather severity",
        "vegetation_exposure_score": "Corridor exposure (demo proxy)",
        "public_outage_history_score": outage_label,
        "terrain_access_score": "Terrain/access constraints",
    }
    top_key = max(driver_map.keys(), key=lambda key: float(row.get(key, 0)))
    return driver_map[top_key]


def suggest_review_action(risk_level: str, top_driver: str) -> str:
    if risk_level == "High":
        if "Corridor" in top_driver or "Vegetation" in top_driver:
            return "Review corridor exposure before storm window"
        if "weather" in top_driver.lower() or "wind" in top_driver.lower():
            return "Consider crew/material pre-staging"
        return "Prioritize patrol if forecast severity increases"
    if risk_level == "Medium":
        return "Prioritize patrol if forecast severity increases"
    return "Monitor only"

