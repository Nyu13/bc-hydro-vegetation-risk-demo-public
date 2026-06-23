# Data Overview (Short)

**Audience:** Managers and research partners  
**Pilot geography:** Surrey, BC (Lower Mainland)  
**As of:** June 2026 — unofficial outage archive through **2026-06-11**; Surrey Causal AI AOI file has **135 rows** (27 processed Sentinel-2 scenes × 5 intervention scenarios).

This is a **proof-of-process** demo using **public and proxy data only**. It does not predict outages and is not operational decision support.

**More detail:** [current_demo_overview.md](current_demo_overview.md) (app tabs, scoring, runbook) · [causal_ai_research_team_dataset_brief.md](causal_ai_research_team_dataset_brief.md) (Fujitsu Causal AI package) · [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md) (full column list — not duplicated here).

---

## 1. What data the demo uses

| Category | When loaded | Examples | Role |
| --- | --- | --- | --- |
| **Live public** | Runtime fetch (Streamlit **Refresh live data**) | BC Hydro outage JSON/RSS; ECCC/MSC GeoMet weather (~48 h, pilot bbox) | Current storm summary, map polygons, live weather severity |
| **Open/free processed** | Bundled `data/processed/*.csv` (offline pipelines) | WorldCover 2021, Sentinel-2 L2A stats/QA, ECCC weather stress, merged corridor summary | Vegetation and atmospheric stress proxies for Surrey 200 m transmission buffer |
| **Unofficial archive proxy** | Bundled summaries + daily parquet | `region_summary.csv`, `municipality_summary.csv`, `bchydro_public_outages_history.parquet` | Historical unique-outage rankings (Area selection tab); daily outage counts in Causal AI exports |
| **Demo / synthetic** | Always bundled `data/demo/` | `demo_corridors.csv`, backtesting CSVs, Planet placeholder, intervention scenario labels | Illustrative segments, workflow testing, not distribution GIS or observed treatments |

**Offline mode** (`DEMO_OFFLINE_MODE=1`): skips live HTTP; uses synthetic demo CSVs only.

---

## 2. Key files in `data/processed/`

| File | One-line purpose |
| --- | --- |
| `surrey_free_data_corridor_summary.csv` | Merged open/free scores for Surrey 200 m transmission buffer AOI |
| `surrey_worldcover_corridor_stats.csv` | ESA WorldCover class percentages per AOI |
| `surrey_sentinel2_corridor_stats.csv` | Corridor-level NDVI/NDMI means and change (Jan–May 2026 stack) |
| `surrey_sentinel2_scene_qa.csv` | Per-scene QA: tile, sensing date, status (28 rows: 27 processed, 1 skipped) |
| `surrey_eccc_weather_stress_stats.csv` | Offline ECCC atmospheric stress components for corridor AOI |
| `surrey_nalcms_corridor_stats.csv` | NALCMS land-cover stats (optional pipeline layer) |
| `surrey_vri_corridor_stats.csv` | BC Vegetation Resources Inventory stats (optional) |
| `surrey_terrain_corridor_stats.csv` | Slope/terrain access stats (optional) |
| `surrey_environmental_stress_corridor_stats.csv` | Environmental stress merge inputs (optional) |
| `bc_transmission_lines_lower_mainland.geojson` | Clipped public HV transmission lines for map overlay |
| `region_summary.csv` | Province region unique-outage archive metrics (through 2026-06-11) |
| `municipality_summary.csv` | Municipality unique-outage archive metrics (through 2026-06-11) |
| `bchydro_public_outages_history.parquet` | Daily Surrey outage rows from unofficial snapshot archive (Causal AI build input) |
| `causal_ai_surrey_aoi_scenarios.csv` | **Recommended** Causal AI export — scene × intervention scenarios |
| `causal_ai_synthetic_training_dataset.csv` | Synthetic expanded dataset for causal workflow testing (default 1000 rows) |
| `causal_ai_surrey_corridor_dataset.csv` | Legacy combined export (Surrey AOI + demo corridors) |

Large rasters and `.SAFE` products live under `data/raw/` (gitignored). Placeholders when pipelines are not run: `data/demo/surrey_free_data_corridor_summary_placeholder.csv`.

---

## 3. Causal AI package (Fujitsu Research)

