# Causal AI Datasets — Quick Overview

**Audience:** Internal team, project managers  
**Repository:** `bc_hydro_vegetation_risk_demo`  
**AOI:** Surrey transmission corridor, 200 m buffer (`SURREY-TX-BUF-200M`)

**External handoff (email attachment):** [causal_ai_data_package_for_research.md](causal_ai_data_package_for_research.md) — standalone document to attach with the CSV zip for Fujitsu Research. No repository references; suitable for PDF export.

---

## 1. Purpose

These CSV exports package open/free vegetation, weather, and outage **proxies** with **synthetic intervention scenario labels** so Fujitsu Causal AI can test workflow fit and schema design.

**This is exploration data only.**

- Not validated causal effect estimates
- Not observed treatment outcomes
- Not an outage prediction or operational decision tool
- Not official BC Hydro data

Use them to evaluate ingestion, causal discovery, and decision-optimization mechanics — not to draw production conclusions.

**Further reading:** [causal_ai_data_package_for_research.md](causal_ai_data_package_for_research.md) (external attachment) · [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md) (column definitions) · [causal_ai_research_team_dataset_brief.md](causal_ai_research_team_dataset_brief.md) (research questions and feedback requests)

---

## 2. Recommended files

| File | Rows | Role |
| --- | --- | --- |
| **`data/processed/causal_ai_surrey_aoi_scenarios.csv`** | **135** | **Primary.** Real Surrey AOI features at Sentinel-2 scene granularity × five intervention scenarios. |
| **`data/processed/causal_ai_synthetic_training_dataset.csv`** | **1000** | **Workflow testing.** Synthetic corridors with transparent causal-effect columns for discovery / optimization drills. |
| `data/processed/causal_ai_surrey_corridor_dataset.csv` | 35 | **Legacy / optional.** Combined Surrey + demo corridors; demo rows are sparse on open/free fields. Prefer the AOI file. |

---

## 3. How to build

From the repository root:

```powershell
python TMP/scripts/build_causal_ai_surrey_dataset.py --all
```

This rebuilds all three CSVs. Prerequisites: processed Surrey pipeline outputs (`surrey_free_data_corridor_summary.csv`, `surrey_sentinel2_scene_qa.csv`, `surrey_sentinel2_corridor_stats.csv`, `surrey_eccc_weather_stress_stats.csv`). Optional: `bchydro_public_outages_history.parquet` for daily outage columns.

Other modes: `--surrey-only`, `--synthetic --synthetic-rows 1000 --seed 42`.

---

## 4. Row design

**Surrey AOI (primary):** one row = one **processed Sentinel-2 scene** (`scene_date` + `tile_id` from `surrey_sentinel2_scene_qa.csv`) × one of **five intervention scenarios**:

| `intervention_type` | Applied | Cost | Lead time (days) |
| --- | --- | --- | --- |
| `no_action` | 0 | none | 0 |
| `vegetation_patrol` | 1 | low | 3 |
| `vegetation_trimming` | 1 | medium | 14 |
| `crew_pre_staging` | 1 | medium | 1 |
| `asset_inspection` | 1 | low | 7 |

~27 processed scenes × 5 interventions ≈ **135 rows**. `record_id` format: `{aoi}__{scene_date}__{tile}__{intervention}`.

**Synthetic:** one row = synthetic corridor × date × intervention (default 1000 rows, seed 42). Adds `synthetic_true_effect_pct`, `observed_outage_impact_proxy`, `post_intervention_outage_impact_proxy`.

---

## 5. What is real vs derived

| Layer | Examples | Status |
| --- | --- | --- |
| **Open/free inputs** | ESA WorldCover land-cover %, Sentinel-2 NDVI/NDMI per scene, cloud-filtered % | Mostly populated in Surrey AOI file |
| **Atmospheric weather (daily)** | `eccc_*` columns, `weather_severity_score` — matched to exact `scene_date` | Derived daily aggregates from demo weather, MSC GeoMet, or ECCC climate-hourly |
| **Outage archive (daily)** | `public_outage_count`, `public_customers_affected`, cause proxies | Unofficial snapshot archive; not certified BC Hydro history |
| **Composite scores** | `vegetation_*_score`, `canopy_exposure_score`, `risk_score`, `public_outage_history_score` | Derived proxies from inputs above |
| **Interventions** | `intervention_type`, cost, lead time, description | **Synthetic scenario labels** — not work-order records |
| **Targets** | `target_outage_impact_proxy`, `target_customer_impact_proxy` | **Derived demo formulas** — identical across interventions in the AOI file |

Static per AOI (repeated on every scene row): WorldCover %, `terrain_access_score`, `transmission_buffer_width_m` (200 m), `area_hectares` (~3,580 ha).

Per-scene variation: Sentinel indices, vegetation dryness/change, weather on `scene_date`, daily outage counts.

---

## 6. Key columns for causal discovery

| Group | Columns |
| --- | --- |
| **Weather** | `weather_severity_score`, `eccc_temperature_mean_c`, `eccc_precip_total_mm`, `eccc_wind_gust_max_kmh`, `eccc_weather_stress_score` |
| **Vegetation** | `worldcover_tree_pct`, `sentinel2_ndvi_mean`, `sentinel2_ndmi_mean`, `vegetation_exposure_score`, `vegetation_dryness_score`, `vegetation_change_score`, `canopy_exposure_score` |
| **Outages** | `public_outage_count`, `public_customers_affected`, `public_outage_history_score`, `tree_related_outage_count_proxy`, `weather_related_outage_count_proxy` |
| **Intervention (scenario input)** | `intervention_type`, `intervention_applied`, `intervention_cost_level`, `intervention_lead_time_days` |
| **Targets (exploration only)** | `risk_score`, `risk_level`, `target_outage_impact_proxy`, `target_customer_impact_proxy` |
| **Synthetic targets (synthetic file only)** | `synthetic_true_effect_pct`, `observed_outage_impact_proxy`, `post_intervention_outage_impact_proxy` |

Check `data_status` and `data_source_notes` on each row for provenance tags (`open_free_processed`, `unofficial_archive_proxy`, `derived_proxy`, `demo_synthetic`).

---

## 7. Caveats (read before analysis)

1. **Interventions are scenario labels, not observed treatments.** No causal effect is encoded in the Surrey AOI targets; `target_outage_impact_proxy` uses the same formula for all five scenarios.
2. **Outage data is an unofficial archive proxy** — daily Surrey municipality counts from snapshot history, not validated cause attribution.
3. **May 31 and other dates without an exact snapshot** may use the **nearest archive snapshot** where outages were active on that calendar day (`date_off ≤ scene_date ≤ date_on`).
4. **ECCC weather is atmospheric** (air temperature, wind gust, precipitation) — **not** land surface temperature (LST) or soil water content (SWC).
5. **Synthetic effect columns** in the 1000-row file follow documented moderator rules for tool testing — they are transparently generated, not ground truth.
6. Do not use these datasets for operational vegetation, outage, or crew decisions.

---

## 8. Suggested starting point

| Goal | Start with |
| --- | --- |
| Test ingestion and discovery on mostly real open/free features | `causal_ai_surrey_aoi_scenarios.csv` |
| Test decision optimization with known synthetic effects | `causal_ai_synthetic_training_dataset.csv` |
| Column-level detail and build prerequisites | [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md) |
| Research questions and feedback checklist | [causal_ai_research_team_dataset_brief.md](causal_ai_research_team_dataset_brief.md) |
