# Free Data Integration Plan — Surrey PoC

How to wire open/free datasets into the BC Hydro vegetation–weather outage risk demo without duplicating [open_data_fallbacks.md](open_data_fallbacks.md). Companion reference: [open_free_data_for_surrey.md](open_free_data_for_surrey.md).

---

## Goals

- Replace **synthetic** corridor vegetation scores with defensible open-data proxies when Planet sample is unavailable.
- Keep the existing **Public/proxy only** data mode working; optionally enrich **Planet sample enabled** mode with open-data QA columns.
- Preserve provenance labelling (🟡 synthetic vs open vs live).

---

## Layer classification

### Immediate (low processing — days)

| Layer | Source | Action | Output location |
| --- | --- | --- | --- |
| Static land cover | ESA WorldCover 2021 | Download 3×3° tile(s) covering Surrey; zonal stats inside 200 m buffer GeoJSON | `data/processed/surrey_worldcover_corridor_stats.csv` |
| Forest mask backup | NALCMS 2020 | Same zonal workflow | `data/processed/surrey_nalcms_corridor_stats.csv` |
| Corridor geometry | Existing `data/demo/surrey_transmission_buffer_200m.geojson` | Already bundled | Used as zonal AOI |
| Weather | ECCC / MSC GeoMet | **Already integrated** via `src/weather_loader.py` | Live + `demo_weather.csv` fallback |
| Outages | BC Hydro JSON/RSS + GitHub archive | **Already integrated** | Live + demo CSVs |
| Transmission | BC WFS export | **Already integrated** (optional overlay) | `data/processed/bc_transmission_lines_lower_mainland.geojson` |

### Processing required (API account + pipeline — 1–2 weeks)

| Layer | Source | Action | Notes |
| --- | --- | --- | --- |
| Greenness / moisture time series | Sentinel-2 L2A via Copernicus CDSE openEO | Register CDSE account; build monthly NDVI/NDMI aggregates per corridor | Cloud mask with SCL |
| Change (simple) | WorldCover 2020 vs 2021 | Class transition matrix in buffer | No satellite time series initially |
| Change (advanced) | Sentinel-2 NDVI slope | 12-month linear trend | After NDVI pipeline stable |
| LST proxy | MODIS MOD11A1 | NASA Earthdata login; extract h09v04 tile; zonal mean | 1 km resolution |
| Soil moisture proxy | ERA5-Land CDS | `cdsapi` retrieve `volumetric_soil_water_layer_1` at corridor centroid | ~9 km; reanalysis not real-time |
| Soil moisture backup | SMAP 1 km downscaled | Optional; heavier download | NSIDC Earthdata |
| Canopy height (sample) | City of Surrey LiDAR 2022 | Download sample LAS tiles intersecting buffer; DSM−DEM → canopy height raster | Bulk full city via gis@surrey.ca if needed |
| Forest structure (sparse) | BC VRI R1 WFS | Clip polygons to buffer; aggregate HEIGHT / CROWN_CLOSURE | Sparse in urban Surrey |
| Terrain slope | BC CDED 25 m | Derive slope; zonal mean in buffer | Replace synthetic terrain incrementally |

### Deferred / optional

| Layer | Reason |
| --- | --- |
| Copernicus CLMS HRL | Europe-only — not applicable to Surrey |
| Full Surrey LiDAR bulk | Terabyte-scale; use samples first |
| Landsat-only stack | Use as Sentinel-2 fallback if CDSE quota issues |
| City orthophoto ML canopy | Research-grade; out of PoC scope unless quick NDVI-from-ortho experiment |

---

## Recommended implementation order

```
Phase 1 — Static cover (Week 1)
  WorldCover 2021 → corridor CSV
  NALCMS 2020     → validation column
  Wire into planet_loader fallback OR new free_data_loader.py

Phase 2 — Temporal vegetation (Week 2)
  Sentinel-2 NDVI/NDMI monthly → greenness + dryness proxies
  WorldCover 2020 vs 2021       → change_score stub

Phase 3 — Environmental stress (Week 3)
  MODIS LST daily mean           → heat_drought_stress partial
  ERA5-Land soil moisture anomaly → vegetation_dryness partial

Phase 4 — Structure & terrain (as capacity allows)
  VRI WFS clip                   → canopy_exposure backup
  Surrey LiDAR sample tiles      → canopy_height_m validation
  BC CDED slope                  → terrain_access_score
```

