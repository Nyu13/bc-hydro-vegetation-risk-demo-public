# Causal AI Exploration Data Package

**From:** BC Hydro vegetation–weather outage risk proof-of-concept (Fujitsu collaboration)  
**Date:** June 11, 2026  
**Geography:** Surrey, BC — 200 m transmission-line buffer (`SURREY-TX-BUF-200M`)

---

## Attached files

| File | Rows | Recommendation |
| --- | ---: | --- |
| **`causal_ai_surrey_aoi_scenarios.csv`** | 135 | **Primary — start here.** Real open/free features at Sentinel-2 scene granularity with five intervention scenario labels per scene. |
| **`causal_ai_synthetic_training_dataset.csv`** | 1,000 | **Optional.** Synthetic corridors with transparent pre/post causal-effect columns for workflow and optimization testing. |
| **`causal_ai_surrey_discovery_raw.csv`** | 27 | **Recommended for causal graph discovery.** One row per Sentinel-2 scene+tile; observed weather, vegetation, and outage proxy inputs only — no derived composite scores or proxy targets. |
| **`causal_ai_surrey_discovery_with_targets.csv`** | 27 | **For supervised / target-aware discovery.** Same inputs as the raw file plus three derived proxy target columns for exploratory outcome modeling. |

The primary file has 135 scenario rows (27 scenes × 5 interventions). Both discovery files have **27 rows** — one per unique (`scene_date`, `tile_id`) pair, using baseline (`no_action`) scene features. The raw discovery file has **15 columns** (13 numeric inputs plus `scene_date` and `tile_id`). The with-targets file adds **3 derived proxy targets** (18 columns total). The synthetic file uses the full 52-column schema. A legacy combined export (`causal_ai_surrey_corridor_dataset.csv`) is **not** included in this package; it mixes sparse demo corridors and is superseded by the primary file above.

---

## Purpose and scope

This package supports **exploratory evaluation** of how Fujitsu Causal AI might ingest tabular vegetation–weather–outage proxy data, run causal discovery, and test decision-optimization workflows. The data illustrate schema design and feature relationships from a public-data pilot — they are **not** validated causal effect estimates, **not** official BC Hydro records, **not** outage predictions, and **not** suitable for operational vegetation, crew, or reliability decisions.

---

## Dataset structure

**Primary file (`causal_ai_surrey_aoi_scenarios.csv`):**

- **135 rows** = **27 processed Sentinel-2 scenes** (unique `scene_date` + `tile_id` pairs) × **5 intervention scenarios**
- **15 unique sensing dates** across two MGRS tiles (`T10UDV`, `T10UEV`), January–May 2026
- **One AOI only:** Surrey 200 m transmission buffer (~3,580 ha)
- **Record ID format:** `{aoi}__{scene_date}__{tile}__{intervention}`

**Intervention scenarios (repeated for every scene row):**

| `intervention_type` | Applied | Cost | Lead time (days) |
| --- | --- | --- | --- |
| `no_action` | 0 | none | 0 |
| `vegetation_patrol` | 1 | low | 3 |
| `vegetation_trimming` | 1 | medium | 14 |
| `crew_pre_staging` | 1 | medium | 1 |
| `asset_inspection` | 1 | low | 7 |

**Synthetic file:** one row per synthetic corridor × date × intervention (seed 42). Adds `synthetic_true_effect_pct`, `observed_outage_impact_proxy`, and `post_intervention_outage_impact_proxy` with documented moderator rules for tool validation.

---

## Key column groups

