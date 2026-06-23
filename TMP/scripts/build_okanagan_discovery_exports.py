#!/usr/bin/env python3
"""
Build Okanagan causal-discovery CSV exports from the planning dataset.

Input:  data/processed/okanagan_vegetation_wildfire_planning_dataset.csv
Output: okanagan_discovery_raw.csv
        okanagan_discovery_with_targets.csv
        okanagan_discovery_export_qa.csv

Column mappings (planning dataset -> discovery export):
  eccc_wind_gust_max_kmh      <- wind_gust_max_kmh
  weather_stress_score        <- eccc_weather_stress_score
  distance_to_active_fire_km  <- nearest_fire_km
  worldcover_tree_pct         <- worldcover_tree_pct (same)
  worldcover_shrub_grass_pct  <- worldcover_shrub_grass_pct (same)
  sentinel2_ndvi_mean         <- sentinel2_ndvi_mean (same)
  sentinel2_ndmi_mean         <- sentinel2_ndmi_mean (same)
  vegetation_dryness_score    <- vegetation_dryness_score (same)
  wildfire_exposure_score     <- wildfire_exposure_score (same)
  planning_priority_score     <- planning_priority_score (same, with_targets only)
  tree_contact_exposure_proxy <- tree_contact_exposure_proxy (same, with_targets only)
  outage_history_proxy_score  <- outage_history_proxy_score (same, with_targets only)

Requested columns with no source mapping in the planning dataset (omitted):
  eccc_temperature_mean_c, eccc_precip_total_mm, fire_danger_score,
  distance_to_hotspot_km, public_outage_count, public_customers_affected,
  tree_related_outage_proxy, weather_related_outage_proxy

Identifiers, text, geometry, dates, reason fields, recommended actions,
scenario columns, and synthetic treatment fields are excluded by design
(only whitelisted discovery columns are exported).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DEFAULT_INPUT = PROCESSED_DIR / "okanagan_vegetation_wildfire_planning_dataset.csv"
OUTPUT_RAW = PROCESSED_DIR / "okanagan_discovery_raw.csv"
OUTPUT_WITH_TARGETS = PROCESSED_DIR / "okanagan_discovery_with_targets.csv"
OUTPUT_QA = PROCESSED_DIR / "okanagan_discovery_export_qa.csv"

# source_column -> export_column (only mapped when source exists)
COLUMN_MAP: dict[str, str] = {
    "eccc_temperature_mean_c": "eccc_temperature_mean_c",
    "eccc_precip_total_mm": "eccc_precip_total_mm",
    "wind_gust_max_kmh": "eccc_wind_gust_max_kmh",
    "eccc_wind_gust_max_kmh": "eccc_wind_gust_max_kmh",
    "eccc_weather_stress_score": "weather_stress_score",
    "weather_stress_score": "weather_stress_score",
    "worldcover_tree_pct": "worldcover_tree_pct",
    "worldcover_shrub_grass_pct": "worldcover_shrub_grass_pct",
    "sentinel2_ndvi_mean": "sentinel2_ndvi_mean",
    "sentinel2_ndmi_mean": "sentinel2_ndmi_mean",
    "vegetation_dryness_score": "vegetation_dryness_score",
    "fire_danger_score": "fire_danger_score",
    "wildfire_exposure_score": "wildfire_exposure_score",
    "nearest_fire_km": "distance_to_active_fire_km",
    "distance_to_active_fire_km": "distance_to_active_fire_km",
    "distance_to_hotspot_km": "distance_to_hotspot_km",
    "public_outage_count": "public_outage_count",
    "public_customers_affected": "public_customers_affected",
    "tree_related_outage_proxy": "tree_related_outage_proxy",
    "tree_related_outage_count_proxy": "tree_related_outage_proxy",
    "weather_related_outage_proxy": "weather_related_outage_proxy",
    "weather_related_outage_count_proxy": "weather_related_outage_proxy",
}

DISCOVERY_RAW_COLUMNS = [
    "eccc_temperature_mean_c",
    "eccc_precip_total_mm",
    "eccc_wind_gust_max_kmh",
    "weather_stress_score",
    "worldcover_tree_pct",
    "worldcover_shrub_grass_pct",
    "sentinel2_ndvi_mean",
    "sentinel2_ndmi_mean",
    "vegetation_dryness_score",
    "fire_danger_score",
    "wildfire_exposure_score",
    "distance_to_active_fire_km",
    "distance_to_hotspot_km",
    "public_outage_count",
    "public_customers_affected",
    "tree_related_outage_proxy",
    "weather_related_outage_proxy",
]

TARGET_COLUMNS = [
    "planning_priority_score",
    "tree_contact_exposure_proxy",
    "outage_history_proxy_score",
]

TARGET_SOURCE_MAP: dict[str, str] = {
    "planning_priority_score": "planning_priority_score",
    "tree_contact_exposure_proxy": "tree_contact_exposure_proxy",
    "outage_history_proxy_score": "outage_history_proxy_score",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-raw", type=Path, default=OUTPUT_RAW)
    parser.add_argument("--output-with-targets", type=Path, default=OUTPUT_WITH_TARGETS)
    parser.add_argument("--output-qa", type=Path, default=OUTPUT_QA)
    return parser.parse_args()


def _resolve_columns(
    source: pd.DataFrame,
    requested: list[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Return export_name -> source_name, present export cols, absent export cols."""
    export_to_source: dict[str, str] = {}
    for export_col in requested:
        candidates = [src for src, dst in COLUMN_MAP.items() if dst == export_col]
        found = next((c for c in candidates if c in source.columns), None)
        if found is not None:
            export_to_source[export_col] = found
    present = [c for c in requested if c in export_to_source]
    absent = [c for c in requested if c not in export_to_source]
    return export_to_source, present, absent


