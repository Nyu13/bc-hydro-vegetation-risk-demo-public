# Surrey Vegetation-Weather Causal AI Exploration Dataset

**Audience:** Fujitsu Research Causal AI team  
**Repository:** `bc_hydro_vegetation_risk_demo`  
**Dictionary:** [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md)

---

## A. Purpose

We are providing public/proxy datasets from the BC Hydro vegetation-weather outage risk demo to explore how Fujitsu Causal AI could support causal discovery and causal decision optimization.

The datasets package open/free vegetation and weather features, unofficial outage archive proxies, and synthetic intervention scenario labels into flat CSVs suitable for tabular causal AI ingestion. They are intended to validate **workflow fit** and **schema design** — not to produce validated causal effect estimates.

---

## B. What changed from the first dataset

The first generated file (`causal_ai_surrey_corridor_dataset.csv`) was **too sparse** for causal AI experimentation:

- Only 35 rows mixing Surrey AOI with bundled demo corridors.
- Demo corridor rows lacked WorldCover, Sentinel-2, and ECCC open/free fields.
- Many missing values across key feature columns.

We now provide **two recommended datasets**:

| File | Rows (typical) | Use case |
| --- | --- | --- |
| **`causal_ai_surrey_aoi_scenarios.csv`** | ~135 (27 scenes × 5 interventions) | Clean Surrey 200 m AOI with mostly real open/free features at scene-level granularity |
| **`causal_ai_synthetic_training_dataset.csv`** | 500–1000 (default 1000) | Expanded synthetic data for testing causal discovery and decision-optimization mechanics |

The original `causal_ai_surrey_corridor_dataset.csv` is retained as a legacy combined export.

---

## C. Current demo question

**Where should we prioritize vegetation-weather review?**

The existing Streamlit proof-of-process demo ranks corridor segments using a transparent composite score (weather severity, vegetation exposure, public outage history proxy, terrain/access). The Surrey AOI dataset exports those features in a research-friendly tabular form with time-varying Sentinel-2 scene rows.

---

## D. Causal AI extension question

**Which intervention is likely to reduce outage impact most, under cost, timing, and operational constraints?**

We add synthetic intervention scenario rows (`no_action`, `vegetation_patrol`, `vegetation_trimming`, `crew_pre_staging`, `asset_inspection`) with cost and lead-time attributes.

- In the **Surrey AOI file**, target proxy columns are provided for exploration using documented formulas — they are **not** observed treatment outcomes and are **not** reduced by intervention type.
- In the **synthetic file**, we additionally provide `synthetic_true_effect_pct`, `observed_outage_impact_proxy`, and `post_intervention_outage_impact_proxy` with transparent moderator rules for workflow testing.

---

## E. Dataset caveat

This is **not** official BC Hydro data and does **not** contain validated intervention outcomes. It is for workflow exploration only.

- Outage archive fields come from an **unofficial** snapshot archive — not certified BC Hydro outage history or cause attribution.
- Vegetation and weather layers are **public/open** proxies (WorldCover, Sentinel-2, ECCC/MSC GeoMet).
- ECCC weather stress is an **atmospheric proxy** (air temperature, wind gust, precipitation) — **not** land surface temperature (LST) or soil water content (SWC).
- Demo corridor segments in the legacy file are **synthetic** illustrations, not distribution GIS.
- Intervention variables are **scenario labels** for research — not records of work performed.
- Target proxies are **derived** for demo exploration — **not** outage prediction or validated causal effects.
- Synthetic causal effect columns are **transparently generated** for tool testing — not ground truth.

Do not use these datasets for operational decisions.

---

## F. Candidate causal variables

| Variable group | Columns (examples) |
| --- | --- |
| Weather severity | `weather_severity_score`, `eccc_wind_gust_max_kmh`, `eccc_precip_total_mm`, `eccc_weather_stress_score` |
| Wind gust | `eccc_wind_gust_max_kmh` |
| Precipitation | `eccc_precip_total_mm` |
| Tree cover | `worldcover_tree_pct`, `canopy_exposure_score` |
| Vegetation dryness | `vegetation_dryness_score`, `sentinel2_ndmi_mean` |
| Vegetation change | `vegetation_change_score`, `sentinel2_ndvi_change`, `sentinel2_ndmi_change` |
| Scene metadata | `scene_date`, `tile_id`, `cloud_filtered_pct` |
| Outage history proxy | `public_outage_history_score`, `public_outage_count`, `tree_related_outage_count_proxy`, `weather_related_outage_count_proxy` |
| Terrain / access | `terrain_access_score`, `area_hectares`, `transmission_buffer_width_m` |
| Intervention type | `intervention_type`, `intervention_applied`, `intervention_cost_level`, `intervention_lead_time_days` |

---

## G. Candidate target variables

| Target | Column | Notes |
| --- | --- | --- |
| Composite review priority | `risk_score`, `risk_level` | Same transparent PoC formula as the Streamlit demo |
| Outage impact proxy | `target_outage_impact_proxy` | `0.40×risk + 0.25×outage_hist + 0.20×weather + 0.15×veg` — unchanged across interventions |
| Customer impact proxy | `target_customer_impact_proxy` | `public_customers_affected × (risk_score / 100)` |
| Synthetic pre/post (synthetic file only) | `observed_outage_impact_proxy`, `post_intervention_outage_impact_proxy`, `synthetic_true_effect_pct` | Transparent synthetic causal pattern for workflow testing |

---

## H. Requested feedback from research team

1. Is this dataset structure suitable for Fujitsu Causal AI ingestion?
2. **Which dataset is more appropriate for initial testing** — the Surrey AOI scenarios file or the synthetic training file?
3. What columns should be renamed or transformed?
4. How should interventions be represented (wide vs long, binary flags, categorical, cost constraints)?
5. Can the tool run **causal discovery** on the Surrey AOI proxy dataset?
6. Can the tool run **causal decision-making / action optimization** with the synthetic intervention scenarios and effect columns?
7. What additional schema changes are needed?
8. What minimum **real BC Hydro internal data** would be required for validated results?
9. What input/output schema should we use if we connect through **Python SDK** or **OpenAPI**?

---

## I. Desired output from research team

- Causal graph or variable relationship summary
- Recommended actions / decision optimization example
- Explanation text (human-readable rationale)
- Confidence / uncertainty if supported by the tool
- Required data gaps list for a production-grade pilot

---

## Build and refresh

```powershell
# All datasets (default)
python TMP/scripts/build_causal_ai_surrey_dataset.py --all

# Surrey AOI only
python TMP/scripts/build_causal_ai_surrey_dataset.py --surrey-only

# Synthetic only
python TMP/scripts/build_causal_ai_surrey_dataset.py --synthetic --synthetic-rows 1000 --seed 42
```

Prerequisites: `data/processed/surrey_free_data_corridor_summary.csv`, `surrey_sentinel2_scene_qa.csv`, `surrey_sentinel2_corridor_stats.csv`, `surrey_eccc_weather_stress_stats.csv`. Optional: `municipality_summary.csv` or `data/demo/demo_municipality_outage_summary.csv`.

**Contact context:** BC Hydro vegetation-weather outage risk proof-of-process demo, Surrey pilot AOI (`SURREY-TX-BUF-200M`, 200 m transmission buffer).
