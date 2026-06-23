# Open Data Fallbacks vs Planet Products

Public and proxy datasets used when Planet is unavailable, in **Public/proxy only** sidebar mode, or for cross-checking licensed Planet layers. Planet is enrichment — not a replacement for BC Hydro internal data.

See also: [data_sources.md](data_sources.md), [planet_products_for_surrey.md](planet_products_for_surrey.md), [open_free_data_for_surrey.md](open_free_data_for_surrey.md) (Surrey catalogue + feature mapping), [free_data_integration_plan.md](free_data_integration_plan.md) (implementation order).

---

## Fallback matrix

| Open / public source | URL | What it provides | Maps to Planet product / demo field | Limitations vs Planet |
| --- | --- | --- | --- | --- |
| **ESA WorldCover 10 m** | https://esa-worldcover.org/en | Global land cover (11 classes): tree, shrub, grass, crop, built, bare, water, etc. | **A** — coarse green/brown/non-veg fractions; static baseline | 10 m, **annual** (2020/2021 vintages); no near-daily moisture or quarterly 3 m canopy height |
| **Land Cover of Canada 2020** | https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47 | 30 m national LC (EOSD classes) | **A**, partial **B** — forest/non-forest exposure | 30 m, single epoch; no structure height |
| **BC VRI (Vegetation Resources Inventory)** | https://catalogue.data.gov.bc.ca/dataset/vegetation-resources-inventory | Forest inventory polygons — species, height, crown closure (provincial) | **B** — canopy cover/height context | Vector inventory, update cadence varies; not satellite near-real-time; access via DataBC |
| **BC Transmission Lines** | https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines · WFS `pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP` | HV transmission linework (province-wide) | AOI definition for **all products** (corridor buffers) | Not distribution/feeder GIS; voltage often suppressed |
| **ECCC / MSC GeoMet** | https://api.weather.gc.ca/ · https://climate.weather.gc.ca/ | Observations & forecasts — wind, precip, temperature | **Weather term** (35% in Planet formula); independent of Planet | Point/station-based; not land-surface moisture |
| **BC Hydro outage map JSON** | https://www.bchydro.com/power-outages/app/outages-map-data.json | Live outage polygons, counts, customers | **public_outage_history_score** (live) | Snapshot only; no validated cause codes in public feed |
| **BC Hydro outage RSS** | https://www.bchydro.com/rss/outages/all.xml | Current outage text/events | Supplementary live context | No geometry |
| **Unofficial outage archive** | https://github.com/outages/bchydro-outages | Historical JSON snapshots | **public_outage_history_score** (municipality proxy) | Non-authoritative; incomplete geography |
| **DEM (BC provincial / global)** | https://catalogue.data.gov.bc.ca/dataset/digital-elevation-model-25m-grid-of-british-columbia-unrestricted-access-ministry-of-environment-and-climate-change-strategy · https://www.opentopography.org/ (SRTM/COP30) | Terrain elevation, slope | **terrain_access_score** (demo still uses synthetic corridors) | Public DEM ≠ ROW access / vehicle constraints |

---

## Product-by-product fallback strategy

### A — Vegetation cover (green / brown / non-vegetated)

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | ARPS / Area Monitoring indices | NDVI, bare-soil probability, land-cover classifiers |
| 2 | ESA WorldCover | % Tree + Shrub + Grass vs Built + Bare + Water within AOI |
| 3 | Canada 2020 LC | Forest class fraction vs urban/agriculture |

### B — Forest carbon / structure (canopy cover, height)

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | FCM 3m Canopy Cover + Height | Zonal mean quarterly |
| 2 | BC VRI | Mean crown closure / height from intersecting polygons |
| 3 | Canada 2020 + DEM | Forest mask + rough height from VRI or default stand table |

### C — PlanetScope / ARPS imagery

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | PlanetScope / ARPS subscription | 3 m time series |
| 2 | Sentinel-2 L2A (Copernicus, Planet Public Data catalog) | 10 m, 5-day; cloud gaps |
| 3 | Landsat Collection 2 (USGS via Planet Public Data) | 30 m, legacy change detection |

Planet Public Data docs: https://docs.planet.com/data/public-data/

### D — Change (vegetation growth / loss)

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | FCM quarter delta or ARPS NDVI trend | Normalized 0–1 change score |
| 2 | WorldCover 2020 vs 2021 | Class transition matrix in AOI |
| 3 | Sentinel-2 NDVI time series (open) | Custom slope; higher effort |

### E — Land surface temperature

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | LST 100m PV | Twice-daily, cloud-robust |
| 2 | MODIS LST (NASA) | 1 km, daily; gap-filled |
| 3 | ECCC station air temperature | Proxy only; not surface |

### F — Soil water content

| Priority | Source | Method |
| --- | --- | --- |
| 1 (Planet) | SWC 100m PV | Near-daily volumetric proxy |
| 2 | ECCC / agricultural drought indices | Indirect |
| 3 | Precip anomaly from MSC GeoMet | Weather-only dryness proxy |

---

## Demo app behavior by sidebar mode

| Data mode | Vegetation inputs | Formula |
| --- | --- | --- |
| **Public/proxy only** | `demo_corridors.csv` + open LC proxies in notebooks | `calculate_demo_risk_score` (40/30/20/10) |
| **Planet sample enabled** | `planet_surrey_sample_placeholder.csv` → live CSV | `calculate_surrey_planet_risk_score` (35/30/15/10/10) |
| **Synthetic fallback** | Bundled demo CSVs when live fetch fails | Same as mode selected, with 🟡 provenance |

---

## When to use fallbacks vs Planet

| Scenario | Recommendation |
| --- | --- |
| API / license pending | WorldCover + VRI + ECCC; keep placeholder CSV |
| Budget-limited PoC | 200 m corridor AOI + FCM + SWC only; ECCC for weather |
| Operational BC Hydro PoC | Planet + **internal** outage/GIS/vegetation ops data; fallbacks for QA only |
| Sandbox development | Alberta SWC/LST sandbox tiles; fallbacks for Surrey map context |

---

## Regeneration commands

```powershell
# Transmission overlay for corridor AOI
python TMP/scripts/fetch_bc_transmission_layer.py
python TMP/scripts/export_bc_transmission_sample.py --lower-mainland

# Surrey AOI hectares + GeoJSON
python TMP/scripts/compute_surrey_aoi_options.py
```
