"""
Export Ville de Montréal 2020 transmission-line GPKG to bundled demo GeoJSON (WGS84).

Run from repo root:
  python TMP/scripts/export_montreal_transmission_sample.py

Input (optional local copy, gitignored):
  data/lignes-transport-electrique-2020.gpkg

Output (committed for Streamlit Cloud):
  data/demo/demo_montreal_transmission_lines_sample.geojson
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[2]
GPKG_PATH = REPO_ROOT / "data" / "lignes-transport-electrique-2020.gpkg"
OUT_PATH = REPO_ROOT / "data" / "demo" / "demo_montreal_transmission_lines_sample.geojson"
LAYER = "carto_ser_ele_tel_aerien"


def main() -> None:
    if not GPKG_PATH.exists():
        raise FileNotFoundError(
            f"Missing {GPKG_PATH}. Download from donnees.montreal.ca (see docs/data_sources.md)."
        )

    gdf = gpd.read_file(GPKG_PATH, layer=LAYER)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:2950")
    gdf = gdf.to_crs(4326)
    gdf = gdf.rename(columns={"ID": "line_id"})
    keep = [c for c in ("line_id", "SOURCE", "DIFFUSEUR", "VERSION") if c in gdf.columns]
    gdf = gdf[keep + ["geometry"]]
    gdf["dataset_note"] = (
        "Ville de Montréal open data 2020 — aerial HV lines (Montréal metro only, not BC Hydro)."
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT_PATH, driver="GeoJSON")

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {len(gdf)} features to {OUT_PATH} ({size_kb:.1f} KB)")
    print("bounds WGS84:", gdf.total_bounds.tolist())


if __name__ == "__main__":
    main()
