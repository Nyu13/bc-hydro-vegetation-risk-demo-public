#!/usr/bin/env python3
"""
Synthetic vegetation treatment gap for Okanagan corridor segments.

Deterministic seed=42 — demonstrates where BC Hydro internal treatment records would fit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    OKANAGAN_PROCESSED_DIR,
    load_okanagan_segments,
    today_iso,
    write_csv,
)

OUTPUT = OKANAGAN_PROCESSED_DIR / "okanagan_synthetic_treatment_gap.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments)
    rng = np.random.default_rng(args.seed)

    rows: list[dict] = []
    for _, seg in segments.iterrows():
        seg_id = str(seg.get("segment_id"))
        seg_seed = args.seed + (hash(seg_id) % 10_000)
        local_rng = np.random.default_rng(seg_seed)
        months_since = int(local_rng.integers(6, 84))
        treatment_gap_score = round(float(np.clip(months_since / 72.0 * 100.0, 0, 100)), 2)
        rows.append(
            {
                "corridor_id": seg.get("corridor_id"),
                "segment_id": seg_id,
                "region": seg.get("region"),
                "months_since_last_treatment": months_since,
                "synthetic_treatment_gap_score": treatment_gap_score,
                "treatment_gap_score": treatment_gap_score,
                "data_status": "synthetic_demo",
                "data_source": "Deterministic synthetic (seed=42) — replace with BC Hydro vegetation records",
                "as_of_date": today_iso(),
                "notes": (
                    "Synthetic treatment recency gap for proof-of-process only. "
                    "BC Hydro internal patrol/trim/work-management data would replace this layer."
                ),
            }
        )

    df = pd.DataFrame(rows)
    write_csv(df, OUTPUT)
    print(f"Wrote {OUTPUT} ({len(df)} segments, synthetic seed={args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
