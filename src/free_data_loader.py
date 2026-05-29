"""Load processed open/free Surrey corridor summary for Public/proxy vegetation scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import (
    DEMO_DATA_DIR,
    SURREY_FREE_DATA_SUMMARY_CSV,
    SURREY_SENTINEL2_SCENE_QA_CSV,
    SURREY_SENTINEL2_STATS_CSV,
)
from src.risk_scoring import (
    compute_free_data_canopy_exposure_score,
    compute_free_data_heat_drought_stress_score,
    compute_free_data_terrain_access_score,
    compute_free_data_vegetation_dryness_score,
    compute_free_data_vegetation_exposure_score,
)

SURREY_FREE_DATA_PLACEHOLDER_CSV = (
    DEMO_DATA_DIR / "surrey_free_data_corridor_summary_placeholder.csv"
)

FREE_DATA_SUMMARY_COLUMNS = (
    "aoi_id",
    "worldcover_tree_pct",
    "worldcover_shrub_grass_pct",
    "worldcover_built_pct",
    "worldcover_bare_pct",
    "nalcms_forest_pct",
    "sentinel2_ndvi_mean",
    "sentinel2_ndmi_mean",
    "sentinel2_ndvi_change",
    "cloud_filtered_pct",
    "scenes_used",
    "tiles_used",
    "vegetation_change_score",
    "modis_lst_day_mean_c",
    "era5_soil_moisture_anomaly",
    "vri_mean_crown_closure",
    "vri_mean_height_m",
    "lidar_canopy_height_mean_m",
    "terrain_slope_mean_deg",
    "vegetation_exposure_score",
    "canopy_exposure_score",
    "vegetation_dryness_score",
    "heat_drought_stress_score",
    "terrain_access_score",
    "data_source",
    "data_status",
    "as_of_date",
)


@dataclass(frozen=True)
class FreeDataLoadResult:
    status: str  # not_loaded | stub | open_free_processed
    detail: str
    row: pd.Series | None
    df: pd.DataFrame


def _resolve_status(data_status: str | None) -> str:
    normalized = str(data_status or "").strip().lower()
    if normalized == "open_free_processed":
        return "open_free_processed"
    if normalized.startswith("stub"):
        return "stub"
    if normalized:
        return "stub"
    return "not_loaded"


def free_data_usable(result: FreeDataLoadResult) -> bool:
    return result.status in {"open_free_processed", "stub"} and result.row is not None


def load_surrey_free_data_summary(csv_path: Path | None = None) -> FreeDataLoadResult:
    """Load merged open/free corridor summary; falls back to bundled placeholder."""
    candidates = [
        csv_path or SURREY_FREE_DATA_SUMMARY_CSV,
        SURREY_FREE_DATA_PLACEHOLDER_CSV,
    ]
    path: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            path = candidate
            break
    if path is None:
        return FreeDataLoadResult(
            status="not_loaded",
            detail="No open/free summary CSV — run TMP/scripts/run_surrey_free_data_pipeline.py",
            row=None,
            df=pd.DataFrame(columns=list(FREE_DATA_SUMMARY_COLUMNS)),
        )

    df = pd.read_csv(path)
    if df.empty:
        return FreeDataLoadResult(
            status="not_loaded",
            detail=f"Open/free summary empty: {path}",
            row=None,
            df=df,
        )

    row = df.iloc[0]
    status = _resolve_status(row.get("data_status"))
    source = str(row.get("data_source", "open_free_v1"))
    return FreeDataLoadResult(
        status=status,
        detail=f"{source} ({status}) — {path.name}",
        row=row,
        df=df,
    )


def _float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def free_data_scores_from_row(row: pd.Series | None) -> dict[str, float]:
    """Map open/free summary row to demo score fields."""
    if row is None:
        return {
            "vegetation_exposure_score": compute_free_data_vegetation_exposure_score(),
            "canopy_exposure_score": compute_free_data_canopy_exposure_score(),
            "vegetation_dryness_score": compute_free_data_vegetation_dryness_score(),
            "heat_drought_stress_score": compute_free_data_heat_drought_stress_score(),
            "terrain_access_score": compute_free_data_terrain_access_score(),
        }

    precomputed = {
        "vegetation_exposure_score": _float(row.get("vegetation_exposure_score")),
        "canopy_exposure_score": _float(row.get("canopy_exposure_score")),
        "vegetation_dryness_score": _float(row.get("vegetation_dryness_score")),
        "heat_drought_stress_score": _float(row.get("heat_drought_stress_score")),
        "terrain_access_score": _float(row.get("terrain_access_score")),
    }

    computed = {
        "vegetation_exposure_score": compute_free_data_vegetation_exposure_score(
            worldcover_tree_pct=_float(row.get("worldcover_tree_pct")),
            nalcms_forest_pct=_float(row.get("nalcms_forest_pct")),
            vri_mean_crown_closure=_float(row.get("vri_mean_crown_closure")),
        ),
        "canopy_exposure_score": compute_free_data_canopy_exposure_score(
            worldcover_tree_pct=_float(row.get("worldcover_tree_pct")),
            vri_mean_height_m=_float(row.get("vri_mean_height_m")),
            lidar_canopy_height_mean_m=_float(row.get("lidar_canopy_height_mean_m")),
        ),
        "vegetation_dryness_score": compute_free_data_vegetation_dryness_score(
            sentinel2_ndmi_mean=_float(row.get("sentinel2_ndmi_mean")),
            era5_soil_moisture_anomaly=_float(row.get("era5_soil_moisture_anomaly")),
        ),
        "heat_drought_stress_score": compute_free_data_heat_drought_stress_score(
            modis_lst_day_mean_c=_float(row.get("modis_lst_day_mean_c")),
        ),
        "terrain_access_score": compute_free_data_terrain_access_score(
            terrain_slope_mean_deg=_float(row.get("terrain_slope_mean_deg")),
        ),
    }

    out: dict[str, float] = {}
    for key in computed:
        out[key] = precomputed[key] if precomputed[key] is not None else computed[key]
    return out


@dataclass(frozen=True)
class Sentinel2StatsLoadResult:
    status: str  # not_loaded | stub | open_free_processed
    detail: str
    row: pd.Series | None
    df: pd.DataFrame


def load_surrey_sentinel2_stats(csv_path: Path | None = None) -> Sentinel2StatsLoadResult:
    """Load corridor Sentinel-2 zonal stats CSV when present."""
    path = csv_path or SURREY_SENTINEL2_STATS_CSV
    if not path.is_file():
        return Sentinel2StatsLoadResult(
            status="not_loaded",
            detail="No Sentinel-2 stats CSV — run TMP/scripts/build_surrey_sentinel2_indices.py",
            row=None,
            df=pd.DataFrame(),
        )
    df = pd.read_csv(path)
    if df.empty:
        return Sentinel2StatsLoadResult(
            status="not_loaded",
            detail=f"Sentinel-2 stats empty: {path.name}",
            row=None,
            df=df,
        )
    row = df.iloc[0]
    status = _resolve_status(row.get("data_status"))
    return Sentinel2StatsLoadResult(
        status=status,
        detail=f"{path.name} ({status})",
        row=row,
        df=df,
    )


SENTINEL2_SCENE_QA_DISPLAY_COLUMNS = (
    "acquisition_date",
    "tile_id",
    "ndvi_mean",
    "ndmi_mean",
    "cloud_filtered_pct",
    "status",
)


def load_surrey_sentinel2_scene_qa(csv_path: Path | None = None) -> pd.DataFrame:
    """Load per-scene QA table; normalize column names for Streamlit display."""
    path = csv_path or SURREY_SENTINEL2_SCENE_QA_CSV
    if not path.is_file():
        return pd.DataFrame(columns=list(SENTINEL2_SCENE_QA_DISPLAY_COLUMNS))
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=list(SENTINEL2_SCENE_QA_DISPLAY_COLUMNS))
    out = df.copy()
    if "acquisition_date" not in out.columns and "sensing_date" in out.columns:
        out["acquisition_date"] = out["sensing_date"]
    if "tile_id" not in out.columns and "tile" in out.columns:
        out["tile_id"] = out["tile"]
    cols = [c for c in SENTINEL2_SCENE_QA_DISPLAY_COLUMNS if c in out.columns]
    return out[cols].copy()
