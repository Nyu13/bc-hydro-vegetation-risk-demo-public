"""Verify BC Hydro JSON lat/lon and polygon ring order (TMP)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import DEMO_PILOT_MUNICIPALITY
from src.area_selection import lookup_municipality_coordinates
from src.outage_loader import load_bchydro_outage_json


def main() -> None:
    df = load_bchydro_outage_json(allow_synthetic_fallback=False)
    print(f"live rows: {len(df)}")
    for i in range(min(5, len(df))):
        row = df.iloc[i]
        print(
            i,
            row.get("municipality"),
            f"lat={row.get('out_lat')}",
            f"lon={row.get('out_lon')}",
            f"poly={row.get('outage_has_polygon')}",
        )
        feat = row.get("outage_geojson")
        if isinstance(feat, dict):
            ring = feat.get("geometry", {}).get("coordinates", [[]])[0]
            if ring:
                print("  first ring pt [lon,lat]:", ring[0])

    surrey = lookup_municipality_coordinates(DEMO_PILOT_MUNICIPALITY)
    print(f"{DEMO_PILOT_MUNICIPALITY} centroid (lat, lon):", surrey)
    assert surrey is not None
    assert 49.0 < surrey[0] < 49.5 and -123.0 < surrey[1] < -122.5


if __name__ == "__main__":
    main()
