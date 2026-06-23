# BC Hydro Vegetation–Weather Outage Risk Demo — Current State (May 2026)

Practical snapshot for **managers** (what to show, what not to claim) and **developers** (how to run, what data exists, how scoring works).  
**HEAD reference:** commit `a23545e` (2026-06-04) — Jan–May Sentinel-2 corridor stats refresh, 28 scene QA rows (27 processed, 1 skipped for cloud).

---

## 1. Purpose and disclaimers

| Topic | Statement |
| --- | --- |
| **What it is** | A **proof-of-process** Streamlit concept dashboard: combine vegetation, wildfire, weather, and **public outage proxies** into a transparent **planning prioritization** workflow for Okanagan / Kootenay transmission corridors. |
| **What it is not** | **Outage prediction**, operational decision support, or validated BC Hydro analytics. |
| **Data** | **Public and proxy** sources only in this repo — not official BC Hydro internal GIS, feeder topology, treatment records, or certified outage history. |
| **Pilot geography** | **Kelowna / Okanagan / Kootenay** (`OKANAGAN_REGION_NAME` in `src/regions.py`). The live Streamlit demo is **Okanagan-only**; Surrey pipeline scripts remain in the repo but are not exposed in the UI. |
| **On-screen disclaimer** | `DEMO_PRIMARY_DISCLAIMER` — proof-of-process only; do not use for operational decisions. |

A formal PoC would need internal outage history, feeder/circuit topology, vegetation programs, asset condition, and operational telemetry. See [bc_hydro_internal_data_needed.md](bc_hydro_internal_data_needed.md).

**Manager walkthrough:** [manager_demo_script.md](manager_demo_script.md)  
**Assumptions and limits:** [demo_assumptions.md](demo_assumptions.md)

---

## 2. How to run

### Local (Python 3.11+)

```powershell
pip install -r requirements.txt
streamlit run app.py
```

| Option | Command / UI |
| --- | --- |
| **Offline (no HTTP)** | `$env:DEMO_OFFLINE_MODE='1'` then `streamlit run app.py` — uses `data/demo/` synthetic CSVs. |
| **BC Hydro TLS (Windows / Cloud)** | App defaults to relaxed TLS when `BC_HYDRO_SSL_VERIFY` is unset on Windows or Streamlit Cloud. Force verify: `$env:BC_HYDRO_SSL_VERIFY='1'`. |
| **Theme** | Sidebar **Appearance** → Light / Dark (Plotly + shell CSS). Native widgets default light via `.streamlit/config.toml`. |

### Streamlit Community Cloud

