"""Probe Risk Map pilot layers and tooltip_text (TMP)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import DEMO_PILOT_TRANSMISSION_BBOX
from src.outage_loader import load_bchydro_outage_json, load_bchydro_rss

# Import helpers without running Streamlit UI
from app import (  # noqa: E402
    _filter_outages_for_risk_map,
    _outage_polygon_features,
    _prepare_outage_map_points,
)


def main() -> None:
    j = load_bchydro_outage_json(allow_synthetic_fallback=False)
    r = load_bchydro_rss(allow_synthetic_fallback=False)
    pj = _filter_outages_for_risk_map(j)
    pr = _filter_outages_for_risk_map(r)
    print("pilot bbox:", DEMO_PILOT_TRANSMISSION_BBOX)
    print(f"pilot json {len(pj)}/{len(j)}  pilot rss {len(pr)}/{len(r)}")

    polys = _outage_polygon_features(pj)
    print("json polygons on map:", len(polys))
    for f in polys:
        p = f.get("properties", {})
        muni = p.get("municipality", "")
        if "Vancouver" in str(muni) or "Surrey" in str(muni):
            tip = (p.get("tooltip_text") or "").replace("\n", " | ")
            print(f"  poly {p.get('outage_id')} {muni}: {tip[:100]}...")

    pts = _prepare_outage_map_points(pj, feed_label="BC Hydro JSON")
    rss_pts = _prepare_outage_map_points(pr, feed_label="BC Hydro RSS")
    print("json points on map:", len(pts))
    print("rss points on map:", len(rss_pts))
    for _, row in pts.iterrows():
        tip = (row.get("tooltip_text") or "").replace("\n", " | ")
        print(f"  pt {row.get('outage_id')} {row.get('municipality')}: {tip[:100]}")


if __name__ == "__main__":
    main()
