#!/usr/bin/env python3
"""Verify pydeck BitmapLayer accepts base64 PNG for FWI overlay."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pydeck as pdk

from src.okanagan_map_layers import okanagan_fwi_bitmap_layer
from src.okanagan_temporal_map import fetch_fwi_raster_for_date, fwi_png_to_pydeck_image


def main() -> None:
    png, bbox, status = fetch_fwi_raster_for_date("2026-06-11")
    print("fetch", status, len(png) if png else None)
    assert png is not None

    layer = okanagan_fwi_bitmap_layer(png, bbox)
    payload = json.loads(layer.to_json())
    image_field = payload["image"]
    print("image type:", type(image_field))
    print("image prefix:", str(image_field)[:100])
    assert isinstance(image_field, str)
    assert "data:image/png;base64," in image_field
    assert len(image_field) > 5000, f"image too short: {len(image_field)}"

    img = fwi_png_to_pydeck_image(png)
    assert str(img).startswith('"data:image/png;base64,')
    print("OK: BitmapLayer image serializes as base64 data URL")


if __name__ == "__main__":
    main()
