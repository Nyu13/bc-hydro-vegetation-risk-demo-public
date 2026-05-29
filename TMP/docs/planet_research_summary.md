# Planet Research Summary — Surrey BC PoC

Condensed findings from Planet documentation review (2026-05-29). Full detail: [planet_surrey_data_request.md](../docs/planet_surrey_data_request.md), [planet_products_for_surrey.md](../docs/planet_products_for_surrey.md).

---

## Key findings

### Sandbox / trial

- [Planet Sandbox Data](https://docs.planet.com/data/planet-sandbox-data/) — **CC-BY-NC**; requires account with **processing units** (paid or trial).
- Tiles are **25–200 km²** at predefined global locations (WorldStrat-style).
- **Surrey is NOT a sandbox location.** Nearest Canadian samples: **Alberta** on SWC and LST sandbox pages.
- Sandbox collections confirmed: PlanetScope (239 regions), ARPS (22), FCM (16), FCD (4), LST (17), SWC (17), SkySat, Mosaics.

### API access patterns

| Product class | Primary API |
| --- | --- |
| Planetary Variables (FCM, LST, SWC, Crop Biomass) | **Subscriptions API only** (not Data/Orders) |
| PlanetScope scenes | **Data API** search + **Orders API** delivery |
| Analysis-Ready PlanetScope | **Subscriptions API** (`analysis_ready_ps`) |
| Road & Building Change | **Analytics API** + Orders/Basemaps for mosaics |

### AOI summarization

- Subscriptions can omit `delivery` → **results-only** CSV with `mean` and `valid_percent` per time step over AOI.
- Full rasters clipped to subscription polygon; cloud delivery to S3/Azure/GCS/GEE optional.

### License / limits (from docs)

- Sandbox: **CC-BY-NC** — confirm commercial PoC terms with Planet sales.
- Orders API: ≤**500** items per request; ≤**50** for some SkySat/Tanager zip deliveries.
- Active orders cap: **10,000** per organization.
- LST/SWC **20 m beta**: AOI must be **single agricultural field** — **unsuitable for Surrey utility corridor/municipal AOI**. Use **100 m or 1000 m**.

### Product naming caveat

- No standalone Planet catalog product named **"Vegetation Cover"** — demo Product A maps to **derived indices** (Area Monitoring markers, ARPS/PlanetScope) or land-cover classifiers.
- **Forest Carbon Monitoring** provides canopy cover/height at **3 m quarterly** (2021–present).
- **Change** is composite: FCM quarterly deltas, ARPS time series, or infrastructure-focused Road & Building Change Detection.

---

## Most useful data for BC Hydro vegetation–outage narrative

1. FCM Canopy Cover + Height 3m  
2. SWC 100m  
3. LST 100m  
4. ARPS for green/brown derivation  
5. FCM/ARPS temporal change  

---

## Recommended first purchase

**~3,580 ha** (Surrey transmission **200 m buffer**) subscription bundle: FCM + SWC 100m + LST 100m, results CSV + quarterly raster QA.

---

## AOI hectares (2026-05-29)

| AOI | ha |
| --- | ---: |
| Municipal | 36,475.1 |
| Buffer 100m | 1,873.1 |
| Buffer 200m | 3,580.0 |
| Buffer 300m | 5,239.1 |
| Outage sub-area | 3,859.3 |

Municipal area exceeds ~31,600 ha reference — use official boundary polygon for quoting.

---

## Documentation URLs reviewed

- https://docs.planet.com/data/
- https://docs.planet.com/data/planet-sandbox-data/
- https://docs.planet.com/tags/sandbox-data/
- https://docs.planet.com/data/planetary-variables/
- https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/
- https://docs.planet.com/data/planetary-variables/land-surface-temperature/
- https://docs.planet.com/data/planetary-variables/soil-water-content/
- https://docs.planet.com/data/imagery/planetscope/
- https://docs.planet.com/data/imagery/arps/
- https://docs.planet.com/guides/subscribe-to-planetary-variables/
- https://docs.planet.com/develop/apis/data/
- https://docs.planet.com/develop/apis/orders/
- https://docs.planet.com/develop/apis/subscriptions/
- Sandbox pages per product (PlanetScope, ARPS, FCM, FCD, LST, SWC)

---

## Uncertainties (confirm with Planet)

- Exact pricing / hectare quota for mixed PV bundle over ~3,580 ha
- Commercial use of sandbox data in BC Hydro internal demos
- Best SKU for green/brown fraction along mixed urban–forest corridors
- Maximum SWC/LST backfill depth for Surrey coordinates
- Whether full Surrey municipal polygon triggers any infeasible-area errors