| Group | Representative columns | Role |
| --- | --- | --- |
| **Identifiers & time** | `record_id`, `aoi_id`, `scene_date`, `tile_id`, `period_start`, `period_end` | Row keys and observation window |
| **Weather** | `weather_severity_score`, `eccc_temperature_mean_c`, `eccc_precip_total_mm`, `eccc_wind_gust_max_kmh`, `eccc_weather_stress_score` | Daily atmospheric stress matched to `scene_date` |
| **Vegetation** | `worldcover_tree_pct`, `sentinel2_ndvi_mean`, `sentinel2_ndmi_mean`, `vegetation_exposure_score`, `vegetation_dryness_score`, `vegetation_change_score`, `canopy_exposure_score` | Land cover (static AOI) + per-scene Sentinel-2 indices |
| **Outages** | `public_outage_count`, `public_customers_affected`, `public_outage_history_score`, `tree_related_outage_count_proxy`, `weather_related_outage_count_proxy` | Unofficial daily Surrey archive proxies |
| **Intervention (scenario input)** | `intervention_type`, `intervention_applied`, `intervention_cost_level`, `intervention_lead_time_days`, `intervention_description` | Synthetic scenario labels — not work-order records |
| **Targets (exploration only)** | `risk_score`, `risk_level`, `target_outage_impact_proxy`, `target_customer_impact_proxy` | Derived demo formulas for workflow testing |
| **Provenance** | `data_status`, `data_source_notes` | Per-row status tags and caveats — read before inference |

Full column definitions are available on request. Check `data_status` and `data_source_notes` on each row before analysis.

---

## Data provenance

| Source layer | Examples | Status |
| --- | --- | --- |
| ESA WorldCover 2021, Sentinel-2 L2A scene stats, terrain AOI geometry | `worldcover_*`, `sentinel2_*`, `terrain_access_score` | `open_free_processed` |
| Live BC Hydro outage JSON / ECCC GeoMet (runtime only) | Not persisted in these CSVs | `live_public` |
| Unofficial outage snapshot archive (Surrey daily counts) | `public_outage_count`, `public_customers_affected` | `unofficial_archive_proxy` |
| Intervention scenario labels | `intervention_type`, cost, lead time | `demo_synthetic` |
| Composite scores and target proxies | `risk_score`, `vegetation_*_score`, `target_*_proxy` | `derived_proxy` |
| Synthetic causal-effect columns (synthetic file only) | `synthetic_true_effect_pct`, `post_intervention_outage_impact_proxy` | `demo_synthetic` |

---

## What is real vs synthetic

| Per row | Real / observed proxy | Synthetic or derived |
| --- | --- | --- |
| **Scene features** | Sentinel-2 NDVI, NDMI, cloud %, and change vs earliest tile scene | Vegetation and canopy composite scores |
| **Weather on `scene_date`** | Daily ECCC/MSC atmospheric aggregates when available | `weather_severity_score`, `eccc_weather_stress_score` |
| **AOI geometry** | WorldCover class %, area, buffer width (static, repeated per scene) | — |
| **Outages** | Daily Surrey counts from unofficial archive on or nearest to `scene_date` | Cause-split proxies, `public_outage_history_score` |
| **Interventions** | — | All five scenario types are labels only; no observed treatments |
| **Targets** | — | `target_outage_impact_proxy` and `target_customer_impact_proxy` use the **same formula for all interventions** in the primary file |

---

## Known limitations

1. **Interventions are scenario labels**, not records of work performed. Target columns do **not** change across intervention types in the primary file.
2. **Outage fields** come from an **unofficial** public snapshot archive — not certified BC Hydro outage history or validated cause attribution.
3. **Dates without an exact archive snapshot** (e.g. May 31, 2026) may use the **nearest snapshot** where outages were active on that calendar day (`date_off ≤ scene_date ≤ date_on`).
4. **ECCC weather is atmospheric** (air temperature, wind gust, precipitation) — **not** land surface temperature (LST) or soil water content (SWC).
5. **Synthetic effect columns** in the optional file follow transparent generator rules for tool testing — they are not ground-truth causal estimates.

---

## Suggested first steps (Fujitsu Causal AI)

1. **Ingest** `causal_ai_surrey_discovery_raw.csv` (recommended for causal graph discovery) or `causal_ai_surrey_discovery_with_targets.csv` if proxy targets are needed; use the full `causal_ai_surrey_aoi_scenarios.csv` only when intervention labels are required.
2. **Run causal discovery** on weather, vegetation, and outage proxy variables in the raw file (27 scene+tile rows). Use the with-targets file when the tool needs explicit outcome columns; treat targets as derived proxies, not observed outcomes.
3. **Test decision optimization** on `causal_ai_synthetic_training_dataset.csv` using `synthetic_true_effect_pct` and pre/post impact columns to validate optimization mechanics.
4. **Review** preprocessing assumptions below and report any columns that should be renamed, transformed, or split (wide vs long, cost constraints, uncertainty outputs).
5. **Share feedback** on minimum additional BC Hydro internal data needed for a production-grade pilot.

