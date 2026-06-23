# Causal AI Surrey Dataset — Data Dictionary

Build script: `TMP/scripts/build_causal_ai_surrey_dataset.py`

**Purpose:** Flat tabular exports for Fujitsu Research Causal AI workflow exploration.  
**Not for operational use.** Does not contain validated intervention outcomes or outage predictions.

---

## Recommended files for research team

| File | `dataset_type` | Description |
| --- | --- | --- |
| `data/processed/causal_ai_surrey_aoi_scenarios.csv` | `surrey_aoi_scenarios` | **Recommended primary file.** Surrey 200 m transmission buffer AOI only — scene-level Sentinel-2 QA rows × five intervention scenarios. Mostly populated open/free features (WorldCover, Sentinel-2, ECCC). |
| `data/processed/causal_ai_synthetic_training_dataset.csv` | `synthetic` | **Recommended for workflow testing.** 500–1000 synthetic rows with transparent causal effect columns for discovery / decision-optimization mechanics. |
| `data/processed/causal_ai_surrey_corridor_dataset.csv` | `legacy_corridor` | Legacy combined file (Surrey AOI + bundled demo corridors). Demo corridor rows are sparse on open/free fields — use the Surrey AOI file instead. |

---

## Status values

| Status | Meaning |
| --- | --- |
| `open_free_processed` | Built from open/free pipeline outputs in `data/processed/` |
| `live_public` | Live public API fetch (not persisted in this CSV build) |
| `unofficial_archive_proxy` | Unofficial outage archive municipality summary |
| `demo_synthetic` | Bundled demo or scenario labels for illustration |
| `derived_proxy` | Computed score or proxy from other columns |
| `future_internal_required` | Placeholder for BC Hydro internal replacement |

---

## Column dictionary

