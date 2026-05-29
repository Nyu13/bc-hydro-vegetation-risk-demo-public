from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import DEMO_DATA_MODES, PLANET_SURREY_SAMPLE_CSV, SURREY_FREE_DATA_SUMMARY_CSV
from src.free_data_loader import free_data_usable, load_surrey_free_data_summary
from src.risk_scoring import (
    compute_canopy_exposure_score,
    compute_heat_drought_stress_score,
    compute_vegetation_dryness_score,
    compute_vegetation_exposure_score,
)

REQUESTED_PLANET_PRODUCTS = (
    "Canopy height & cover (vegetation structure)",
    "Vegetation change detection (growth / loss)",
    "Soil water content (drought stress proxy)",
    "Land surface temperature (LST)",
    "Green / brown vegetation fraction",
    "Non-vegetated surface fraction",
)

PLANET_CSV_COLUMNS = (
    "aoi_id",
    "area_hectares",
    "vegetation_cover_green_pct",
    "vegetation_cover_brown_pct",
    "non_vegetation_pct",
    "canopy_cover_pct",
    "canopy_height_m",
    "vegetation_change_score",
    "soil_water_content",
    "land_surface_temperature_c",
    "data_source",
    "data_status",
)


@dataclass(frozen=True)
class PlanetLoadResult:
    status: str  # not loaded | placeholder | loaded
    detail: str
    row: pd.Series | None
    df: pd.DataFrame


def planet_sample_enabled(data_mode: str) -> bool:
    return data_mode == "Planet sample enabled"


def _resolve_planet_status(data_status: str | None) -> str:
    normalized = str(data_status or "").strip().lower()
    if normalized == "loaded":
        return "loaded"
    if normalized == "placeholder":
        return "placeholder"
    return "placeholder"


def load_planet_surrey_sample(data_mode: str, csv_path: Path | None = None) -> PlanetLoadResult:
    """Load Surrey Planet sample CSV when Planet mode is enabled; otherwise not loaded."""
    path = csv_path or PLANET_SURREY_SAMPLE_CSV
    if not planet_sample_enabled(data_mode):
        free_hint = ""
        if SURREY_FREE_DATA_SUMMARY_CSV.is_file() or free_data_usable(load_surrey_free_data_summary()):
            free_hint = " Open/free summary CSV available for Public/proxy mode."
        return PlanetLoadResult(
            status="not loaded",
            detail=(
                "Planet sample disabled — select “Planet sample enabled” in the sidebar."
                + free_hint
            ),
            row=None,
            df=pd.DataFrame(columns=list(PLANET_CSV_COLUMNS)),
        )
    if not path.is_file():
        return PlanetLoadResult(
            status="not loaded",
            detail=f"Planet sample file missing: {path}",
            row=None,
            df=pd.DataFrame(columns=list(PLANET_CSV_COLUMNS)),
        )
    df = pd.read_csv(path)
    if df.empty:
        return PlanetLoadResult(
            status="not loaded",
            detail=f"Planet sample file is empty: {path}",
            row=None,
            df=df,
        )
    row = df.iloc[0]
    status = _resolve_planet_status(row.get("data_status"))
    source = str(row.get("data_source", "Planet sample"))
    return PlanetLoadResult(
        status=status,
        detail=f"{source} ({status}) — {path.name}",
        row=row,
        df=df,
    )


def planet_scores_from_row(row: pd.Series | None) -> dict[str, float]:
    """Compute Planet-derived risk component scores from a CSV row or neutral defaults."""
    if row is None:
        return {
            "vegetation_exposure_score": compute_vegetation_exposure_score(),
            "vegetation_dryness_score": compute_vegetation_dryness_score(),
            "canopy_exposure_score": compute_canopy_exposure_score(),
            "heat_drought_stress_score": compute_heat_drought_stress_score(),
        }
    return {
        "vegetation_exposure_score": compute_vegetation_exposure_score(
            vegetation_cover_green_pct=_float(row.get("vegetation_cover_green_pct")),
            canopy_cover_pct=_float(row.get("canopy_cover_pct")),
            vegetation_change_score=_float(row.get("vegetation_change_score")),
        ),
        "vegetation_dryness_score": compute_vegetation_dryness_score(
            vegetation_cover_brown_pct=_float(row.get("vegetation_cover_brown_pct")),
            soil_water_content=_float(row.get("soil_water_content")),
        ),
        "canopy_exposure_score": compute_canopy_exposure_score(
            canopy_cover_pct=_float(row.get("canopy_cover_pct")),
            canopy_height_m=_float(row.get("canopy_height_m")),
        ),
        "heat_drought_stress_score": compute_heat_drought_stress_score(
            land_surface_temperature_c=_float(row.get("land_surface_temperature_c")),
            soil_water_content=_float(row.get("soil_water_content")),
        ),
    }


def _float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_data_mode(data_mode: str) -> str:
    if data_mode in DEMO_DATA_MODES:
        return data_mode
    return DEMO_DATA_MODES[0]