### Preprocessing applied to discovery files

Both discovery files apply the exploratory preprocessing steps discussed with Fujitsu Research:

- **Deduplicated:** one row per (`scene_date`, `tile_id`); prefers `no_action` baseline when selecting from the five intervention scenario duplicates in the primary file.
- **Removed (metadata):** record IDs, AOI/corridor metadata, period dates, free-text notes, intervention scenario columns, `risk_level`, and synthetic-only columns with no values in the primary file.
- **Removed (derived/formula — circular graph risk):** `risk_score`, `target_outage_impact_proxy`, `target_customer_impact_proxy`, `eccc_weather_stress_score`, `weather_severity_score`, `vegetation_dryness_score`, `vegetation_change_score`, `canopy_exposure_score`, `public_outage_history_score`. These are composite or formula-based scores; including them alongside their input components can create spurious edges in causal discovery.
- **Removed (constant across rows — no discovery value):** `worldcover_tree_pct`, `worldcover_shrub_grass_pct`, `worldcover_built_pct`, `worldcover_bare_pct`, `vegetation_exposure_score`, `weather_related_outage_count_proxy`, `terrain_access_score`. These do not vary across the 27 scene+tile rows in this export.
- **Imputation:** mean imputation for any remaining numeric nulls (none expected in the current export).

#### `causal_ai_surrey_discovery_raw.csv` — causal graph inputs (15 columns)

Use this file when the goal is **structure learning** without outcome columns that reuse the same input features.

| Column | Role |
| --- | --- |
| `scene_date`, `tile_id` | Row keys (one row per Sentinel-2 scene+tile) |
| `eccc_temperature_mean_c`, `eccc_temperature_max_c`, `eccc_temperature_min_c` | Daily ECCC temperature aggregates on `scene_date` |
| `eccc_precip_total_mm`, `eccc_wind_gust_max_kmh` | Daily precipitation and wind gust |
| `sentinel2_ndvi_mean`, `sentinel2_ndmi_mean`, `sentinel2_ndvi_change`, `sentinel2_ndmi_change` | Per-scene vegetation indices and change vs earliest tile scene |
| `cloud_filtered_pct` | Scene cloud-filtered pixel percentage |
| `public_outage_count`, `public_customers_affected` | Unofficial Surrey daily outage archive counts |
| `tree_related_outage_count_proxy` | Cause-split outage proxy (tree-related share) |

#### `causal_ai_surrey_discovery_with_targets.csv` — raw inputs + proxy targets (18 columns)

Same columns as the raw file, plus:

| Column | Role |
| --- | --- |
| `risk_score` | **Derived proxy** — composite demo risk score from weather/vegetation/outage inputs |
| `target_outage_impact_proxy` | **Derived proxy target** — formula-based outage impact estimate; **not** an observed outage outcome |
| `target_customer_impact_proxy` | **Derived proxy target** — formula-based customer impact estimate; **not** an observed customer count |

**Important:** The three target columns are **derived from the same input features**, not independently observed outcomes. Use them only for exploratory supervised discovery or workflow testing — not as ground-truth labels for causal effect estimation.

**Example research questions:**

- Which weather and vegetation variables show the strongest associations with outage proxy targets?
- How should interventions be represented for action optimization (categorical, binary flags, cost/lead-time constraints)?
- Can the tool produce a causal graph, recommended actions, and human-readable rationale from this schema?

---

## Questions and contact

**Primary contact:** *[Name, email — to be completed before send]*  
**Organization:** BC Hydro / Fujitsu vegetation–weather PoC team  
**Subject line suggestion:** *Surrey Causal AI exploration data package — June 2026*

Please direct schema, ingestion, and tooling questions to the contact above. A detailed column dictionary can be provided separately if needed.

---
