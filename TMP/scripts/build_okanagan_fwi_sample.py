#!/usr/bin/env python3
"""
Sample CWFIS Fire Weather Index (FWI) at Okanagan corridor segment centroids.

Uses open GeoServer WCS (public:fwi) — not BC Hydro internal data.
"""

from __future__ import annotations

import argparse
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

from src.config import OKANAGAN_FWI_CORRIDOR_CSV, OKANAGAN_FWI_SAMPLE_CSV  # noqa: E402
from src.cwfis_fwi import CWFIS_FWI_SOURCE_LABEL, fetch_fwi_samples  # noqa: E402
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_REGION_NAME  # noqa: E402

from _okanagan_pipeline_common import (  # noqa: E402
    DEFAULT_SEGMENTS_GEOJSON,
    load_okanagan_segments,
    today_iso,
    write_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS_GEOJSON)
    return parser.parse_args()


def _fwi_risk_band(value: float | None) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "unknown"
    if value < 5:
        return "low"
    if value < 10:
        return "moderate"
    if value < 20:
        return "high"
    return "extreme"


def main() -> int:
    args = parse_args()
    segments = load_okanagan_segments(args.segments).to_crs(4326)
    centroids = segments.geometry.centroid
    values, status = fetch_fwi_samples(
        None,
        centroids.x.tolist(),
        centroids.y.tolist(),
        auto_bbox=True,
        fallback_bbox=OKANAGAN_AOI_BBOX,
    )

    rows: list[dict] = []
    for (_, seg), lon, lat, fwi in zip(
        segments.iterrows(),
        centroids.x.tolist(),
        centroids.y.tolist(),
        values,
        strict=True,
    ):
        rows.append(
            {
                "corridor_id": seg.get("corridor_id"),
                "segment_id": seg.get("segment_id"),
                "region": seg.get("region", OKANAGAN_REGION_NAME),
                "centroid_lat": round(float(lat), 6),
                "centroid_lon": round(float(lon), 6),
                "fwi_value": fwi,
                "fwi_risk_band": _fwi_risk_band(fwi),
                "data_status": status,
                "data_source": CWFIS_FWI_SOURCE_LABEL,
                "as_of_date": today_iso(),
            }
        )

    df = pd.DataFrame(rows)
    write_csv(df, OKANAGAN_FWI_CORRIDOR_CSV)
    write_csv(df, OKANAGAN_FWI_SAMPLE_CSV)
    valid = int(df["fwi_value"].notna().sum())
    print(
        f"Wrote {OKANAGAN_FWI_CORRIDOR_CSV} and {OKANAGAN_FWI_SAMPLE_CSV} "
        f"({len(df)} segments, {valid} with FWI values, status={status})"
    )
    if valid:
        print(
            f"  FWI range: {df['fwi_value'].min():.1f} – {df['fwi_value'].max():.1f} "
            f"(median {df['fwi_value'].median():.1f})"
        )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