| Field | Description | Type | Source | Status | Future BC Hydro replacement | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `record_id` | Unique row identifier | string | derived | derived_proxy | Internal record / work-order ID | Format: `{aoi}__{scene_date}__{tile}__{intervention}` or `{corridor}__{intervention}` |
| `dataset_type` | Dataset package label | string | build script | derived_proxy | N/A | `surrey_aoi_scenarios`, `synthetic`, or `legacy_corridor` |
| `aoi_id` | Area-of-interest identifier | string | pipeline / synthetic | open_free_processed or demo_synthetic | Official AOI / feeder corridor ID | Surrey AOI: `SURREY-TX-BUF-200M` |
| `aoi_name` | Human-readable AOI label | string | pipeline / synthetic | open_free_processed or demo_synthetic | Official corridor naming | |
| `corridor_id` | Corridor segment identifier | string | pipeline / demo / synthetic | mixed | Distribution / transmission segment GIS ID | |
| `corridor_name` | Human-readable corridor label | string | pipeline / demo / synthetic | mixed | Official corridor name | |
| `period_start` | Overall observation window start | string | Sentinel-2 / ECCC stats | open_free_processed | Operational review period start | |
| `period_end` | Overall observation window end | string | Sentinel-2 / ECCC stats | open_free_processed | Operational review period end | |
| `scene_date` | Sentinel-2 sensing date (ISO date) | string | `surrey_sentinel2_scene_qa.csv` | open_free_processed | Acquisition date | One row per processed scene × intervention in Surrey AOI file |
| `tile_id` | Sentinel-2 MGRS tile | string | scene QA | open_free_processed | Tile / product ID | e.g. `T10UDV`, `T10UEV` |
| `weather_severity_score` | Normalized 0–100 weather severity composite | float | Exact `scene_date` via `calculate_weather_severity()` | derived_proxy | Internal storm / forecast severity index | Daily aggregate for `scene_date`; wind 55%, precip 25%, temp stress 10%, code 10% |
| `eccc_temperature_mean_c` | Mean air temperature (°C) | float | Exact `scene_date` (demo weather, MSC GeoMet, or ECCC climate-hourly) | derived_proxy | Field / SCADA weather telemetry | `demo_weather.csv` or live MSC rows for that calendar day; else ECCC climate-hourly pilot station daily mean; null if unavailable |
| `eccc_temperature_max_c` | Max air temperature (°C) | float | Exact `scene_date` (derived) | derived_proxy | Field / SCADA weather telemetry | Daily max from hourly observations |
| `eccc_temperature_min_c` | Min air temperature (°C) | float | Exact `scene_date` (derived) | derived_proxy | Field / SCADA weather telemetry | Daily min from hourly observations |
| `eccc_precip_total_mm` | Total precipitation (mm) in window | float | Exact `scene_date` (derived) | derived_proxy | Radar / gauge network | Daily sum from hourly observations |
| `eccc_wind_gust_max_kmh` | Max wind gust (km/h) | float | Exact `scene_date` (derived) | derived_proxy | Field anemometer / forecast gust | Daily max from hourly wind speed |
| `eccc_weather_stress_score` | Atmospheric stress score 0–100 | float | Exact `scene_date` via `compute_eccc_weather_stress_score()` | derived_proxy | Internal storm-risk model | Recomputed from daily temp/precip/gust; **not LST or soil moisture**; seasonal curve only as documented last resort |
| `worldcover_tree_pct` | Tree cover % in corridor buffer | float | ESA WorldCover 2021 | open_free_processed | BC Hydro vegetation inventory / LiDAR / Planet FCM | AOI-level, repeated per scene row |
| `worldcover_shrub_grass_pct` | Shrub + grass % | float | ESA WorldCover 2021 | open_free_processed | Vegetation inventory | |
| `worldcover_built_pct` | Built-up % | float | ESA WorldCover 2021 | open_free_processed | Land-use GIS | |
| `worldcover_bare_pct` | Bare / sparse vegetation % | float | ESA WorldCover 2021 | open_free_processed | Land-use GIS | |
| `sentinel2_ndvi_mean` | Mean NDVI for scene | float | Sentinel-2 L2A scene QA | open_free_processed | Planet ARPS / internal condition index | Scene-level in Surrey AOI file |
| `sentinel2_ndmi_mean` | Mean NDMI (moisture index) for scene | float | Sentinel-2 L2A scene QA | open_free_processed | Planet SWC / field inspection | Scene-level in Surrey AOI file |
| `sentinel2_ndvi_change` | NDVI change vs earliest processed scene per tile | float | `surrey_sentinel2_scene_qa.csv` | open_free_processed | Time-series vegetation monitoring | Scene-level cumulative change from first tile scene |
| `sentinel2_ndmi_change` | NDMI change vs earliest processed scene per tile | float | `surrey_sentinel2_scene_qa.csv` | open_free_processed | Moisture trend monitoring | Scene-level cumulative change from first tile scene |
| `cloud_filtered_pct` | Cloud-filtered pixel % for scene | float | scene QA | open_free_processed | QA metadata | Scene-level |
| `vegetation_exposure_score` | 0–100 vegetation exposure composite | float | open/free merge or synthetic blend | open_free_processed or demo_synthetic | Certified vegetation risk model | |
| `vegetation_dryness_score` | 0–100 dryness / stress proxy | float | Scene NDMI via `compute_free_data_vegetation_dryness_score()` | derived_proxy | Planet dryness / field moisture | Per-scene from `surrey_sentinel2_scene_qa.csv` NDMI; lower NDMI → higher dryness |
| `vegetation_change_score` | 0–100 change signal from scene NDVI delta | float | `surrey_sentinel2_scene_qa.csv` | derived_proxy | Annual change monitoring | `abs(ndvi_change) / 0.3 × 100` vs earliest tile scene; 0 on baseline scene |
| `canopy_exposure_score` | 0–100 canopy exposure proxy | float | WorldCover tree % + scene NDVI blend | derived_proxy | LiDAR canopy metrics | 60% WorldCover canopy score + 40% scene NDVI component |
| `public_outage_count` | Daily unique outage count (Surrey) | integer | `bchydro_public_outages_history.parquet` | unofficial_archive_proxy | BC Hydro validated outage history | Snapshot on `scene_date` when available; else nearest snapshot with outages active that day |
| `public_customers_affected` | Daily customers affected (Surrey) | integer | Daily archive rows | unofficial_archive_proxy | Official customers-out count | Sum of `num_customers_out` for unique outages on that day |
| `public_outage_history_score` | 0–100 outage history priority proxy | float | Daily density + archive priority blend | derived_proxy | Internal reliability index | `calculate_live_outage_density_score` on daily counts; blended with municipality archive priority when available |
| `tree_related_outage_count_proxy` | Tree-related daily outage proxy | integer | Daily archive `cause` / `is_tree_related` | derived_proxy | Validated cause-coded outages | Count for outages on that `scene_date` |
| `weather_related_outage_count_proxy` | Weather-related daily outage proxy | integer | Daily archive `cause` / `is_weather_related` | derived_proxy | Validated cause-coded outages | Count for outages on that `scene_date` |
| `terrain_access_score` | 0–100 terrain / access difficulty | float | terrain pipeline or synthetic | open_free_processed or demo_synthetic | ROW access / slope GIS | |
| `transmission_buffer_width_m` | Transmission corridor buffer width (m) | integer | AOI geometry config | demo_synthetic | Official ROW width | 200 m for Surrey pilot |
| `area_hectares` | Corridor AOI area (hectares) | float | AOI geometry | open_free_processed or demo_synthetic | Official GIS acreage | Surrey 200 m buffer ≈ 3,580 ha |
| `intervention_type` | Scenario label | string | synthetic scenario | demo_synthetic | Vegetation / work-management records | Five types per base row |
| `intervention_applied` | Binary: intervention planned (1) or not (0) | integer | synthetic scenario | demo_synthetic | Work-order / CMMS status | |
| `intervention_cost_level` | Cost band: `none`, `low`, `medium` | string | synthetic scenario | demo_synthetic | Actual cost estimates | |
| `intervention_lead_time_days` | Lead time before weather window (days) | integer | synthetic scenario | demo_synthetic | Scheduling / crew availability | |
| `intervention_description` | Plain-language scenario description | string | synthetic scenario | demo_synthetic | Standard work instructions | Not observed treatment |
| `risk_score` | 0–100 composite review-priority score | float | `calculate_demo_risk_score()` | derived_proxy | Internal operational risk model | 40% weather + 30% veg + 20% outage + 10% terrain |
| `risk_level` | `Low` / `Medium` / `High` | string | derived from risk_score | derived_proxy | Official priority tier | High ≥70, Medium ≥40 |
| `target_outage_impact_proxy` | Demo target: outage impact proxy 0–100 | float | derived formula | derived_proxy | Validated outage impact metric | `0.40×risk + 0.25×outage_hist + 0.20×weather + 0.15×veg` — **same across interventions** |
| `target_customer_impact_proxy` | Demo target: customer impact proxy | float | derived formula | derived_proxy | Official customers affected | `public_customers_affected × (risk_score / 100)` — **not reduced by intervention** |
| `synthetic_true_effect_pct` | Transparent synthetic causal reduction % | float | synthetic generator | demo_synthetic | Validated treatment effect | **Synthetic dataset only** (null in Surrey AOI file) |
| `observed_outage_impact_proxy` | Pre-intervention synthetic impact proxy | float | synthetic generator | demo_synthetic | Observed outage impact | **Synthetic dataset only** (null in Surrey AOI file) |
| `post_intervention_outage_impact_proxy` | Post-intervention synthetic impact proxy | float | synthetic generator | demo_synthetic | Counterfactual outcome | `observed × (1 - synthetic_true_effect_pct/100)` — **Synthetic dataset only** |
| `data_status` | Semicolon-separated status tags | string | build script | mixed | N/A | Labels public/proxy/synthetic mix per row |
| `data_source_notes` | Free-text provenance and caveat | string | build script | mixed | N/A | Read before any causal inference |

