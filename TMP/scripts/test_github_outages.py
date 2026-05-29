"""Fetch GitHub bchydro-outages and verify row/polygon counts in pilot bbox (TMP)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import DEMO_PILOT_TRANSMISSION_BBOX
from src.outage_loader import load_github_bchydro_outages, outage_has_polygon_row


def _in_pilot_bbox(lat: float, lon: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = DEMO_PILOT_TRANSMISSION_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def main() -> None:
    df = load_github_bchydro_outages(allow_synthetic_fallback=False)
    poly_count = int(df.apply(outage_has_polygon_row, axis=1).sum()) if not df.empty else 0
    print(f"github rows: {len(df)}")
    print(f"rows with polygon geometry: {poly_count}")
    if df.empty:
        print("no rows (check network/TLS)")
        return

    pilot_ids: list[str] = []
    for _, row in df.iterrows():
        lat = row.get("out_lat")
        lon = row.get("out_lon")
        if lat is not None and lon is not None:
            try:
                if _in_pilot_bbox(float(lat), float(lon)):
                    pilot_ids.append(str(row.get("outage_id", "")))
            except (TypeError, ValueError):
                pass

    print(f"pilot bbox point matches: {len(pilot_ids)}")
    if pilot_ids:
        print(f"sample pilot outage_id: {pilot_ids[0]}")
        sample = df[df["outage_id"].astype(str) == pilot_ids[0]].iloc[0]
        print(
            f"  municipality={sample.get('municipality')} "
            f"out_lat={sample.get('out_lat')} out_lon={sample.get('out_lon')} "
            f"poly={sample.get('outage_has_polygon')}"
        )
        feat = sample.get("outage_geojson")
        if isinstance(feat, dict):
            ring = feat.get("geometry", {}).get("coordinates", [[]])[0]
            if ring:
                print(f"  first ring pt [lon,lat]: {ring[0]}")


if __name__ == "__main__":
    main()
