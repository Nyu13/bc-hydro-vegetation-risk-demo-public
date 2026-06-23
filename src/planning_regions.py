"""Region configuration for vegetation-wildfire planning demo tabs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import (
    OKANAGAN_AOI_BBOX,
    OKANAGAN_BC_HYDRO_REGION,
    OKANAGAN_CORRIDOR_BUFFER_CANDIDATES,
    OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES,
    OKANAGAN_FWI_CORRIDOR_CSV,
    OKANAGAN_FWI_SAMPLE_CSV,
    OKANAGAN_HISTORY_START_DATE,
    OKANAGAN_MAP_ZOOM,
    OKANAGAN_MUNICIPALITIES,
    OKANAGAN_PILOT_LAT,
    OKANAGAN_PILOT_LON,
    OKANAGAN_PLANNING_DATASET_CSV,
    OKANAGAN_PLANNING_DISCLAIMER,
    OKANAGAN_PLANNING_STRESS_DATASET_CSV,
    OKANAGAN_REGION_NAME,
    OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV,
    OKANAGAN_SENTINEL2_SCENE_QA_CSV,
    OKANAGAN_WORLDCOVER_STATS_CSV,
    BC_TRANSMISSION_OVERLAY_CANDIDATES,
    PROCESSED_DATA_DIR,
    SURREY_AOI_BBOX,
    SURREY_BC_HYDRO_REGION,
    SURREY_CAUSAL_AI_AOI_SCENARIOS_CSV,
    SURREY_CAUSAL_AI_DATASET_DICT_MD,
    SURREY_CAUSAL_AI_DISCOVERY_CSV,
    SURREY_CORRIDOR_BUFFER_CANDIDATES,
    SURREY_CORRIDOR_SEGMENTS_CANDIDATES,
    SURREY_FWI_SAMPLE_CSV,
    SURREY_HISTORY_START_DATE,
    SURREY_MAP_ZOOM,
    SURREY_MUNICIPALITIES,
    SURREY_PILOT_LAT,
    SURREY_PILOT_LON,
    SURREY_PLANNING_DATASET_CSV,
    SURREY_PLANNING_DISCLAIMER,
    SURREY_PLANNING_STRESS_DATASET_CSV,
    SURREY_REGION_NAME,
    SURREY_SENTINEL2_SCENE_QA_CSV,
    SURREY_SENTINEL2_STATS_CSV,
    SURREY_WORLDCOVER_STATS_CSV,
)


@dataclass(frozen=True)
class PlanningRegionConfig:
    key: str
    label: str
    region_name: str
    bc_hydro_region: str
    aoi_bbox: tuple[float, float, float, float]
    pilot_lat: float
    pilot_lon: float
    map_zoom: float
    history_start_date: str
    planning_csv: Path
    planning_stress_csv: Path
    segments_geojson_candidates: tuple[Path, ...]
    buffer_geojson_candidates: tuple[Path, ...]
    fwi_corridor_csv: Path
    fwi_sample_csv: Path
    worldcover_stats_csv: Path
    sentinel2_stats_csv: Path
    sentinel2_scene_qa_csv: Path
    transmission_geojson_candidates: tuple[Path, ...]
    municipalities: tuple[str, ...]
    planning_disclaimer: str
    pipeline_build_cmd: str
    stress_build_cmd: str
    pilot_place_label: str
    outage_place_summary_csv: Path | None
    sentinel2_l2a_subdir: str
    sentinel2_build_cmd: str
    worldcover_build_cmd: str
    causal_ai_aoi_csv: Path | None = None
    causal_ai_discovery_csv: Path | None = None
    causal_ai_dict_md: Path | None = None


OKANAGAN_REGION = PlanningRegionConfig(
    key="okanagan",
    label="Kelowna / Okanagan",
    region_name=OKANAGAN_REGION_NAME,
    bc_hydro_region=OKANAGAN_BC_HYDRO_REGION,
    aoi_bbox=OKANAGAN_AOI_BBOX,
    pilot_lat=OKANAGAN_PILOT_LAT,
    pilot_lon=OKANAGAN_PILOT_LON,
    map_zoom=OKANAGAN_MAP_ZOOM,
    history_start_date=OKANAGAN_HISTORY_START_DATE,
    planning_csv=OKANAGAN_PLANNING_DATASET_CSV,
    planning_stress_csv=OKANAGAN_PLANNING_STRESS_DATASET_CSV,
    segments_geojson_candidates=OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES,
    buffer_geojson_candidates=OKANAGAN_CORRIDOR_BUFFER_CANDIDATES,
    fwi_corridor_csv=OKANAGAN_FWI_CORRIDOR_CSV,
    fwi_sample_csv=OKANAGAN_FWI_SAMPLE_CSV,
    worldcover_stats_csv=OKANAGAN_WORLDCOVER_STATS_CSV,
    sentinel2_stats_csv=OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV,
    sentinel2_scene_qa_csv=OKANAGAN_SENTINEL2_SCENE_QA_CSV,
    transmission_geojson_candidates=BC_TRANSMISSION_OVERLAY_CANDIDATES,
    municipalities=OKANAGAN_MUNICIPALITIES,
    planning_disclaimer=OKANAGAN_PLANNING_DISCLAIMER,
    pipeline_build_cmd="python TMP/scripts/build_okanagan_demo_pipeline.py",
    stress_build_cmd="python TMP/scripts/build_okanagan_stress_scenario_dataset.py",
    pilot_place_label="Kelowna",
    outage_place_summary_csv=PROCESSED_DATA_DIR / "okanagan_outage_proxy_summary.csv",
    sentinel2_l2a_subdir="okanagan/L2A",
    sentinel2_build_cmd="python TMP/scripts/build_okanagan_sentinel2_indices.py",
    worldcover_build_cmd="python TMP/scripts/build_okanagan_worldcover_stats.py",
)

SURREY_REGION = PlanningRegionConfig(
    key="surrey",
    label="Surrey / Lower Mainland",
    region_name=SURREY_REGION_NAME,
    bc_hydro_region=SURREY_BC_HYDRO_REGION,
    aoi_bbox=SURREY_AOI_BBOX,
    pilot_lat=SURREY_PILOT_LAT,
    pilot_lon=SURREY_PILOT_LON,
    map_zoom=SURREY_MAP_ZOOM,
    history_start_date=SURREY_HISTORY_START_DATE,
    planning_csv=SURREY_PLANNING_DATASET_CSV,
    planning_stress_csv=SURREY_PLANNING_STRESS_DATASET_CSV,
    segments_geojson_candidates=SURREY_CORRIDOR_SEGMENTS_CANDIDATES,
    buffer_geojson_candidates=SURREY_CORRIDOR_BUFFER_CANDIDATES,
    fwi_corridor_csv=SURREY_FWI_SAMPLE_CSV,
    fwi_sample_csv=SURREY_FWI_SAMPLE_CSV,
    worldcover_stats_csv=SURREY_WORLDCOVER_STATS_CSV,
    sentinel2_stats_csv=SURREY_SENTINEL2_STATS_CSV,
    sentinel2_scene_qa_csv=SURREY_SENTINEL2_SCENE_QA_CSV,
    transmission_geojson_candidates=BC_TRANSMISSION_OVERLAY_CANDIDATES,
    municipalities=SURREY_MUNICIPALITIES,
    planning_disclaimer=SURREY_PLANNING_DISCLAIMER,
    pipeline_build_cmd="python TMP/scripts/build_surrey_planning_assets.py",
    stress_build_cmd="python TMP/scripts/build_surrey_planning_assets.py --stress-only",
    pilot_place_label="Surrey",
    outage_place_summary_csv=None,
    sentinel2_l2a_subdir="surrey/Sentinel-2 L2A",
    sentinel2_build_cmd="python TMP/scripts/build_surrey_sentinel2_indices.py",
    worldcover_build_cmd="python TMP/scripts/run_surrey_free_data_pipeline.py",
    causal_ai_aoi_csv=SURREY_CAUSAL_AI_AOI_SCENARIOS_CSV,
    causal_ai_discovery_csv=SURREY_CAUSAL_AI_DISCOVERY_CSV,
    causal_ai_dict_md=SURREY_CAUSAL_AI_DATASET_DICT_MD,
)

PLANNING_REGIONS: dict[str, PlanningRegionConfig] = {
    OKANAGAN_REGION.key: OKANAGAN_REGION,
    SURREY_REGION.key: SURREY_REGION,
}

PLANNING_REGION_OPTIONS: tuple[tuple[str, str], ...] = (
    (OKANAGAN_REGION.key, OKANAGAN_REGION.label),
    (SURREY_REGION.key, SURREY_REGION.label),
)
