#!/usr/bin/env python3
"""
Build Surrey corridor segments, buffer, and planning datasets for the Streamlit demo.

Uses bundled Lower Mainland transmission GeoJSON (no WFS required). Planning scores
reuse the Okanagan composite formula with Surrey open/free corridor summary inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, box, mapping
from shapely.ops import linemerge, unary_union

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_okanagan_planning_dataset import (  # noqa: E402
    _canopy_exposure_score,
    _corridor_sentinel2_change_defaults,
    _derive_problem_type,
    _float,
    _planning_score_from_components,
    _read_csv,
    _scenario_scores,
    _terrain_score_from_segment,
    _tree_contact_exposure_proxy,
    _vegetation_change_from_ndvi_delta,
    _vegetation_score,
    _wind_stress_from_gust,
    PLANNING_WEIGHTS,
    PROBLEM_TYPE_ACTIONS,
    REASON_LABELS,
    RISK_PATHWAY_BY_PROBLEM,
    EXPLANATION_BY_PROBLEM,
)
from build_okanagan_stress_scenario_dataset import build_stress_dataset  # noqa: E402
from src.config import (  # noqa: E402
    BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON,
    DEMO_DATA_DIR,
    PROCESSED_DATA_DIR,
    SURREY_CORRIDOR_BUFFER_GEOJSON,
    SURREY_CORRIDOR_BUFFER_M,
    SURREY_CORRIDOR_SEGMENTS_GEOJSON,
    SURREY_FREE_DATA_SUMMARY_CSV,
    SURREY_PLANNING_DATASET_CSV,
    SURREY_PLANNING_STRESS_DATASET_CSV,
    SURREY_SEGMENT_LENGTH_KM,
    SURREY_TRANSMISSION_LINES_GEOJSON,
)
from src.regions import SURREY_AOI_BBOX, SURREY_REGION_NAME  # noqa: E402
from src.risk_scoring import (  # noqa: E402
    compute_free_data_vegetation_dryness_score,
    compute_free_data_vegetation_exposure_score,
    normalize_score,
)
from _okanagan_pipeline_common import (  # noqa: E402
    NEUTRAL_DEFAULT_SCORE,
    assign_planning_priority_level,
    load_okanagan_segments,
    score_or_neutral,
    today_iso,
    top_contributing_reasons,
    write_csv,
)

METRIC_CRS = "EPSG:3005"
BUFFER_DEMO = DEMO_DATA_DIR / "surrey_transmission_buffer_200m.geojson"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-km", type=float, default=SURREY_SEGMENT_LENGTH_KM)
    parser.add_argument("--buffer-m", type=float, default=SURREY_CORRIDOR_BUFFER_M)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stress-only", action="store_true")
    return parser.parse_args()


def _line_parts(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if not part.is_empty]
    merged = linemerge(geom)
    if merged.geom_type == "LineString":
        return [merged]
    if merged.geom_type == "MultiLineString":
        return [part for part in merged.geoms if not part.is_empty]
    return []


def _substring(line: LineString, start_dist: float, end_dist: float) -> LineString | None:
    if end_dist <= start_dist:
        return None
    try:
        total = line.length
        if total <= 0:
            return None
        start_frac = max(0.0, min(1.0, start_dist / total))
        end_frac = max(0.0, min(1.0, end_dist / total))
        if end_frac <= start_frac:
            return None
        n = max(2, int((end_frac - start_frac) * 50) + 1)
        fracs = [start_frac + (end_frac - start_frac) * i / (n - 1) for i in range(n)]
        coords = [line.interpolate(frac, normalized=True).coords[0] for frac in fracs]
        return LineString(coords)
    except Exception:  # noqa: BLE001
        return None


def split_line_to_segments(line: LineString, segment_m: float) -> list[LineString]:
    if line.length <= segment_m:
        return [line]
    segments: list[LineString] = []
    start = 0.0
    while start < line.length:
        end = min(start + segment_m, line.length)
        sub = _substring(line, start, end)
        if sub is not None and not sub.is_empty and sub.length > 1:
            segments.append(sub)
        if end >= line.length:
            break
        start = end
    return segments


def _resolve_transmission_source() -> Path:
    for path in (SURREY_TRANSMISSION_LINES_GEOJSON, BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON):
        if path.is_file():
            return path
    raise FileNotFoundError(
        "No Surrey transmission GeoJSON — expected bundled "
        f"{BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON.name}"
    )


def build_transmission_and_segments(
    segment_km: float,
    buffer_m: float,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    source = _resolve_transmission_source()
    min_lon, min_lat, max_lon, max_lat = SURREY_AOI_BBOX
    aoi_wgs = box(min_lon, min_lat, max_lon, max_lat)
    aoi_metric = gpd.GeoDataFrame(geometry=[aoi_wgs], crs="EPSG:4326").to_crs(METRIC_CRS).geometry.iloc[0]
    lines = gpd.read_file(source).to_crs(METRIC_CRS)
    lines = lines.loc[lines.intersects(aoi_metric)].copy()
    if lines.empty:
        raise RuntimeError(f"No transmission lines in Surrey AOI from {source.name}")

    lines = gpd.clip(lines, gpd.GeoDataFrame(geometry=[aoi_metric], crs=METRIC_CRS))
    if lines.empty:
        raise RuntimeError("Clipped transmission lines empty for Surrey AOI.")

    segment_m = segment_km * 1000.0
    seg_rows: list[dict] = []
    for idx, row in lines.iterrows():
        line_id = str(row.get("TRANSMISSION_LINE_ID", row.get("line_id", idx)))
        corridor_id = f"SR-TX-{line_id}"
        for part in _line_parts(row.geometry):
            seg_num = 0
            for seg in split_line_to_segments(part, segment_m):
                seg_num += 1
                seg_rows.append(
                    {
                        "corridor_id": corridor_id,
                        "segment_id": f"{corridor_id}-S{seg_num:03d}",
                        "region": SURREY_REGION_NAME,
                        "transmission_line_id": line_id,
                        "length_km": round(seg.length / 1000.0, 3),
                        "geometry": seg,
                    }
                )
    if not seg_rows:
        raise RuntimeError("No corridor segments created for Surrey.")
    segments = gpd.GeoDataFrame(seg_rows, crs=METRIC_CRS)

    if BUFFER_DEMO.is_file():
        buffer = gpd.read_file(BUFFER_DEMO).to_crs(METRIC_CRS)
    else:
        dissolved = unary_union(segments.geometry)
        geoms = _line_parts(dissolved) if dissolved.geom_type != "LineString" else [dissolved]
        polys = [g.buffer(buffer_m) for g in geoms if g is not None and not g.is_empty]
        buffer = gpd.GeoDataFrame(geometry=polys, crs=METRIC_CRS)

    return lines, segments, buffer


def _segment_rng(segment_id: str, seed: int) -> np.random.Generator:
    token = sum(ord(c) for c in segment_id) + seed * 9973
    return np.random.default_rng(token)


def _synthetic_wildfire_score(segment_id: str, seed: int) -> float:
    rng = _segment_rng(segment_id, seed)
    return round(float(rng.uniform(35, 72)), 2)


def _synthetic_treatment_gap(segment_id: str, seed: int) -> float:
    rng = _segment_rng(segment_id, seed + 17)
    return round(float(rng.uniform(45, 85)), 2)


def build_planning_dataset(segments: gpd.GeoDataFrame, *, seed: int) -> pd.DataFrame:
    segments = segments.to_crs(4326)
    rng = np.random.default_rng(seed)

    free = _read_csv(SURREY_FREE_DATA_SUMMARY_CSV)
    weather = _read_csv(PROCESSED_DATA_DIR / "surrey_eccc_weather_stress_stats.csv")
    s2 = _read_csv(PROCESSED_DATA_DIR / "surrey_sentinel2_corridor_stats.csv")

    summary = free.iloc[0].to_dict() if not free.empty else {}
    tree_pct = summary.get("worldcover_tree_pct")
    shrub_grass_pct = summary.get("worldcover_shrub_grass_pct")
    built_pct = summary.get("worldcover_built_pct")
    bare_pct = summary.get("worldcover_bare_pct")
    ndvi = summary.get("sentinel2_ndvi_mean")
    ndmi = summary.get("sentinel2_ndmi_mean")
    ndvi_change = summary.get("sentinel2_ndvi_change")
    ndmi_change = summary.get("sentinel2_ndmi_change")

    weather_score, weather_status = score_or_neutral(
        _float(weather.iloc[0].get("eccc_weather_stress_score")) if not weather.empty else summary.get("heat_drought_stress_score")
    )
    wind_gust = _float(weather.iloc[0].get("eccc_wind_gust_max_kmh")) if not weather.empty else None
    wind_stress_score, wind_data_status = _wind_stress_from_gust(wind_gust)

    region_outage_score = _float(summary.get("public_outage_history_score"), NEUTRAL_DEFAULT_SCORE)
    if region_outage_score is None:
        region_outage_score = NEUTRAL_DEFAULT_SCORE

    default_ndvi_change, default_ndmi_change = _corridor_sentinel2_change_defaults(s2)
    if ndvi_change is None:
        ndvi_change = default_ndvi_change
    if ndmi_change is None:
        ndmi_change = default_ndmi_change

    rows: list[dict] = []
    for _, seg in segments.iterrows():
        seg_id = str(seg.get("segment_id"))
        seg_rng = _segment_rng(seg_id, seed)

        veg_exposure = compute_free_data_vegetation_exposure_score(worldcover_tree_pct=_float(tree_pct))
        veg_dryness = compute_free_data_vegetation_dryness_score(sentinel2_ndmi_mean=_float(ndmi))
        veg_change = _vegetation_change_from_ndvi_delta(_float(ndvi_change))
        canopy_exposure = _canopy_exposure_score(tree_pct, ndvi)
        veg_score, veg_status = _vegetation_score(tree_pct, ndvi, ndmi)

        wf_score = _synthetic_wildfire_score(seg_id, seed)
        tx_score = _synthetic_treatment_gap(seg_id, seed)
        terrain_score = _terrain_score_from_segment(_float(seg.get("length_km")), seg_rng)

        components = {
            "vegetation_score": veg_score,
            "wildfire_score": wf_score,
            "weather_score": weather_score,
            "treatment_gap_score": tx_score,
            "outage_score": region_outage_score,
            "terrain_score": terrain_score,
        }
        planning_score = _planning_score_from_components(components)
        priority = assign_planning_priority_level(planning_score)
        r1, r2, r3 = top_contributing_reasons(components, weight_map=PLANNING_WEIGHTS, labels=REASON_LABELS)

        tree_contact_vals = {
            "vegetation_exposure_score": veg_exposure,
            "vegetation_dryness_score": veg_dryness,
            "wind_stress_score": wind_stress_score,
            "treatment_gap_score": tx_score,
            "terrain_score": terrain_score,
        }
        tree_contact_proxy, tree_contact_quality, tree_contact_missing = _tree_contact_exposure_proxy(
            tree_contact_vals
        )

        centroid = seg.geometry.centroid
        row = {
            "corridor_id": seg.get("corridor_id"),
            "segment_id": seg_id,
            "region": SURREY_REGION_NAME,
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
            "wildfire_data_status": "synthetic_proxy",
            "nearest_fire_km": None,
            "eccc_weather_stress_score": weather_score,
            "weather_data_status": weather_status,
            "wind_gust_max_kmh": wind_gust,
            "treatment_gap_score": tx_score,
            "treatment_data_status": "synthetic",
            "outage_history_proxy_score": region_outage_score,
            "outage_data_status": "unofficial_archive_proxy",
            "terrain_score": terrain_score,
            "terrain_data_status": "derived_proxy",
            "planning_priority_score": planning_score,
            "planning_priority_level": priority,
            "top_reason_1": r1,
            "top_reason_2": r2,
            "top_reason_3": r3,
            "data_source_notes": "Surrey open/free summary + synthetic wildfire/treatment proxies",
            "as_of_date": today_iso(),
            "tree_contact_exposure_proxy": tree_contact_proxy,
            "wind_stress_score": wind_stress_score,
            "wind_data_status": wind_data_status,
            "tree_contact_score_data_quality": tree_contact_quality,
            "tree_contact_missing_components": tree_contact_missing,
        }
        problem = _derive_problem_type(row)
        row["problem_type"] = problem
        row["recommended_planning_action"] = PROBLEM_TYPE_ACTIONS.get(problem, "Monitor / routine review")
        row["risk_pathway"] = RISK_PATHWAY_BY_PROBLEM.get(problem, "")
        row["explanation_short"] = EXPLANATION_BY_PROBLEM.get(problem, "")
        row.update(_scenario_scores(components, planning_score))
        rows.append(row)

    return pd.DataFrame(rows)


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_crs(4326).to_file(path, driver="GeoJSON")


def main() -> int:
    args = parse_args()
    if args.stress_only:
        if not SURREY_PLANNING_DATASET_CSV.is_file():
            print(f"Baseline missing: {SURREY_PLANNING_DATASET_CSV}")
            return 1
        baseline = pd.read_csv(SURREY_PLANNING_DATASET_CSV)
        stressed = build_stress_dataset(baseline, seed=args.seed)
        write_csv(stressed, SURREY_PLANNING_STRESS_DATASET_CSV)
        print(f"Wrote stress scenario ({len(stressed)} rows) -> {SURREY_PLANNING_STRESS_DATASET_CSV}")
        return 0

    lines, segments, buffer = build_transmission_and_segments(args.segment_km, args.buffer_m)
    write_geojson(lines, SURREY_TRANSMISSION_LINES_GEOJSON)
    write_geojson(segments, SURREY_CORRIDOR_SEGMENTS_GEOJSON)
    write_geojson(buffer, SURREY_CORRIDOR_BUFFER_GEOJSON)
    print(f"Segments: {len(segments)} -> {SURREY_CORRIDOR_SEGMENTS_GEOJSON.name}")

    planning = build_planning_dataset(segments, seed=args.seed)
    write_csv(planning, SURREY_PLANNING_DATASET_CSV)
    print(f"Planning dataset ({len(planning)} rows) -> {SURREY_PLANNING_DATASET_CSV.name}")
    if "planning_priority_level" in planning.columns:
        print("Priority breakdown:", planning["planning_priority_level"].value_counts().to_dict())

    stressed = build_stress_dataset(planning, seed=args.seed)
    write_csv(stressed, SURREY_PLANNING_STRESS_DATASET_CSV)
    print(f"Stress scenario -> {SURREY_PLANNING_STRESS_DATASET_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
