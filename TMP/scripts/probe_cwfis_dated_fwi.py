#!/usr/bin/env python3
"""Probe CWFIS WMS/WCS for dated FWI and historical fire layers."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.outage_loader import _public_http_get  # noqa: E402

WMS = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wms"
WCS = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wcs"
DATE = "2026-06-22"
BBOX = (-120.5, 49.5, -119.0, 50.5)


def main() -> None:
    content, _ = _public_http_get(
        f"{WMS}?service=WMS&version=1.3.0&request=GetCapabilities"
    )
    text = content.decode("utf-8", errors="replace")
    idx = text.lower().find("fire weather index")
    print("=== FWI layer snippet ===")
    print(text[max(0, idx - 300) : idx + 1200] if idx >= 0 else "not found")

    for layer, style in [("public:fwi", "cffdrs_fwi_col"), ("fwi", "cffdrs_fwi_col")]:
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": layer,
            "styles": style,
            "crs": "EPSG:4326",
            "bbox": f"{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}",
            "width": "400",
            "height": "400",
            "format": "image/png",
            "TIME": DATE,
        }
        url = f"{WMS}?{urlencode(params)}"
        try:
            data, _ = _public_http_get(url)
            print(f"WMS {layer} TIME={DATE}: {len(data)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"WMS {layer} failed: {exc}")

    for time_key in ("time", "TIME"):
        params = {
            "service": "WCS",
            "version": "1.0.0",
            "request": "GetCoverage",
            "coverage": "public:fwi",
            "format": "GeoTIFF",
            "bbox": f"{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}",
            "width": "200",
            "height": "200",
            "crs": "EPSG:4326",
            time_key: DATE,
        }
        url = f"{WCS}?{urlencode(params)}"
        try:
            data, _ = _public_http_get(url)
            print(f"WCS {time_key}={DATE}: {len(data)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"WCS {time_key} failed: {exc}")

    # WFS fire layers
    wfs = "https://cwfis.cfs.nrcan.gc.ca/geoserver/public/ows"
    for typename in ("public:activefires", "public:fire_perimeters", "public:hotspots_24h"):
        params = urlencode(
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": typename,
                "outputFormat": "application/json",
                "count": "5",
            }
        )
        try:
            data, _ = _public_http_get(f"{wfs}?{params}")
            print(f"WFS {typename}: {len(data)} bytes")
        except Exception as exc:  # noqa: BLE001
            print(f"WFS {typename} failed: {exc}")


if __name__ == "__main__":
    main()