def _build_export_frame(
    source: pd.DataFrame,
    export_to_source: dict[str, str],
    column_order: list[str],
) -> pd.DataFrame:
    present = [c for c in column_order if c in export_to_source]
    out = pd.DataFrame(index=source.index)
    for export_col in present:
        out[export_col] = source[export_to_source[export_col]]
    return out[present]


def _missing_value_pct(df: pd.DataFrame) -> float:
    if df.empty or df.size == 0:
        return 0.0
    return round(float(df.isna().sum().sum() / df.size * 100.0), 4)


def _per_column_missing_notes(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    parts: list[str] = []
    for col in df.columns:
        pct = df[col].isna().mean() * 100.0
        if pct > 0:
            parts.append(f"{col}={pct:.2f}%")
    return "; ".join(parts)


def _qa_row(
    file_name: str,
    df: pd.DataFrame,
    target_columns_present: str,
    notes: str,
) -> dict[str, object]:
    return {
        "file_name": file_name,
        "row_count": len(df),
        "column_count": len(df.columns),
        "missing_value_pct": _missing_value_pct(df),
        "target_columns_present": target_columns_present,
        "notes": notes,
    }


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 1

    source = pd.read_csv(args.input)
    input_rows = len(source)

    raw_map, raw_present, raw_absent = _resolve_columns(source, DISCOVERY_RAW_COLUMNS)
    raw_df = _build_export_frame(source, raw_map, DISCOVERY_RAW_COLUMNS)

    target_map = {
        export_col: TARGET_SOURCE_MAP[export_col]
        for export_col in TARGET_COLUMNS
        if TARGET_SOURCE_MAP[export_col] in source.columns
    }
    target_absent = [c for c in TARGET_COLUMNS if c not in target_map]

    with_targets_cols = raw_present + [c for c in TARGET_COLUMNS if c in target_map]
    with_targets_df = _build_export_frame(
        source,
        {**raw_map, **{k: v for k, v in target_map.items()}},
        with_targets_cols,
    )

    rows_before = len(with_targets_df)
    if target_map:
        required = list(target_map.keys())
        with_targets_df = with_targets_df.dropna(subset=required)
    rows_dropped = rows_before - len(with_targets_df)

    args.output_raw.parent.mkdir(parents=True, exist_ok=True)
    raw_df.to_csv(args.output_raw, index=False)
    with_targets_df.to_csv(args.output_with_targets, index=False)

    raw_missing_notes = _per_column_missing_notes(raw_df)
    targets_missing_notes = _per_column_missing_notes(with_targets_df)

    qa_rows = [
        _qa_row(
            args.output_raw.name,
            raw_df,
            "no",
            (
                f"Input rows={input_rows}; "
                f"absent_requested_columns={','.join(raw_absent) or 'none'}; "
                f"missing_by_column={raw_missing_notes or 'none'}"
            ),
        ),
        _qa_row(
            args.output_with_targets.name,
            with_targets_df,
            ",".join(target_map.keys()) if target_map else "none",
            (
                f"Input rows={input_rows}; dropped_missing_targets={rows_dropped}; "
                f"absent_target_columns={','.join(target_absent) or 'none'}; "
                f"absent_raw_columns={','.join(raw_absent) or 'none'}; "
                f"missing_by_column={targets_missing_notes or 'none'}"
            ),
        ),
    ]
    qa_df = pd.DataFrame(qa_rows)
    qa_df.to_csv(args.output_qa, index=False)

    print(f"Input: {args.input} ({input_rows} rows, {len(source.columns)} columns)")
    print(f"Mapped discovery columns ({len(raw_present)}): {', '.join(raw_present)}")
    print(f"Absent from source ({len(raw_absent)}): {', '.join(raw_absent) or 'none'}")
    print(f"Wrote {args.output_raw} ({len(raw_df)} rows, {len(raw_df.columns)} cols)")
    print(
        f"Wrote {args.output_with_targets} "
        f"({len(with_targets_df)} rows, {len(with_targets_df.columns)} cols; "
        f"dropped {rows_dropped} rows with missing targets)"
    )
    print(f"Wrote {args.output_qa}")
    print(f"Raw missing value %: {_missing_value_pct(raw_df)}")
    print(f"With-targets missing value %: {_missing_value_pct(with_targets_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
