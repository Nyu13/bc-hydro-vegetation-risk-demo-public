#!/usr/bin/env python3
"""Run all Okanagan demo pipeline stages in order; continue on optional failures."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

STAGES: list[tuple[str, str, bool]] = [
    ("transmission_corridors", "build_okanagan_transmission_corridors.py", True),
    ("bc_transmission_lines", "build_bc_transmission_lines.py", False),
    ("outage_proxy", "build_okanagan_outage_proxy.py", False),
    ("weather_stress", "build_okanagan_weather_stress.py", False),
    ("sentinel2", "build_okanagan_sentinel2_indices.py", False),
    ("worldcover", "build_okanagan_worldcover_stats.py", False),
    ("wildfire", "build_okanagan_wildfire_exposure.py", False),
    ("fwi_sample", "build_okanagan_fwi_sample.py", False),
    ("treatment_gap", "build_okanagan_synthetic_treatment_gap.py", False),
    ("planning_dataset", "build_okanagan_planning_dataset.py", True),
]

PLANNING_CSV = PROJECT_ROOT / "data" / "processed" / "okanagan_vegetation_wildfire_planning_dataset.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    return parser.parse_args()


def run_stage(python: str, script: str) -> tuple[int, str]:
    path = SCRIPT_DIR / script
    print(f"\n=== {script} ===")
    result = subprocess.run([python, str(path)], cwd=str(PROJECT_ROOT), check=False, capture_output=True, text=True)
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout:
        print(stdout.rstrip())
    if stderr:
        print(stderr.rstrip(), file=sys.stderr)
    return int(result.returncode), stdout + stderr


def validate_outputs() -> dict:
    report: dict = {"ok": False, "row_count": 0, "priorities": {}, "top10": [], "missing": {}, "layers": {}}
    if not PLANNING_CSV.is_file():
        report["error"] = f"Missing {PLANNING_CSV}"
        return report

    df = pd.read_csv(PLANNING_CSV)
    report["row_count"] = len(df)
    report["ok"] = len(df) > 0

    score_col = "planning_priority_score"
    if score_col in df.columns:
        report["missing"]["planning_priority_score"] = int(df[score_col].isna().sum())
        report["priorities"] = df.get("planning_priority_level", pd.Series(dtype=str)).value_counts().to_dict()
        top = df.sort_values(score_col, ascending=False).head(10)
        report["top10"] = top[
            [c for c in ("segment_id", "planning_priority_score", "planning_priority_level", "top_reason_1") if c in top.columns]
        ].to_dict(orient="records")

    status_cols = [c for c in df.columns if c.endswith("_data_status")]
    for col in status_cols:
        report["layers"][col] = df[col].value_counts().to_dict() if col in df.columns else {}

    return report


def main() -> int:
    args = parse_args()
    exit_code = 0
    stage_results: dict[str, str] = {}

    for name, script, required in STAGES:
        code, output = run_stage(args.python, script)
        stage_results[name] = "ok" if code == 0 else f"exit {code}"
        if code != 0:
            msg = f"Stage {name} ({script}) exited {code}"
            if required:
                print(f"ERROR: {msg}")
                exit_code = code
            else:
                print(f"WARNING: {msg} — continuing")

    print("\n=== Pipeline summary ===")
    report = validate_outputs()
    print(f"Planning dataset: {PLANNING_CSV} ({'found' if report['ok'] else 'MISSING'})")
    print(f"Segment rows: {report['row_count']}")
    print(f"Priority breakdown: {report.get('priorities', {})}")
    print(f"Missing planning scores: {report.get('missing', {})}")
    print("Stage status:", stage_results)

    if report.get("top10"):
        print("\nTop 10 corridors by planning_priority_score:")
        for row in report["top10"]:
            print(
                f"  {row.get('segment_id')}: score={row.get('planning_priority_score')} "
                f"level={row.get('planning_priority_level')} — {row.get('top_reason_1')}"
            )

    if report.get("layers"):
        print("\nLayer data status counts:")
        for layer, counts in report["layers"].items():
            print(f"  {layer}: {counts}")

    if not report["ok"]:
        return 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
