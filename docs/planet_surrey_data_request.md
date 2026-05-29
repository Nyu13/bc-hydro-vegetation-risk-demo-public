# Planet Data Quote Request — Surrey BC Vegetation–Weather Outage Risk PoC

**Prepared for:** Planet sales / account team  
**Prepared by:** Fujitsu (analytics & dashboard) on behalf of BC Hydro discovery  
**Pilot geography:** Surrey, British Columbia, Canada  
**Date:** 2026-05-29  

---

## 1. Purpose and scope

Fujitsu is building an **illustrative proof-of-process dashboard** for BC Hydro that combines **weather severity**, **vegetation / environmental stress**, and **public outage proxies** into a discovery workflow. **Planet is requested as a remote-sensing data provider only.** Fujitsu performs analytics, scoring, and Streamlit dashboard presentation.

This request covers:

- Product selection for a Surrey AOI (see [surrey_aoi_options.md](surrey_aoi_options.md))
- Trial / sandbox access for ETL and API workflow validation
- Commercial quote for a **6–12 month PoC window** with defined AOI and delivery format
- AOI-level summary statistics suitable for dashboard tiles (not only full raster hosting)

**Planet data does not replace BC Hydro internal systems.** Outage history with validated causes, feeder/circuit topology, vegetation patrol/treatment records, asset condition, and work-management data remain BC Hydro responsibilities for any operational PoC.

---

## 2. Requested products (Products A–F)

Detailed comparison: [planet_products_for_surrey.md](planet_products_for_surrey.md).

| ID | Product | Preferred resolution | PoC role |
| --- | --- | --- | --- |
| A | Vegetation cover / green–brown fraction (derived from ARPS, PlanetScope, or Area Monitoring markers) | 3 m indices or FOI-level signals | Exposure & dryness proxies |
| B | Forest Carbon Monitoring — Canopy Cover 3m + Canopy Height 3m | 3 m, quarterly | Structure / encroachment context |
| C | Analysis-Ready PlanetScope (and/or PlanetScope surface reflectance) | 3 m, near-daily | Custom indices & change input |
| D | Vegetation change (FCM quarter deltas and/or ARPS time series) | 3 m quarterly + daily stacks | Recent growth/loss near corridors |
| E | Land Surface Temperature | **100 m** (not 20 m beta) | Heat–drought stress |
| F | Soil Water Content | **100 m** (not 20 m beta) | Moisture stress / dryness |

**Minimum viable commercial bundle (recommended for quote Option 1):**

- FCM Canopy Cover 3m + Canopy Height 3m (quarterly, 2021–present + ongoing during PoC)
- SWC 100 m (near-daily, maximum practical archive backfill for AOI)
- LST 100 m (twice-daily, aligned period)
- Subscriptions API delivery with **results-only** time series (`mean`, `valid_percent` per AOI) **plus** periodic GeoTIFF clips for map overlay QA

**Optional add-ons:**

- ARPS daily stack for custom green/brown derivation (Product A/D)
- PlanetScope scene package for visual validation (limited scene count)

---

## 3. Area of interest (AOI) options — please quote each

| Option | Description | Area (ha) | GeoJSON |
| --- | --- | ---: | --- |
| **Preferred** | Surrey transmission corridor **200 m buffer** (clipped to municipal boundary) | **~3,580** | `data/demo/surrey_transmission_buffer_200m.geojson` |
| Budget | 100 m corridor buffer | **~1,873** | `surrey_transmission_buffer_100m.geojson` |
| Conservative ROW | 300 m corridor buffer | **~5,239** | `surrey_transmission_buffer_300m.geojson` |
| Municipal context | Full City of Surrey boundary | **~36,475** | `surrey_municipal_boundary.geojson` |
| Targeted sub-area | Demo outage-proxy sub-area (~4 km radius, clipped) | **~3,859** | `surrey_outage_prone_subarea.geojson` |

**Note:** Official boundary download yields **36,475 ha**, higher than commonly cited ~31,600 ha — please confirm billing hectare definition (land vs. total polygon).

We can supply merged GeoJSON / Feature Collection via Planet Features Manager if required.

---

## 4. Delivery and integration requirements

