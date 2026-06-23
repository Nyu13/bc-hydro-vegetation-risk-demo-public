#!/usr/bin/env python3
"""
Build synthetic stress-scenario variant of the Okanagan planning dataset.

Reads the baseline planning CSV (does not modify it), applies deterministic
score boosts on selected corridor segments, and recalculates derived planning
fields using the same helpers as build_okanagan_planning_dataset.py.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_okanagan_planning_dataset import (  # noqa: E402
    EXPLANATION_BY_PROBLEM,
    PLANNING_WEIGHTS,
    PROBLEM_TYPE_ACTIONS,
    REASON_LABELS,
    RISK_PATHWAY_BY_PROBLEM,
    _derive_problem_type,
    _planning_score_from_components,
    _scenario_scores,
    _tree_contact_exposure_proxy,
)
from src.risk_scoring import normalize_score  # noqa: E402
from _okanagan_pipeline_common import (  # noqa: E402
    OKANAGAN_PROCESSED_DIR,
    assign_planning_priority_level,
    top_contributing_reasons,
    write_csv,
)

BASELINE_CSV = OKANAGAN_PROCESSED_DIR / "okanagan_vegetation_wildfire_planning_dataset.csv"
OUTPUT_CSV = OKANAGAN_PROCESSED_DIR / "okanagan_vegetation_wildfire_planning_dataset_stress_scenario.csv"

SCENARIO_MODE = "synthetic_stress_scenario"
SCENARIO_NOTES = (
    "Synthetic stress scenario — illustrative only. Not observed BC Hydro data. "
    "Elevated treatment gap, vegetation dryness, ECCC weather stress, and wildfire "
    "exposure on multi-signal corridor segments; planning priority recalculated with "
    "the baseline composite formula (seed=42)."
)

CANDIDATE_THRESHOLDS = {
    "vegetation_exposure_score": 55,
    "vegetation_dryness_score": 60,
    "wildfire_exposure_score": 40,
    "treatment_gap_score": 60,
    "tree_contact_exposure_proxy": 60,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASELINE_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _row_rng(segment_id: str, seed: int) -> np.random.Generator:
    token = f"{seed}:{segment_id}".encode()
    digest = int.from_bytes(hashlib.md5(token).digest()[:4], "big")
    return np.random.default_rng(digest)


def _criteria_count(row: pd.Series) -> int:
    return int(
        sum(
            float(row.get(col, 0) or 0) >= threshold
            for col, threshold in CANDIDATE_THRESHOLDS.items()
        )
    )


def is_stress_candidate(row: pd.Series) -> bool:
    return _criteria_count(row) >= 1


def _apply_stress_boosts(row: pd.Series, rng: np.random.Generator) -> dict[str, float]:
    """Return boosted score fields for a stress candidate (tiered by signal count)."""
    criteria_n = _criteria_count(row)
    # Dryness is saturated at 100 in baseline — only boost when other signals are present.
    if criteria_n <= 1:
        return {}

    if criteria_n >= 4:
        treatment = max(float(row["treatment_gap_score"]), rng.uniform(85, 98))
        weather = max(float(row["eccc_weather_stress_score"]), rng.uniform(75, 90))
        wildfire = max(float(row["wildfire_exposure_score"]), rng.uniform(78, 95))
    elif criteria_n == 3:
        treatment = max(float(row["treatment_gap_score"]), rng.uniform(75, 90))
        weather = max(float(row["eccc_weather_stress_score"]), rng.uniform(60, 78))
        wildfire = max(float(row["wildfire_exposure_score"]), rng.uniform(55, 78))
    else:
        treatment = max(float(row["treatment_gap_score"]), rng.uniform(75, 80))
        weather = max(float(row["eccc_weather_stress_score"]), rng.uniform(55, 65))
        wildfire = max(float(row["wildfire_exposure_score"]), rng.uniform(50, 62))

    dryness = max(float(row["vegetation_dryness_score"]), rng.uniform(65, 90))
    return {
        "treatment_gap_score": round(treatment, 2),
        "vegetation_dryness_score": round(dryness, 2),
        "eccc_weather_stress_score": round(weather, 2),
        "wildfire_exposure_score": round(wildfire, 2),
    }


def _vegetation_score_from_parts(
    exposure: float,
    dryness: float,
    ndvi: float | None,
) -> float:
    ndvi_boost = (
        normalize_score(float(ndvi), 0, 0.8)
        if ndvi is not None and not (isinstance(ndvi, float) and pd.isna(ndvi))
        else 50.0
    )
    return round(0.55 * float(exposure) + 0.25 * float(dryness) + 0.20 * ndvi_boost, 2)


def _recalculate_derived_fields(row: dict) -> dict:
    veg_score = _vegetation_score_from_parts(
        row["vegetation_exposure_score"],
        row["vegetation_dryness_score"],
        row.get("sentinel2_ndvi_mean"),
    )
    row["vegetation_score"] = veg_score

    components = {
        "vegetation_score": veg_score,
        "wildfire_score": float(row["wildfire_exposure_score"]),
        "weather_score": float(row["eccc_weather_stress_score"]),
        "treatment_gap_score": float(row["treatment_gap_score"]),
        "outage_score": float(row["outage_history_proxy_score"]),
        "terrain_score": float(row["terrain_score"]),
    }
    planning_score = _planning_score_from_components(components)
    row["planning_priority_score"] = planning_score
    row["planning_priority_level"] = assign_planning_priority_level(planning_score)

    r1, r2, r3 = top_contributing_reasons(
        components,
        weight_map=PLANNING_WEIGHTS,
        labels=REASON_LABELS,
    )
    row["top_reason_1"] = r1
    row["top_reason_2"] = r2
    row["top_reason_3"] = r3

    tree_contact_vals = {
        "vegetation_exposure_score": float(row["vegetation_exposure_score"]),
        "vegetation_dryness_score": float(row["vegetation_dryness_score"]),
        "wind_stress_score": row.get("wind_stress_score"),
        "treatment_gap_score": float(row["treatment_gap_score"]),
        "terrain_score": float(row["terrain_score"]),
    }
    tree_contact_proxy, tree_contact_quality, tree_contact_missing = _tree_contact_exposure_proxy(
        tree_contact_vals
    )
    row["tree_contact_exposure_proxy"] = tree_contact_proxy
    row["tree_contact_score_data_quality"] = tree_contact_quality
    row["tree_contact_missing_components"] = tree_contact_missing

    problem_type = _derive_problem_type(row)
    row["problem_type"] = problem_type
    row["risk_pathway"] = RISK_PATHWAY_BY_PROBLEM[problem_type]
    row["recommended_planning_action"] = PROBLEM_TYPE_ACTIONS[problem_type]
    row["explanation_short"] = EXPLANATION_BY_PROBLEM[problem_type]
    row.update(_scenario_scores(components, planning_score))
    return row


def build_stress_dataset(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rows: list[dict] = []
    boosted = 0
    for _, baseline in df.iterrows():
        row = baseline.to_dict()
        row["scenario_mode"] = SCENARIO_MODE
        row["scenario_notes"] = SCENARIO_NOTES

        if is_stress_candidate(baseline) and _criteria_count(baseline) > 1:
            rng = _row_rng(str(baseline["segment_id"]), seed)
            boosts = _apply_stress_boosts(baseline, rng)
            if boosts:
                row.update(boosts)
                boosted += 1

        row = _recalculate_derived_fields(row)
        rows.append(row)

    out = pd.DataFrame(rows)
    print(f"Stress boosts applied to {boosted} / {len(df)} segments")
    if not out.empty and "planning_priority_level" in out.columns:
        print("Priority breakdown:", out["planning_priority_level"].value_counts().to_dict())
    return out


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        print(f"ERROR: baseline dataset not found: {args.input}")
        return 1

    baseline = pd.read_csv(args.input)
    if baseline.empty:
        print(f"ERROR: baseline dataset empty: {args.input}")
        return 1

    stress_df = build_stress_dataset(baseline, seed=args.seed)
    write_csv(stress_df, args.output)
    print(f"Wrote {args.output} ({len(stress_df)} segments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