1. Deploy from the **`public`** remote repo (see §9) — [share.streamlit.io](https://share.streamlit.io), main file `app.py`.
2. If live BC Hydro outages are empty, set in **App settings → Secrets** (see `.streamlit/secrets.toml.example`):

   ```toml
   BC_HYDRO_SSL_VERIFY = "0"
   ```

3. Redeploy or restart, then sidebar **Refresh live data**.
4. Ship small **`data/processed/*.csv`** with the app; keep large rasters in `data/raw/` (gitignored).

**May 2026 live example (when fetches succeed):** ~40 province-wide JSON outages; Surrey pilot slice often ~3 outages / ~54 customers (public JSON; website totals may differ).

---

## 3. Tab guide

The live demo has three tabs (Okanagan / Kootenay only):

| Tab | Audience | What it shows |
| --- | --- | --- |
| **Overview** | Managers | In-app “shows / does not show” lists; points to Planning tab. |
| **Kelowna / Okanagan Planning** | Both | Corridor priority map, top segments table, score breakdown, BC Hydro data-replacement table. Uses `okanagan_vegetation_wildfire_planning_dataset.csv`. |
| **Data Sources & Assumptions** | Both | Okanagan layer inventory (transmission WFS, WorldCover, ECCC, CWFIS, outage proxy, synthetic treatment gap). |

**Removed from live demo (still in repo for scripts):** Surrey Risk Dashboard, Risk Map, PoC Sample, Backtesting, Area selection, and sidebar region/mode selectors.

---

## 4. Sidebar controls

| Control | Effect |
| --- | --- |
| **Appearance** | Light / Dark theme for UI and charts. |

Live outage refresh and Surrey-specific controls (region selector, data mode, Planet) are not in the current demo UI.

---

## 5. Data layers inventory

| Layer | Source | Runtime | Notes |
| --- | --- | --- | --- |
| **BC Hydro outage JSON** | `outages-map-data.json` | Live fetch | Primary map/dashboard outages; Surrey filter in pilot views. |
| **BC Hydro outage RSS** | `rss/outages/all.xml` | Live fetch | Supplementary feed on dashboard. |
| **ECCC / MSC GeoMet weather** | `swob-realtime`, `climate-hourly` | Live fetch | Pilot bbox, ~48h; drives `weather_severity_score`. |
| **ESA WorldCover 2021** | Offline pipeline | Processed CSV | Tree/shrub/built/bare % per Surrey transmission buffer AOI. |
| **Sentinel-2 L2A (Jan–May 2026)** | Manual CDSE → `--safe-dir` | Processed CSV + QA | **28** scenes in QA file (**27** processed, **1** skipped); tiles T10UDV / T10UEV; NDVI/NDMI corridor stats. |
| **ECCC weather stress proxy** | Pipeline + live weather | Processed + live | Atmospheric stress from gust/precip/temp — **not** LST/SWC. |
| **BC transmission lines** | Bundled GeoJSON / optional WFS | Static overlay | Lower Mainland clip in `data/processed/` or demo sample; reference HV geometry, not feeders. |
| **Area selection archive** | `region_summary.csv`, `municipality_summary.csv` | Bundled or `EXTRACTOR_OUTPUT_DIR` | Unofficial snapshot archive proxy through **2026-05-19**. |
| **Planet commercial layers** | Placeholder CSV | Demo mode only | Request/quote narrative in UI; see [planet_surrey_data_request.md](planet_surrey_data_request.md). |
| **Demo corridors / risk table** | `data/demo/demo_*.csv` | Always synthetic | Illustrative segments, not distribution GIS. |
| **NALCMS / VRI / terrain / MODIS / ERA5** | Pipeline stages | Optional processed CSVs | Merged into free-data summary when built; stubs if credentials/rasters missing. |

**Provenance badges:** 🟢 Live public · 🟡 Demo/synthetic · 🟦 Open/free processed · 🔴 Unavailable (`src/data_provenance.py`).

Deeper catalogs: [data_sources.md](data_sources.md), [open_free_data_for_surrey.md](open_free_data_for_surrey.md), [bc_transmission_lines_public_data.md](bc_transmission_lines_public_data.md).  
Planet quote package: [planet_surrey_data_request.md](planet_surrey_data_request.md) · Products A–F detail: [TMP/docs/archive/planet_products_for_surrey.md](../TMP/docs/archive/planet_products_for_surrey.md).

---

## 6. Key files in `data/processed/`

| File | Contents |
| --- | --- |
| `surrey_free_data_corridor_summary.csv` | **Merged** open/free scores for Surrey 200 m transmission buffer (`SURREY-TX-BUF-200M`): WorldCover %, Sentinel-2 NDVI/NDMI/change, vegetation/canopy/dryness/heat scores, terrain, `data_status=open_free_processed`, `as_of_date`. |
| `surrey_worldcover_corridor_stats.csv` | Per-AOI WorldCover class percentages. |
| `surrey_sentinel2_corridor_stats.csv` | Corridor-level NDVI/NDMI means, change, cloud-filtered %, scenes/tiles used. |
| `surrey_sentinel2_scene_qa.csv` | Per-scene QA: scene_id, tile, sensing_date, status (`processed` / `skipped_no_clear_pixels`). |
| `surrey_eccc_weather_stress_stats.csv` | Offline ECCC atmospheric stress components for corridor AOI. |
| `surrey_nalcms_corridor_stats.csv`, `surrey_vri_corridor_stats.csv`, `surrey_terrain_corridor_stats.csv`, `surrey_environmental_stress_corridor_stats.csv` | Optional layer stats feeding the merge. |
| `bc_transmission_lines_lower_mainland.geojson` | Clipped public transmission lines for map overlay. |
| `region_summary.csv`, `municipality_summary.csv` | Archive **unique-outage** metrics for Area selection tab (extractor-compatible schema). |

Placeholders when pipeline not run: `data/demo/surrey_free_data_corridor_summary_placeholder.csv`.

---

## 7. Offline pipelines

### Surrey open/free (recommended quick path)

```powershell
python TMP/scripts/run_surrey_free_data_pipeline.py --static-only
```

Full run executes static land cover → Sentinel-2 → environmental stress → VRI → terrain → merge.  
**Runbook:** [free_data_pipeline_runbook.md](free_data_pipeline_runbook.md)

### Sentinel-2 (manual products, no runtime download)

1. Download L2A `.SAFE` / `.zip` to `data/raw/surrey/Sentinel-2 L2A/` (gitignored).
2. Process:

```powershell
python TMP/scripts/build_surrey_sentinel2_indices.py `
  --aoi data/demo/surrey_transmission_buffer_200m.geojson `
  --safe-dir "data/raw/surrey/Sentinel-2 L2A" `
  --out data/processed/surrey_sentinel2_corridor_stats.csv
```

3. Re-run free-data merge / pipeline so `surrey_free_data_corridor_summary.csv` picks up new stats.

**Notes:** [sentinel2_manual_download_notes.md](sentinel2_manual_download_notes.md)  
**May 2026 state:** Jan–May stack, commit `a23545e` updated corridor summary and scene QA (28 rows).

### Area selection refresh (optional)

```powershell
python TMP/scripts/refresh_area_selection_data.py
```

Or set `EXTRACTOR_OUTPUT_DIR` to an external `bchydro-outage-history-extractor` `data/processed/` path.

### Transmission overlay refresh (optional)

`python TMP/scripts/fetch_bc_transmission_layer.py` — copy LM GeoJSON to `data/demo/` for Cloud if needed.

### Causal AI exploration dataset (Fujitsu Research)

```powershell
python TMP/scripts/build_causal_ai_surrey_dataset.py --all
```

Recommended outputs:

| File | Purpose |
| --- | --- |
| `causal_ai_surrey_aoi_scenarios.csv` | Clean Surrey 200 m AOI — scene-level Sentinel-2 rows × intervention scenarios (mostly real open/free features) |
| `causal_ai_synthetic_training_dataset.csv` | Expanded synthetic dataset (default 1000 rows, seed 42) for causal discovery / decision-optimization workflow testing |
| `causal_ai_surrey_corridor_dataset.csv` | Legacy combined file (Surrey AOI + demo corridors); kept for backward compatibility |

Flags: `--surrey-only`, `--synthetic`, `--all` (default), `--synthetic-rows 1000`, `--seed 42`. Not outage prediction. See [causal_ai_research_team_dataset_brief.md](causal_ai_research_team_dataset_brief.md) and [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md).

---

## 8. Risk scoring (brief)

Implementation: `src/risk_scoring.py`, orchestration: `app.py` → `_prepare_risk_data()`.

### Default / Public–proxy composite (`calculate_demo_risk_score`)

```
risk_score =
  0.40 × weather_severity_score
+ 0.30 × vegetation_exposure_score
+ 0.20 × public_outage_history_score
+ 0.10 × terrain_access_score
```

- **Weather:** wind, precipitation, temperature, weather code (0–100).
- **Vegetation:** open/free blend (WorldCover / NALCMS / VRI / Sentinel-2) when summary usable; else corridor `forest_exposure` + `historical_outage_proxy` + length.
- **Outage history:** prefer **live** Surrey JSON density (60% count + 40% customers, capped); else municipality `suggested_priority_score` from archive summary.
- **Terrain:** from free-data slope or demo corridors.
- **Levels:** High ≥ 70, Medium ≥ 40, else Low.

### Planet sample mode (`calculate_surrey_planet_risk_score`)

```
risk_score =
  0.35 × weather
+ 0.30 × vegetation_exposure (Planet)
+ 0.15 × vegetation_dryness (Planet)
+ 0.10 × public_outage_history
+ 0.10 × terrain_access
```

Planet sample **wins** over open/free when mode is **Planet sample enabled** and CSV status is `placeholder` or `loaded`.

### Open/free sub-scores (when merged summary active)

Weighted blends for vegetation exposure, canopy, dryness (e.g. NDMI), heat/drought (ECCC stress proxy) — see `compute_free_data_*` functions in `src/risk_scoring.py`.

---

## 9. Git remotes and deploy target

| Remote | URL | Role |
| --- | --- | --- |
| **origin** | `https://github.com/Nyu13/bc-hydro-vegetation-risk-demo` | Private / full development repo |
| **public** | `https://github.com/Nyu13/bc-hydro-vegetation-risk-demo-public.git` | **Streamlit Cloud deploy source** — sanitized, committable `data/processed/` artifacts |

Push workflow: develop on **origin**; publish deployable commits to **public** when ready for Cloud. **No automatic push** from this doc.

---

## 10. Related documentation

| Document | Use when |
| --- | --- |
| [manager_demo_script.md](manager_demo_script.md) | ~5 min sponsor/manager demo script |
| [demo_assumptions.md](demo_assumptions.md) | Scoring weights, TLS, archive caveats |
| [free_data_pipeline_runbook.md](free_data_pipeline_runbook.md) | Building `data/processed/` open/free outputs |
| [planet_surrey_data_request.md](planet_surrey_data_request.md) | Planet commercial quote / AOI request draft |
| [surrey_aoi_options.md](surrey_aoi_options.md) | AOI geometries and hectare options |
| [sentinel2_manual_download_notes.md](sentinel2_manual_download_notes.md) | CDSE download + `--safe-dir` processing |
| [open_free_data_for_surrey.md](open_free_data_for_surrey.md) | Open data ↔ Planet product mapping |
| [bc_hydro_internal_data_needed.md](bc_hydro_internal_data_needed.md) | Formal PoC internal data requirements |
| [data_sources.md](data_sources.md) | Layer catalog and provenance |
| [bc_transmission_lines_public_data.md](bc_transmission_lines_public_data.md) | BC transmission download guide |
| [causal_ai_research_team_dataset_brief.md](causal_ai_research_team_dataset_brief.md) | Fujitsu Causal AI dataset brief |
| [causal_ai_surrey_dataset_dictionary.md](causal_ai_surrey_dataset_dictionary.md) | Causal AI CSV column dictionary |

**README:** project root `README.md` — setup, provenance table, live vs historical views.

---

## Quick reference — repo layout

```
app.py                 # Streamlit UI (mode-dependent tabs, sidebar Analysis region)
src/config.py          # URLs, pilot constants, paths, data modes
src/risk_scoring.py    # Score formulas
src/*_loader.py        # Data loaders + provenance
data/demo/             # Synthetic fallbacks + Planet placeholder
data/processed/        # Pipeline outputs (committed for Cloud where small)
TMP/scripts/           # Offline build pipelines (not runtime)
docs/                  # This file and linked guides
```

**Last updated for demo state:** May–June 2026 (Sentinel Jan–May stack, archive through 2026-05-19).