---

## Target proxy formulas

```
target_outage_impact_proxy =
  0.40 × risk_score
+ 0.25 × public_outage_history_score
+ 0.20 × weather_severity_score
+ 0.15 × vegetation_exposure_score

target_customer_impact_proxy =
  public_customers_affected × (risk_score / 100)
```

Interventions are scenario **inputs**, not observed causal outcomes. Target values are **not** reduced by intervention type.

---

## Synthetic causal effect rules (synthetic dataset only)

Transparent moderator rules for workflow testing:

| Intervention | Effect increases when… |
| --- | --- |
| `vegetation_trimming` | Tree cover % and vegetation exposure score are high |
| `crew_pre_staging` | Weather severity score is high |
| `vegetation_patrol` | Cloud-filtered % is high (observation uncertainty) |
| `asset_inspection` | Terrain access score and outage history score are high |
| `no_action` | Effect = 0% |

---

## Build commands

```powershell
# All three datasets (default)
python TMP/scripts/build_causal_ai_surrey_dataset.py --all

# Surrey AOI scenarios only
python TMP/scripts/build_causal_ai_surrey_dataset.py --surrey-only

# Synthetic training dataset only
python TMP/scripts/build_causal_ai_surrey_dataset.py --synthetic --synthetic-rows 1000 --seed 42
```

Prerequisites: `surrey_free_data_corridor_summary.csv`, `surrey_sentinel2_scene_qa.csv`, `surrey_sentinel2_corridor_stats.csv`, `surrey_eccc_weather_stress_stats.csv`. Optional: `municipality_summary.csv` or `data/demo/demo_municipality_outage_summary.csv`. Daily weather uses MSC GeoMet / ECCC climate-hourly for each `scene_date`. Daily outages require `bchydro_public_outages_history.parquet` in `data/processed/`, `EXTRACTOR_OUTPUT_DIR`, or the default `bchydro-outage-history-extractor` path.

---

## Row structure

### Surrey AOI scenarios (`causal_ai_surrey_aoi_scenarios.csv`)

- One row = one **processed Sentinel-2 scene date × tile × intervention scenario**.
- Expected ~135 rows with 27 processed scenes × 5 interventions (28 QA rows minus 1 skipped).
- AOI-level WorldCover and terrain geometry are static across scene rows.
- Per-scene variation: NDVI, NDMI, cloud-filtered %, vegetation dryness/change, canopy exposure (NDVI blend), weather (exact `scene_date` daily match), and outage proxies (exact `scene_date` daily archive match).
- Static per AOI: `terrain_access_score`, `transmission_buffer_width_m`, `area_hectares`.

### Synthetic training (`causal_ai_synthetic_training_dataset.csv`)

- Default 1000 rows, seed 42.
- One row = one **synthetic corridor × date × intervention**.
- Includes `synthetic_true_effect_pct`, `observed_outage_impact_proxy`, `post_intervention_outage_impact_proxy`.
