# Free Data Pipeline Runbook — Surrey PoC

Step-by-step commands to build `data/processed/surrey_free_data_corridor_summary.csv` for **Public/proxy only** vegetation scoring.

## Prerequisites

```powershell
pip install -r requirements.txt
```

Optional credentials (stub rows written if missing):

| Variable | Purpose |
| --- | --- |
| `CDSE_USERNAME` / `CDSE_PASSWORD` | Sentinel-2 NDVI/NDMI (Phase 2) |
| `EARTHDATA_USERNAME` | NASA MODIS MOD11A1 LST |
| `CDSAPI_KEY` | ERA5-Land soil moisture |

## Quick start (static land cover only)

Downloads ESA WorldCover 2021 tile **N48W123** (~74 MB) when network allows:

```powershell
python TMP/scripts/run_surrey_free_data_pipeline.py --static-only
```

Outputs:

| File | Description |
| --- | --- |
| `data/processed/surrey_worldcover_corridor_stats.csv` | Tree / shrub-grass / built / bare % |
| `data/processed/surrey_nalcms_corridor_stats.csv` | NALCMS stub or forest % |
| `data/processed/surrey_free_data_corridor_summary.csv` | Merged schema + demo scores |

## Full pipeline

```powershell
python TMP/scripts/run_surrey_free_data_pipeline.py
```

Stages:

1. `build_surrey_static_landcover.py` — WorldCover + NALCMS zonal stats
2. `build_surrey_sentinel2_indices.py` — Sentinel-2 stub or future CDSE stats
3. `build_surrey_environmental_stress.py` — MODIS/ERA5 or ECCC temperature fallback
4. `build_surrey_vri_stats.py` — BC VRI WFS clip
5. `build_surrey_terrain_stats.py` — DEM slope (optional Copernicus DEM fetch)
6. `build_surrey_lidar_notes.py` → `docs/surrey_lidar_canopy_height_plan.md`
7. `build_surrey_free_data_summary.py` — merge + scoring

## Manual raster paths

```powershell
python TMP/scripts/build_surrey_static_landcover.py `
  --aoi data/demo/surrey_transmission_buffer_200m.geojson `
  --worldcover-raster data/raw/surrey/worldcover/ESA_WorldCover_10m_2021_v200_N48W123_Map.tif `
  --nalcms-raster data/raw/surrey/nalcms/nalcms_2020_bc.tif `
  --out-dir data/processed
```

WorldCover direct URL:  
https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N48W123_Map.tif

## App integration

- `src/free_data_loader.py` loads processed summary (or `data/demo/surrey_free_data_corridor_summary_placeholder.csv`).
- **Planet sample enabled** takes priority over open/free data.
- **Public/proxy only** uses open/free scores when summary exists (`data_status=open_free_processed` or stub with partial stats).
- Provenance: 🟦 Open/free processed in Data Sources tab.

## Validation

```powershell
python TMP/scripts/run_surrey_free_data_pipeline.py --static-only
python -c "import app; from src.free_data_loader import load_surrey_free_data_summary; print(load_surrey_free_data_summary())"
```

## Streamlit Cloud

Commit small processed CSVs under `data/processed/` (gitignore exceptions). Large rasters stay in `data/raw/` (ignored).

See also: [open_free_data_for_surrey.md](open_free_data_for_surrey.md). Historical layer plan: [TMP/docs/archive/free_data_integration_plan.md](../TMP/docs/archive/free_data_integration_plan.md).
