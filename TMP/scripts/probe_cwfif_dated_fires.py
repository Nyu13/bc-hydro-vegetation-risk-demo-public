#!/usr/bin/env python3
"""Probe CWFIF WFS for fires on a specific date."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.outage_loader import _public_http_get  # noqa: E402
from src.regions import OKANAGAN_AOI_BBOX  # noqa: E402

DATE = "2026-06-22"
CWFIF_WFS = "https://geoserver.cwfif.nrcan.gc.ca/geoserver/ows"


def _fetch(cql: str) -> None:
    params = urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": "public:cwfif_national_activefires",
            "outputFormat": "application/json",
            "CQL_FILTER": cql,
            "count": "50",
        }
    )
    url = f"{CWFIF_WFS}?{params}"
    data, _ = _public_http_get(url)
    payload = json.loads(data.decode("utf-8"))
    features = payload.get("features") or []
    print(f"CQL ({cql[:70]}...): {len(features)} features")
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    in_aoi = 0
    for feat in features:
        props = feat.get("properties") or {}
        lat = props.get("latitude")
        lon = props.get("longitude")
        if lat is not None and lon is not None:
            if min_lat <= float(lat) <= max_lat and min_lon <= float(lon) <= max_lon:
                in_aoi += 1
    print(f"  in Okanagan AOI: {in_aoi}")
    if features:
        props = features[0].get("properties") or {}
        print("  sample keys:", list(props.keys())[:12])


def main() -> None:
    ts = f"{DATE}T12:00:00Z"
    _fetch(f"agency_code='BC' AND '{ts}'>=record_start AND '{ts}'<=record_end")
    _fetch("agency_code='BC' AND now()>=record_start AND now()<=record_end")


if __name__ == "__main__":
    main()
