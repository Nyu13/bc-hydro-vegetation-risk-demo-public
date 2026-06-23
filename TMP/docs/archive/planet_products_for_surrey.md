# Planet Products for Surrey BC PoC (Products A–F)

Reference for the Fujitsu / BC Hydro vegetation–weather outage risk **concept demo** in Surrey, BC. Planet is a **data provider only**; Fujitsu performs analytics and dashboard integration. Planet layers **do not replace** BC Hydro internal outage, feeder, vegetation, or asset data.

Sources: [Planet Data Catalog](https://docs.planet.com/data/), [Planetary Variables](https://docs.planet.com/data/planetary-variables/), [Planet Sandbox Data](https://docs.planet.com/data/planet-sandbox-data/), product pages linked below. Uncertainty is noted where docs are incomplete or product naming differs from demo labels.

---

## Product comparison table

| ID | Product name (Planet / demo label) | Measures | BC Hydro use case (Surrey PoC) | Spatial / temporal resolution | History (archive) | Format | Sandbox / trial? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A** | **Vegetation Cover** (demo) — *derived; no single PV product* | Green / brown / non-vegetated fractions; NDVI-like greenness; bare-soil probability | Corridor **exposure** and **dryness** proxies along transmission ROW; complements public land-cover | **Derived:** pixel-level from ARPS / PlanetScope (3 m) or Area Monitoring markers on Sentinel-2 / ARPS stacks; temporal = daily–weekly depending on source | ARPS from **2017-01-01**; PlanetScope catalog from **2014** (instrument-dependent) | GeoTIFF rasters (reflectance); Area Monitoring signal CSVs / markers | **Partial:** PlanetScope & ARPS sandbox (239 / 22 global regions); **no Surrey sandbox tile** | Planet catalog lists Forest Carbon, SWC, LST, Crop Biomass — not a standalone “Vegetation Cover” PV. Demo maps A to **Binary Land-Cover Marker** (forest, bare-soil) + NDVI time series from [Area Monitoring](https://docs.planet.com/data/analytic-feeds/area-monitoring/) or custom indices from ARPS/PlanetScope. Bare-Soil Marker supports brown / senescent signal. |
| **B** | **Forest Carbon / Structure** — [Forest Carbon Monitoring (FCM)](https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/) | Canopy cover (%), canopy height (m), aboveground live carbon (Mg/ha) at **3 m** | Tree **contact / fall-in** context; structure-based exposure near corridors | **3 m**, **quarterly** (seasonal quarters); global landmass 75°N–60°S | **Q1 2021 – present** (released last day of Mar/Jun/Sep/Dec) | Cloud-optimized GeoTIFF (UINT8/INT16 bands per [tech spec](https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/techspec/)) | **Yes:** [FCM sandbox](https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/sandbox/) — 16 regions globally; **none in BC** | Lower-res alternative: [Forest Carbon Diligence 30 m](https://docs.planet.com/data/planetary-variables/forest-carbon-diligence/) (archive **2013–2017** in sandbox). Subscriptions API only; rasters clipped to AOI. |
| **C** | **PlanetScope** — [PlanetScope imagery](https://docs.planet.com/data/imagery/planetscope/) | Multispectral TOA / surface reflectance, visual, UDM2 masks; ~**3 m** scenes | Visual confirmation, custom vegetation indices, change detection input | **~3 m** scenes (~280–630 km² per scene); **near-daily** revisit (Mission 1) | **July 2014 – present** (PS2); SuperDove **~2020 – present** | GeoTIFF assets via Data API / Orders API (`PSScene` item type) | **Yes:** [PlanetScope sandbox](https://docs.planet.com/data/imagery/planetscope/sandbox/) — BYOC collection, **2022-05-01 – 2023-04-30**, 239 regions | Orders API: ≤500 items/request. Surface reflectance ~8–12 h after publish. |
| **C′** | **Analysis-Ready PlanetScope (ARPS)** — [ARPS](https://docs.planet.com/data/imagery/arps/) | Harmonized **4-band surface reflectance** (blue, green, red, NIR); QA cloud/shadow mask | Time-series ML, consistent indices for **change** and green/brown fraction | **3 m ortho**, **near-daily** stacks | **2017-01-01 – present** (on-demand at subscription) | COG GeoTIFF (16-bit SR ×10,000) | **Yes:** [ARPS sandbox](https://docs.planet.com/data/imagery/arps/sandbox/) — **2021-01-01 – 2023-12-31**, 22 regions | Subscriptions API only; **Polygon AOI only** (no MultiPolygon). Source type `analysis_ready_ps`. |
| **D** | **Change** (demo) — *composite* | Vegetation change score; canopy cover delta; disturbance polygons | Detect **recent growth or loss** near corridors (encroachment, storm damage proxy) | **FCM:** quarterly 3 m; **custom:** daily–weekly from ARPS/PlanetScope; **Road & Building Change:** weekly/monthly (infrastructure, not vegetation) | FCM quarterly since 2021; ARPS since 2017 | Rasters (delta) or vector change polygons (Analytic Feeds) | **Partial:** FCM sandbox for structure change; PlanetScope/ARPS sandbox for custom change | No single “vegetation change” PV. Options: (1) delta between FCM quarters on canopy cover/height; (2) ARPS NDVI / forest-classifier time series; (3) [Road & Building Change Detection](https://docs.planet.com/data/analytic-feeds/road-building-change-detection/) if ROW encroachment is built environment (Analytics API). |
| **E** | **Land Surface Temperature (LST)** — [LST PV](https://docs.planet.com/data/planetary-variables/land-surface-temperature/) | Land surface temperature (°C); cloud-robust microwave + optical fusion | **Heat + drought stress** compounding vegetation dryness before storm windows | **20 m** (beta, single-field AOI), **100 m**, **1000 m**; **twice-daily** global | **100 m / 1000 m:** multi-year (sandbox LST 100m from **2017**; 1km from **2012**); exact product archive varies by source ID | GeoTIFF via Subscriptions API | **Yes:** [LST sandbox](https://docs.planet.com/data/planetary-variables/land-surface-temperature/sandbox/) — 17 regions; **Alberta, Canada** included (~580 km²); **not Surrey** | 20 m is **beta** and docs require **single agricultural field** AOI — **not suitable for full Surrey municipal AOI**. Use **100 m or 1000 m** for utility-scale pilot. Subscriptions API only. |
| **F** | **Soil Water Content (SWC)** — [SWC PV](https://docs.planet.com/data/planetary-variables/soil-water-content/) | Volumetric soil moisture proxy (unsaturated zone) | **Drought / moisture stress** before wind events; dryness composite in demo | **20 m** (beta, field-scale), **100 m**, **1000 m**; **near-daily** | **20+ years** archive on some products (sandbox 1km from **2015**; 100m from **2017**) | GeoTIFF via Subscriptions API | **Yes:** [SWC sandbox](https://docs.planet.com/data/planetary-variables/soil-water-content/sandbox/) — 17 regions; **Alberta, Canada** (~580 km²); **not Surrey** | 20 m beta: single-field AOI constraint (same as LST 20 m). **100 m recommended** for corridor/municipal summaries. Subscriptions API only. |

---

## API access summary (all products)

| API | PlanetScope / ARPS scenes | Planetary Variables (FCM, LST, SWC) | Analytic Feeds (change, area monitoring) |
| --- | --- | --- | --- |
| [Data API](https://docs.planet.com/develop/apis/data/) | ✅ Search catalog (`PSScene`, etc.) | ❌ | ❌ (scenes only) |
| [Orders API](https://docs.planet.com/develop/apis/orders/) | ✅ Activate / deliver scenes (≤500 items) | ❌ | ✅ Mosaic quads (Road & Building Change) |
| [Subscriptions API](https://docs.planet.com/develop/apis/subscriptions/) | ✅ Catalog imagery feeds; ✅ ARPS | ✅ Primary delivery for PV | ❌ (mosaic quads not supported for R&B change) |
| Analytics API | ❌ | ❌ | ✅ Query change detections |

**AOI summarization (Subscriptions):** Planetary Variable subscriptions can be **results-only** (no cloud delivery): the [results endpoint](https://docs.planet.com/guides/subscribe-to-planetary-variables/) returns CSV time series with per-delivery **`mean`** and **`valid_percent`** statistics over the subscription AOI — suitable for dashboard tiles without full raster hosting. Full rasters clip to AOI and deliver to S3 / Azure / GCS / GEE.

**Sandbox / trial:** [Planet Sandbox Data](https://docs.planet.com/data/planet-sandbox-data/) — **CC-BY-NC** license; requires account with **processing units** (paid or [trial](https://docs.planet.com/data/planet-sandbox-data/)). Locations are **25–200 km²** WorldStrat-style tiles globally — **Surrey is not a pre-built sandbox tile**; Alberta is the nearest Canadian SWC/LST sandbox.

---

## Recommended pairing for Surrey demo wiring

| Demo CSV field | Primary Planet product(s) |
| --- | --- |
| `vegetation_cover_green_pct` | A — NDVI / forest classifier (Area Monitoring) or ARPS-derived green fraction |
| `vegetation_cover_brown_pct` | A — Bare-Soil Marker or inverse greenness |
| `canopy_cover_pct`, `canopy_height_m` | B — FCM Canopy Cover 3m, Canopy Height 3m |
| `vegetation_change_score` | D — FCM quarter-over-quarter or ARPS temporal change |
| `soil_water_content` | F — SWC 100m (normalized 0–1 in app) |
| `land_surface_temperature_c` | E — LST 100m |

See [surrey_planet_integration_notes.md](surrey_planet_integration_notes.md) and [demo_plan_with_planet_surrey.md](demo_plan_with_planet_surrey.md).