Aligns with sidebar mode **Public/proxy only** using `calculate_demo_risk_score`; optional columns can feed a future `calculate_surrey_free_data_risk_score` if Planet remains disabled.

---

## Expected output columns

Target schema for `data/processed/surrey_free_data_corridor_summary.csv` (one row per corridor segment or single AOI summary row for PoC):

| Column | Source layer | Description |
| --- | --- | --- |
| `aoi_id` | Demo config | e.g. `surrey_buffer_200m` |
| `worldcover_tree_pct` | WorldCover 2021 | % Tree class in AOI |
| `worldcover_shrub_grass_pct` | WorldCover 2021 | % Shrub + Grass |
| `worldcover_built_pct` | WorldCover 2021 | % Built-up |
| `worldcover_bare_pct` | WorldCover 2021 | % Bare / sparse vegetation |
| `nalcms_forest_pct` | NALCMS 2020 | % forest classes (backup) |
| `sentinel2_ndvi_mean` | Sentinel-2 | Recent-month mean NDVI (0–1) |
| `sentinel2_ndmi_mean` | Sentinel-2 | Recent-month mean NDMI (moisture) |
| `vegetation_change_score` | WorldCover Δ or S2 trend | Normalized 0–100 |
| `modis_lst_day_mean_c` | MOD11A1 | Daytime LST °C (1 km) |
| `era5_soil_moisture_anomaly` | ERA5-Land | Standardized anomaly vs climatology |
| `vri_mean_crown_closure` | BC VRI | Mean where polygons intersect (nullable) |
| `vri_mean_height_m` | BC VRI | Mean stand height (nullable) |
| `lidar_canopy_height_mean_m` | Surrey LiDAR | From DSM−DEM sample (nullable) |
| `terrain_slope_mean_deg` | BC CDED | Mean slope in buffer |
| `data_source` | Provenance | e.g. `open_free_v1` |
| `as_of_date` | Processing run | ISO date |

### Mapping to demo score fields

| Demo field | Primary open column(s) | Formula hint |
| --- | --- | --- |
| `vegetation_exposure_score` | `worldcover_tree_pct`, `nalcms_forest_pct`, `vri_mean_crown_closure` | Weighted blend → 0–100 |
| `canopy_exposure_score` | `vri_mean_height_m`, `lidar_canopy_height_mean_m`, `worldcover_tree_pct` | Height percentile or capped linear |
| `vegetation_dryness_score` | `sentinel2_ndmi_mean`, `era5_soil_moisture_anomaly` | Invert moisture → dryness |
| `heat_drought_stress_score` | `modis_lst_day_mean_c`, ECCC `weather_severity_score` | Normalize LST + weather |
| `terrain_access_score` | `terrain_slope_mean_deg` | Higher slope → lower access (demo logic) |

---

## Code touchpoints

| File | Change |
| --- | --- |
| `src/planet_loader.py` | Add optional read of `surrey_free_data_corridor_summary.csv` when Planet CSV absent |
| `src/config.py` | Paths for processed free-data CSVs |
| `app.py` | **Done** — Surrey PoC tab “Free/open data fallback” status table |
| `TMP/scripts/` | One-off zonal stats scripts (WorldCover clip, VRI WFS fetch) — create only when running extraction |

---

## Regeneration commands (existing)

```powershell
# Transmission overlay
python TMP/scripts/fetch_bc_transmission_layer.py
python TMP/scripts/export_bc_transmission_sample.py --lower-mainland

# Surrey AOI hectares + GeoJSON
python TMP/scripts/compute_surrey_aoi_options.py
```

---

## Success criteria

- **Public/proxy only** mode shows non-synthetic vegetation proxy sourced from at least WorldCover + one temporal index (Sentinel-2 or MODIS/ERA5).
- Streamlit **Free/open data fallback** table reflects live status for ECCC, BC Hydro, archive, transmission.
- Documentation cross-links stay consistent with Planet purchase path in [demo_plan_with_planet_surrey.md](demo_plan_with_planet_surrey.md).
