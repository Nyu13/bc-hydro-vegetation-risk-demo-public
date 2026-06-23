#!/usr/bin/env python3
"""
Merge Okanagan planning layers into one row per corridor segment.

Proof-of-process composite — public/proxy layers + synthetic treatment gap.
With BC Hydro internal data this workflow can become a validated planning tool.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.regions import OKANAGAN_HISTORY_START_DATE, OKANAGAN_REGION_NAME  # noqa: E402
from src.risk_scoring import (  # noqa: E402
    compute_free_data_canopy_exposure_score,
    compute_free_data_terrain_access_score,
    compute_free_data_vegetation_dryness_score,
    compute_free_data_vegetation_exposure_score,
    normalize_score,
)

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    NEUTRAL_DEFAULT_SCORE,
    OKANAGAN_PROCESSED_DIR,
    assign_planning_priority_level,
    load_okanagan_segments,
    score_or_neutral,
    today_iso,
    top_contributing_reasons,
    write_csv,
)

OUTPUT = OKANAGAN_PROCESSED_DIR / "okanagan_vegetation_wildfire_planning_dataset.csv"

PLANNING_WEIGHTS = {
    "vegetation_score": 0.25,
    "wildfire_score": 0.20,
    "weather_score": 0.20,
    "treatment_gap_score": 0.15,
    "outage_score": 0.10,
    "terrain_score": 0.10,
}

REASON_LABELS = {
    "vegetation_score": "Vegetation cover / moisture (WorldCover + Sentinel-2)",
    "wildfire_score": "Wildfire exposure (CWFIS / placeholder)",
    "weather_score": "ECCC weather stress proxy",
    "treatment_gap_score": "Treatment gap (synthetic — BC Hydro records would replace)",
    "outage_score": "Public outage history proxy",
    "terrain_score": "Terrain / access proxy",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        print(f"WARNING: missing layer {path.name} — neutral defaults will apply.")
        return pd.DataFrame()
    return pd.read_csv(path)


def _float(val, default=None):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _vegetation_change_from_ndvi_delta(ndvi_change: float | None) -> float | None:
    if ndvi_change is None or (isinstance(ndvi_change, float) and pd.isna(ndvi_change)):
        return None
    return round(float(np.clip(abs(float(ndvi_change)) / 0.3 * 100.0, 0, 100)), 2)


def _canopy_exposure_score(tree_pct, ndvi) -> float:
    base = compute_free_data_canopy_exposure_score(worldcover_tree_pct=_float(tree_pct))
    if ndvi is None or (isinstance(ndvi, float) and pd.isna(ndvi)):
        return base
    ndvi_component = normalize_score(float(ndvi), 0.05, 0.75)
    return round(0.60 * base + 0.40 * ndvi_component, 2)


def _vegetation_score(tree_pct, ndvi, ndmi) -> tuple[float, str]:
    exposure = compute_free_data_vegetation_exposure_score(
        worldcover_tree_pct=_float(tree_pct),
        nalcms_forest_pct=None,
        vri_mean_crown_closure=None,
    )
    dryness = compute_free_data_vegetation_dryness_score(sentinel2_ndmi_mean=_float(ndmi))
    ndvi_boost = normalize_score(_float(ndvi, 0.3), 0, 0.8) if ndvi is not None else NEUTRAL_DEFAULT_SCORE
    score = round(0.55 * exposure + 0.25 * dryness + 0.20 * ndvi_boost, 2)
    status = "computed" if any(v is not None for v in (tree_pct, ndvi, ndmi)) else "neutral_default_50"
    if status == "neutral_default_50":
        return NEUTRAL_DEFAULT_SCORE, status
    return score, status


def _terrain_score_from_segment(length_km: float | None, rng: np.random.Generator) -> float:
    if length_km is None:
        return NEUTRAL_DEFAULT_SCORE
    slope_proxy = float(rng.uniform(3, 18))
    return compute_free_data_terrain_access_score(terrain_slope_mean_deg=slope_proxy)


def _corridor_sentinel2_change_defaults(s2: pd.DataFrame) -> tuple[float | None, float | None]:
    """Period-wide NDVI/NDMI change when corridor stats omit change columns."""
    if not s2.empty and "sentinel2_ndvi_change" in s2.columns and s2["sentinel2_ndvi_change"].notna().any():
        row = s2.dropna(subset=["sentinel2_ndvi_change"]).iloc[0]
        return _float(row.get("sentinel2_ndvi_change")), _float(row.get("sentinel2_ndmi_change"))
    qa_path = OKANAGAN_PROCESSED_DIR / "okanagan_sentinel2_scene_qa.csv"
    if not qa_path.is_file():
        return None, None
    qa = pd.read_csv(qa_path)
    if qa.empty or "status" not in qa.columns:
        return None, None
    ok = qa.loc[qa["status"] == "processed"].copy()
    if ok.empty or "sensing_date" not in ok.columns:
        return None, None
    ok["sensing_date"] = ok["sensing_date"].astype(str)
    dates = sorted(ok["sensing_date"].unique())
    if len(dates) < 2:
        return None, None
    early = ok.loc[ok["sensing_date"] == dates[0]]
    late = ok.loc[ok["sensing_date"] == dates[-1]]
    ndvi_change = None
    ndmi_change = None
    if "ndvi_mean" in ok.columns and early["ndvi_mean"].notna().any() and late["ndvi_mean"].notna().any():
        ndvi_change = round(float(late["ndvi_mean"].mean()) - float(early["ndvi_mean"].mean()), 4)
    if "ndmi_mean" in ok.columns and early["ndmi_mean"].notna().any() and late["ndmi_mean"].notna().any():
        ndmi_change = round(float(late["ndmi_mean"].mean()) - float(early["ndmi_mean"].mean()), 4)
    return ndvi_change, ndmi_change


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments).to_crs(4326)
    rng = np.random.default_rng(args.seed)

    wc = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_worldcover_corridor_stats.csv")
    s2 = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_sentinel2_corridor_stats.csv")
    weather = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_weather_stress_stats.csv")
    wildfire = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_cwfis_wildfire_exposure.csv")
    treatment = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_synthetic_treatment_gap.csv")
    outage_summary = _read_csv(OKANAGAN_PROCESSED_DIR / "okanagan_outage_proxy_summary.csv")

    region_outage_score = NEUTRAL_DEFAULT_SCORE
    if not outage_summary.empty and "outage_history_proxy_score" in outage_summary.columns:
        region_outage_score = float(outage_summary["outage_history_proxy_score"].mean())
    elif not outage_summary.empty and "suggested_priority_score" in outage_summary.columns:
        from src.risk_scoring import calculate_municipality_outage_history_score

        region_outage_score = float(
            outage_summary["suggested_priority_score"].apply(calculate_municipality_outage_history_score).mean()
        )

    weather_score, weather_status = score_or_neutral(
        _float(weather.iloc[0].get("eccc_weather_stress_score")) if not weather.empty else None
    )

    default_ndvi_change, default_ndmi_change = _corridor_sentinel2_change_defaults(s2)

    rows: list[dict] = []
    for _, seg in segments.iterrows():
        seg_id = str(seg.get("segment_id"))
        wc_row = wc.loc[wc["segment_id"] == seg_id] if not wc.empty and "segment_id" in wc.columns else pd.DataFrame()
        s2_row = s2.loc[s2["segment_id"] == seg_id] if not s2.empty and "segment_id" in s2.columns else pd.DataFrame()
        wf_row = (
            wildfire.loc[wildfire["segment_id"] == seg_id]
            if not wildfire.empty and "segment_id" in wildfire.columns
            else pd.DataFrame()
        )
        tx_row = (
            treatment.loc[treatment["segment_id"] == seg_id]
            if not treatment.empty and "segment_id" in treatment.columns
            else pd.DataFrame()
        )

        tree_pct = wc_row.iloc[0]["worldcover_tree_pct"] if not wc_row.empty else None
        shrub_grass_pct = wc_row.iloc[0]["worldcover_shrub_grass_pct"] if not wc_row.empty else None
        built_pct = wc_row.iloc[0]["worldcover_built_pct"] if not wc_row.empty else None
        bare_pct = wc_row.iloc[0]["worldcover_bare_pct"] if not wc_row.empty else None
        ndvi = s2_row.iloc[0]["sentinel2_ndvi_mean"] if not s2_row.empty else None
        ndmi = s2_row.iloc[0]["sentinel2_ndmi_mean"] if not s2_row.empty else None
        ndvi_change = (
            s2_row.iloc[0]["sentinel2_ndvi_change"]
            if not s2_row.empty and "sentinel2_ndvi_change" in s2_row.columns
            else default_ndvi_change
        )
        ndmi_change = (
            s2_row.iloc[0]["sentinel2_ndmi_change"]
            if not s2_row.empty and "sentinel2_ndmi_change" in s2_row.columns
            else default_ndmi_change
        )

        veg_exposure = compute_free_data_vegetation_exposure_score(worldcover_tree_pct=_float(tree_pct))
        veg_dryness = compute_free_data_vegetation_dryness_score(sentinel2_ndmi_mean=_float(ndmi))
        veg_change = _vegetation_change_from_ndvi_delta(_float(ndvi_change))
        canopy_exposure = _canopy_exposure_score(tree_pct, ndvi)

        veg_score, veg_status = _vegetation_score(tree_pct, ndvi, ndmi)
        wf_score, wf_status = score_or_neutral(
            _float(wf_row.iloc[0]["wildfire_exposure_score"]) if not wf_row.empty else None
        )
        tx_score, tx_status = score_or_neutral(
            _float(tx_row.iloc[0]["treatment_gap_score"]) if not tx_row.empty else None
        )
        terrain_score = _terrain_score_from_segment(_float(seg.get("length_km")), rng)

        components = {
            "vegetation_score": veg_score,
            "wildfire_score": wf_score,
            "weather_score": weather_score,
            "treatment_gap_score": tx_score,
            "outage_score": region_outage_score,
            "terrain_score": terrain_score,
        }
        planning_score = round(
            sum(components[k] * PLANNING_WEIGHTS[k] for k in PLANNING_WEIGHTS),
            2,
        )
        priority = assign_planning_priority_level(planning_score)
        r1, r2, r3 = top_contributing_reasons(components, weight_map=PLANNING_WEIGHTS, labels=REASON_LABELS)

        centroid = seg.geometry.centroid
        rows.append(
            {
                "corridor_id": seg.get("corridor_id"),
                "segment_id": seg_id,
                "region": seg.get("region", OKANAGAN_REGION_NAME),
                "length_km": seg.get("length_km"),
                "centroid_lat": round(centroid.y, 6),
                "centroid_lon": round(centroid.x, 6),
                "worldcover_tree_pct": tree_pct,
                "worldcover_shrub_grass_pct": shrub_grass_pct,
                "worldcover_built_pct": built_pct,
                "worldcover_bare_pct": bare_pct,
                "sentinel2_ndvi_mean": ndvi,
                "sentinel2_ndmi_mean": ndmi,
                "sentinel2_ndvi_change": ndvi_change,
                "sentinel2_ndmi_change": ndmi_change,
                "vegetation_exposure_score": veg_exposure,
                "vegetation_dryness_score": veg_dryness,
                "vegetation_change_score": veg_change,
                "canopy_exposure_score": canopy_exposure,
                "vegetation_score": veg_score,
                "vegetation_data_status": veg_status,
                "wildfire_exposure_score": wf_score,
                "wildfire_data_status": wf_status,
                "nearest_fire_km": _float(wf_row.iloc[0]["nearest_fire_km"]) if not wf_row.empty else None,
                "eccc_weather_stress_score": weather_score,
                "weather_data_status": weather_status,
                "treatment_gap_score": tx_score,
                "treatment_data_status": tx_status,
                "outage_history_proxy_score": region_outage_score,
                "outage_data_status": "unofficial_archive_proxy",
                "terrain_score": terrain_score,
                "terrain_data_status": "synthetic_slope_proxy",
                "planning_priority_score": planning_score,
                "planning_priority_level": priority,
                "top_reason_1": r1,
                "top_reason_2": r2,
                "top_reason_3": r3,
                "data_source_notes": (
                    "Public/proxy layers + synthetic treatment gap. "
                    f"Outage/weather history window starts {OKANAGAN_HISTORY_START_DATE}. "
                    "Proof-of-process for Fujitsu + BC Hydro planning workflow — not outage prediction."
                ),
                "as_of_date": today_iso(),
            }
        )

    df = pd.DataFrame(rows)
    write_csv(df, OUTPUT)
    print(f"Wrote {OUTPUT} ({len(df)} segments)")
    if not df.empty:
        print("Priority breakdown:", df["planning_priority_level"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