| File | Rows | Use |
| --- | --- | --- |
| **`causal_ai_surrey_aoi_scenarios.csv`** | **135** | **Start here.** Surrey 200 m AOI only; one row per processed Sentinel-2 scene × five intervention scenarios (`no_action`, `vegetation_patrol`, `vegetation_trimming`, `crew_pre_staging`, `asset_inspection`). Mostly real open/free features. |
| `causal_ai_synthetic_training_dataset.csv` | 500–1000 (default 1000) | Expanded synthetic data with transparent pre/post effect columns for discovery and decision-optimization mechanics. |
| `causal_ai_surrey_corridor_dataset.csv` | ~35 (legacy) | Older combined file; demo corridor rows are sparse — prefer the AOI scenarios file. |

Build: `python TMP/scripts/build_causal_ai_surrey_dataset.py --all`  
Field definitions: [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md).

---

## 4. Provenance labels

Used in CSV `data_status` / UI badges. Semantics:

| Label | Meaning |
| --- | --- |
| `live_public` | Fetched from public APIs at runtime (not persisted in offline CSV builds) |
| `open_free_processed` | Built from open/free pipeline outputs in `data/processed/` |
| `unofficial_archive_proxy` | Unofficial BC Hydro outage snapshot archive — not certified history |
| `demo_synthetic` | Bundled demo data or scenario labels for illustration |
| `derived_proxy` | Computed score or proxy from other columns (e.g. `risk_score`, weather severity) |

Intervention types and target proxies in the AOI file are **scenario labels** (`demo_synthetic` / `derived_proxy`), not observed treatment outcomes.

---

## 5. What is real per `scene_date` (Causal AOI file)

Each base row corresponds to one **processed** Sentinel-2 scene (`scene_date`, `tile_id` from `surrey_sentinel2_scene_qa.csv`).

| Feature group | Tied to `scene_date`? | Source |
| --- | --- | --- |
| **Sentinel-2** (NDVI, NDMI, change, cloud %) | **Yes** | Real scene-level stats from L2A products |
| **ECCC weather** (temp, precip, gust, stress) | **When available** | Daily aggregate for that calendar day (demo weather, MSC GeoMet, or ECCC climate-hourly pilot station); null if no daily source |
| **WorldCover / terrain** | Static AOI | Repeated on every scene row |
| **Outage counts** | **By `scene_date`** | Daily Surrey rows from `bchydro_public_outages_history.parquet` — snapshot on that date when available, else nearest snapshot with outages active that day (`date_off ≤ scene_date ≤ date_on`) |
| **Interventions & targets** | No | Synthetic scenario dimensions; targets unchanged across intervention types in this file |

ECCC weather stress is an **atmospheric proxy** (air temperature, wind, precipitation) — **not** land surface temperature or soil moisture.

---

## 6. How to refresh data

| Goal | Command / action |
| --- | --- |
| **Live outages & weather** | Streamlit sidebar **Refresh live data** (or restart app) |
| **Historical archive summaries** | Run external [bchydro-outage-history-extractor](https://github.com/outages/bchydro-outages), then `python TMP/scripts/refresh_area_selection_data.py` — copies `region_summary.csv` / `municipality_summary.csv` into `data/processed/` and demo bundle |
| **Open/free vegetation & weather layers** | `python TMP/scripts/run_surrey_free_data_pipeline.py` (use `--static-only` for quick static layers; full run includes Sentinel-2 merge when rasters exist). Runbook: [free_data_pipeline_runbook.md](free_data_pipeline_runbook.md) |
| **Sentinel-2 only** | Download L2A to `data/raw/surrey/Sentinel-2 L2A/`, then `python TMP/scripts/build_surrey_sentinel2_indices.py ...`, re-run merge/pipeline |
| **Causal AI CSVs** | `python TMP/scripts/build_causal_ai_surrey_dataset.py --all` (after processed inputs and parquet archive are current) |

Set `EXTRACTOR_OUTPUT_DIR` to point the app at an external extractor `data/processed/` path instead of copying files.

---

## 7. What is NOT included

- BC Hydro **internal** outage history, cause attribution, feeder/circuit topology, vegetation programs, asset condition, or work-management records
- **Planet** commercial products (Basemaps, ARPS, SWC, etc.) — placeholder CSV and quote narrative only; see [planet_surrey_data_request.md](planet_surrey_data_request.md)
- **Validated causal outcomes** or intervention effect estimates — synthetic columns are for workflow testing only
- **Outage prediction** or operational prioritization certified by BC Hydro

---

## Quick disclaimer

Public/proxy datasets illustrate dashboard and research **workflow fit**. Do not use for operational decisions. For internal data needs in a formal PoC, see [bc_hydro_internal_data_needed.md](bc_hydro_internal_data_needed.md).