| Requirement | Detail |
| --- | --- |
| API | **Subscriptions API** for all Planetary Variables; Data/Orders API only if PlanetScope scenes added |
| AOI statistics | **Results-only subscriptions** exporting CSV time series with `mean` and `valid_percent` per delivery ([guide](https://docs.planet.com/guides/subscribe-to-planetary-variables/)) |
| Raster delivery | Cloud delivery (Azure Blob or S3) — destination TBD; COG GeoTIFF preferred |
| Temporal window | Backfill to product maximum practical archive + **6–12 months** forward during PoC |
| Cadence | FCM quarterly; SWC/LST per product native cadence; summaries aggregated to **weekly** for dashboard if supported |
| CRS | WGS84 / UTM as delivered; Fujitsu reprojects to EPSG:3005 for BC overlay |
| Licensing | Commercial PoC use; clarify redistribution restrictions for BC Hydro internal viewers |

---

## 5. Trial and sandbox access (requested)

Per [Planet Sandbox Data](https://docs.planet.com/data/planet-sandbox-data/):

1. **Trial account** with processing units for API workflow development.
2. Sandbox collections for ETL proof **before** Surrey paid delivery:

| Sandbox collection | Relevance |
| --- | --- |
| [Soil Water Content](https://docs.planet.com/data/planetary-variables/soil-water-content/sandbox/) | SWC API + **Alberta, Canada** tile (nearest Canadian sample) |
| [Land Surface Temperature](https://docs.planet.com/data/planetary-variables/land-surface-temperature/sandbox/) | LST API + Alberta tile |
| [Forest Carbon Monitoring](https://docs.planet.com/data/planetary-variables/forest-carbon-monitoring/sandbox/) | FCM structure workflow (no BC tile — e.g., Idaho or Iowa) |
| [Analysis-Ready PlanetScope](https://docs.planet.com/data/imagery/arps/sandbox/) | ARPS subscription mechanics |
| [PlanetScope](https://docs.planet.com/data/imagery/planetscope/sandbox/) | Scene search / order workflow |

**Question:** Is CC-BY-NC sandbox data usable in a **non-public BC Hydro internal demo**, or does PoC require paid license even for development?

---

## 6. Questions for Planet

1. **Quota model:** How are hectares × time × product priced for FCM (quarterly), SWC 100m (near-daily), and LST 100m (twice-daily) over **~3,580 ha** for 12 months?
2. **Backfill:** Maximum archive depth available for Surrey AOI for each product (SWC/LST source IDs)?
3. **Feasibility:** Will Subscriptions API accept our Surrey corridor polygon, or will any portion return **infeasible area** errors ([docs](https://docs.planet.com/develop/apis/subscriptions/))?
4. **20 m beta products:** Confirm **100 m** is appropriate for mixed urban–forest utility corridor (20 m docs require single agricultural field).
5. **Product A mapping:** Recommended Planet SKU for **green / brown / non-vegetated fraction** along utility corridors — Area Monitoring vs. custom ARPS indices vs. other?
6. **Change product:** Best-supported approach for **vegetation encroachment / loss** near ROW — FCM quarterly delta vs. analytic feed vs. custom?
7. **Summarization:** Can subscription **results** provide zonal stats per corridor segment if we supply multiple AOI polygons (feeder-span proxies)?
8. **Timeline:** Typical lead time from PO to first data delivery for new AOI in BC, Canada.
9. **Support:** Technical contact for Subscriptions API + Features Manager during PoC integration.

---

## 7. Usage rights and disclaimer (PoC)

**Intended use:**

- Internal BC Hydro / Fujitsu discovery workshops and dashboard prototype
- Non-operational risk **illustration** only — not for switching, dispatch, restoration, or vegetation work orders

**Not intended use:**

- Operational outage prediction or vegetation management dispatch
- Redistribution of Planet rasters outside licensed parties
- Replacement of BC Hydro authoritative GIS or outage systems

**Attribution:** Fujitsu dashboard will display Planet data provenance and [PLANET_POC_DISCLAIMER](surrey_planet_integration_notes.md) text.

---

## 8. Contact and next steps

| Step | Owner | Action |
| --- | --- | --- |
| 1 | Fujitsu | Send this package + AOI GeoJSON to Planet account manager |
| 2 | Planet | Confirm sandbox/trial provisioning and quote Options 1–4 (AOI table) |
| 3 | Fujitsu | Implement Subscriptions ETL; replace placeholder CSV ([`planet_surrey_sample_placeholder.csv`](../data/demo/planet_surrey_sample_placeholder.csv)) |
| 4 | BC Hydro | Validate AOI and internal data gap list ([bc_hydro_internal_data_needed.md](bc_hydro_internal_data_needed.md)) |

---

## 9. Research summary (Task 7)

### Most useful Planet data for this PoC

| Rank | Product | Why |
| --- | --- | --- |
| 1 | **FCM Canopy Cover + Height 3m** | Directly feeds demo `canopy_cover_pct`, `canopy_height_m`, and vegetation exposure composite |
| 2 | **SWC 100m** | Drought/moisture stress — core to `vegetation_dryness_score` |
| 3 | **LST 100m** | Heat compounding — `heat_drought_stress_score` / transparency tab |
| 4 | **ARPS or derived green/brown** | Fills Product A fields not covered by FCM alone |
| 5 | **FCM / ARPS change** | `vegetation_change_score` for encroachment narrative |

### Recommended first purchase

**Subscriptions bundle** over **Surrey 200 m transmission buffer (~3,580 ha)**:

- FCM Canopy Cover 3m + Canopy Height 3m (quarterly)
- SWC 100m + LST 100m (aligned 12-month window + max backfill)
- Results-only CSV summaries for Streamlit + quarterly GeoTIFF clips for map QA

Use **Alberta SWC/LST sandbox** and **FCM sandbox (Idaho/Iowa)** for API development before Surrey paid AOI.

### AOI hectares (calculated 2026-05-29)

| AOI | Hectares |
| --- | ---: |
| Municipal Surrey | 36,475.1 |
| Corridor 100 m | 1,873.1 |
| Corridor 200 m | 3,580.0 |
| Corridor 300 m | 5,239.1 |
| Outage sub-area (demo) | 3,859.3 |

### Files created (this work package)

| File | Purpose |
| --- | --- |
| `docs/planet_products_for_surrey.md` | Products A–F table |
| `docs/surrey_aoi_options.md` | AOI options + hectares |
| `docs/planet_surrey_data_request.md` | This quote package |
| `docs/demo_plan_with_planet_surrey.md` | Streamlit integration plan |
| `docs/open_data_fallbacks.md` | Public data fallbacks vs Planet |
| `TMP/docs/planet_research_summary.md` | Condensed Planet research notes |
| `TMP/docs/surrey_aoi_hectares.json` | Machine-readable AOI areas |
| `TMP/scripts/compute_surrey_aoi_options.py` | Boundary download + buffer calc |
| `data/demo/surrey_municipal_boundary.geojson` | Option 1 geometry |
| `data/demo/surrey_transmission_buffer_*m.geojson` | Option 2 geometry |
| `data/demo/surrey_outage_prone_subarea.geojson` | Option 3 geometry |

### Next steps for manager email

1. Attach **AOI GeoJSON** (lead: 200 m buffer) and link to this document.
2. Request **trial + sandbox** activation and **written quote** for 12-month PoC on ~3,580 ha.
3. Ask Planet to confirm **Product A (vegetation cover fraction)** SKU and **change detection** recommendation.
4. Schedule **BC Hydro workshop** showing placeholder dashboard → live Planet feed roadmap ([demo_plan_with_planet_surrey.md](demo_plan_with_planet_surrey.md)).
5. Parallel track: BC Hydro internal data checklist — Planet does not replace outage/feeder/vegetation ops data.

### Sandbox products available (confirmed from Planet docs)

| Sandbox collection | Regions | Nearest to Surrey | License |
| --- | ---: | --- | --- |
| PlanetScope | 239 | None in BC (global WorldStrat tiles) | CC-BY-NC |
| Analysis-Ready PlanetScope | 22 | None in BC | CC-BY-NC |
| Forest Carbon Monitoring | 16 | None in BC (e.g., Idaho, Iowa) | CC-BY-NC |
| Forest Carbon Diligence | 4 | None in BC | CC-BY-NC |
| Land Surface Temperature | 17 | **Alberta, Canada** | CC-BY-NC |
| Soil Water Content | 17 | **Alberta, Canada** | CC-BY-NC |
| SkySat / Mosaics | varies | See respective sandbox pages | CC-BY-NC |

**Requirement:** Paid or trial account with **processing units**. Surrey-specific geometry requires **commercial subscription** — not available as pre-built sandbox tile.

---

*Document version: 2026-05-29. Planet product details sourced from docs.planet.com; pricing and feasibility subject to Planet account confirmation.*
