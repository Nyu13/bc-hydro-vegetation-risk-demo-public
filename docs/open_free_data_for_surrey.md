# Open & Free Data for Surrey BC — Vegetation–Weather Outage Risk Demo

Public and open datasets that can stand in for Planet commercial layers and BC Hydro internal vegetation/outage data during the Surrey proof-of-concept. Consolidates the former generic fallback matrix ([TMP/docs/archive/open_data_fallbacks.md](../TMP/docs/archive/open_data_fallbacks.md)) with Surrey-specific availability, licensing, and implementation priority.

Planet remains enrichment; free/open data demonstrates workflow and reduces early purchase risk but does **not** replace Planet products or BC Hydro operational data.

---

## Dataset catalog (A–J priority order)

| Dataset | Provider | URL | License | Spatial / temporal resolution | What it provides | Demo feature mapping | Limitations vs Planet / internal | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A — Sentinel-2 L2A (Copernicus)** | ESA / Copernicus Data Space | [CDSE Sentinel-2](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2) · [Process API](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html) · [openEO NDVI example](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/NDVI_Timeseries.html) | Copernicus free and open (Sentinel data policy) | **10 m** multispectral; **~5-day** revisit (twin satellites) | Surface reflectance (B04/B08/B11/B12), SCL cloud mask; derive **NDVI**, **NDMI** (moisture), NBR (change) | Products **A**, **C**, **D** — greenness, dryness, change time series | Cloud gaps in coastal BC; processing pipeline required; not 3 m daily PlanetScope | **High** |
| **B — Landsat Collection 2 (L2)** | USGS / NASA | [EarthExplorer](https://earthexplorer.usgs.gov/) · [LC2 Surface Reflectance](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) · [Planet Public Data catalog](https://docs.planet.com/data/public-data/) | USGS public domain | **30 m**; **16-day** revisit (L8/L9) | SR bands for NDVI/NDMI; legacy change detection; thermal bands for coarse LST | **A**, **C**, **D**, backup **E** | Coarser and less frequent than Sentinel-2/Planet; thermal is not PV-quality LST | **Medium** |
| **C — ESA WorldCover 2020 / 2021** | ESA WorldCover consortium | [esa-worldcover.org](https://esa-worldcover.org/en/data-access) · [AWS Open Data](https://registry.opendata.aws/esa-worldcover/) · [Zenodo 2021](https://doi.org/10.5281/zenodo.7254221) | **CC-BY 4.0** | **10 m**; static **2020** and **2021** vintages | 11-class land cover: Tree, Shrub, Grass, Crop, Built, Bare, Water, etc. | Product **A** — green/brown/non-veg fractions within corridor AOI | Static annual maps; no near-daily moisture or quarterly 3 m canopy height | **High** |
| **D — Land Cover of Canada 2020 (NALCMS)** | NRCan / CEC trilateral | [Open Canada](https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47) · [WMS](https://datacube.services.geo.ca/web/landcover.xml) · [CEC atlas](https://www.cec.org/north-american-environmental-atlas/land-cover-30m-2020/) | **Open Government Licence – Canada** | **30 m**; epoch **2020** (Canada) | 19 NALCMS classes; national forest/urban/cropland mask | **A**, partial **B** — forest/non-forest exposure baseline | 30 m; single epoch; no structure height | **High** |
| **E — Copernicus Land Monitoring Service (CLMS)** | European Commission / EEA | [CLMS portal](https://land.copernicus.eu/) · [HRL Forests](https://land.copernicus.eu/en/products/high-resolution-layer-forests-and-tree-cover) | Copernicus free and open (Europe products) | Varies (e.g. **10 m** tree cover in Europe) | Pan-European high-resolution layers: forest, impervious, grassland, water | Conceptual reference only for **A**/**B** methodology | **Europe-only** — not available for Surrey; listed for completeness | **Low** (N/A Canada) |
| **F — LidarBC (provincial)** | GeoBC / Caslys | [LidarBC portal](https://portal.lidarbc.ca/) · [DataBC catalogue](https://catalogue.data.gov.bc.ca/dataset/lidar) · [ArcGIS extent index](https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/LiDAR_BC_S3_Public/FeatureServer) | **OGL-BC** | **~1 m** point density (project-dependent); project vintages vary | Point clouds, **DSM/DEM** derivatives; canopy height derivable | **B** — canopy height / structure near forested corridors | **Metro Vancouver / Surrey municipal area largely uncovered** by provincial tiles; patchy Lower Mainland projects only | **Medium** (provincial) |
| **F′ — City of Surrey LiDAR 2022** | City of Surrey | [Raw LiDAR 2022](https://data.surrey.ca/dataset/raw-lidar-data) · [Elevation grid 2022](https://data.surrey.ca/dataset/elevation-grid-2022) · [Hillshade 2022](https://data.surrey.ca/dataset/lidar-hillshade-2022) · [Bulk data request](https://www.surrey.ca/services-payments/online-services/open-data/bulk-data) | **Open Government Licence** (City) | **City-wide** 2022 acquisition; LAS + derived rasters | High-resolution elevation, DSM; tree/building separation possible | **B**, **terrain/access** — canopy height proxy, slope | Large downloads (bulk ≥750 GB needs gis@surrey.ca); **not wired in demo**; processing required | **High** (Surrey municipal) |
| **G — BC VRI (Vegetation Resources Inventory)** | BC Forest Analysis & Inventory | [VRI R1 2024](https://catalogue.data.gov.bc.ca/dataset/vri-2024-forest-vegetation-composite-rank-1-layer-r1-) · [WFS](https://openmaps.gov.bc.ca/geo/pub/WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY/wfs?service=WFS&request=GetCapabilities) · [Data management](https://www2.gov.bc.ca/gov/content/industry/forestry/managing-our-forest-resources/forest-inventory/data-management-and-access) | **OGL-BC** | Vector polygons; photo-estimated inventory; **annual** projection | Species, **stand height**, **crown closure**, age, volume | **B** — canopy cover/height context along forested ROW segments | Urban Surrey has **sparse VRI** (inventory targets managed forest); not satellite near-real-time | **Medium** |
| **H — City of Surrey Open Data** | City of Surrey | [data.surrey.ca](https://data.surrey.ca/) · [ArcGIS REST](https://gisservices.surrey.ca/arcgis/rest/services) · [AerialImages MapServer](https://gisservices.surrey.ca/arcgis/rest/services/AerialImages/MapServer) | Open Government Licence | Orthophoto **10 cm** (2013 Abacus; **2020/2022** city catalogue); municipal boundaries | Orthophoto, LiDAR, land use, infrastructure; **no dedicated public tree-canopy layer** | Map context, manual QA, optional ML canopy from LiDAR/imagery | No standardized tree-canopy product; aerial services are reference overlays not analytics | **Medium** |
| **I — DEM / terrain (BC + global)** | GeoBC / OpenTopography | [BC CDED 25 m](https://open.canada.ca/data/en/dataset/7b4fef7e-7cae-4379-97b8-62b03e9ac83d) · [BC elevation page](https://www2.gov.bc.ca/gov/content/data/geographic-data-services/topographic-data/elevation) · [OpenTopography SRTM/COP30](https://www.opentopography.org/) | **OGL-BC** / various open | **25 m** (BC CDED); **30 m** (Copernicus DEM/SRTM) | Elevation, **slope**, aspect, roughness | **terrain_access_score** (demo uses synthetic corridors today) | Public DEM ≠ ROW access / vehicle constraints; 25 m coarse for fine corridor grading | **Medium** |
| **J — ECCC / ERA5 / SMAP / MODIS** | ECCC · ECMWF · NASA | [MSC GeoMet API](https://api.weather.gc.ca/) · [ERA5-Land CDS](https://cds.climate.copernicus.eu/) · [SMAP NSIDC](https://nsidc.org/data/nsidc-0779/versions/1) · [MOD11A1 LST](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD11A1) | ECCC open · CDS terms · NASA open | ECCC: station/forecast; ERA5-Land: **~9 km** hourly; SMAP: **1–9 km** daily; MODIS LST: **1 km** daily | Wind, precip, temperature (**ECCC**); soil moisture reanalysis (**ERA5**); surface moisture (**SMAP**); **LST** (**MODIS**) | Weather term (35% Planet formula); **F** dryness; **E** heat/drought stress | Point/station weather ≠ land-surface moisture at corridor scale; MODIS/SMAP much coarser than Planet SWC/LST 100 m | **High** (ECCC wired) · **Medium** (ERA5/SMAP/MODIS) |

### Already integrated in demo

| Dataset | URL | Demo use | Priority |
| --- | --- | --- | --- |
| BC transmission lines | [DataBC](https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines) · WFS `pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP` | Corridor AOI definition | **High** |
| BC Hydro outage JSON/RSS | [JSON](https://www.bchydro.com/power-outages/app/outages-map-data.json) · [RSS](https://www.bchydro.com/rss/outages/all.xml) | Live outage density | **High** |
| Unofficial outage archive | [GitHub](https://github.com/outages/bchydro-outages) | Municipality priority proxy | **Medium** |

---

## Feature mapping — demo fields vs free sources

| Demo feature | Best free source | Backup | Planet equivalent | Notes |
| --- | --- | --- | --- | --- |
| **Vegetation exposure** | ESA WorldCover (% tree+shrub+grass in corridor buffer) | NALCMS 2020 forest fraction | Product **A** (ARPS / Area Monitoring) | Zonal stats over `surrey_transmission_buffer_200m.geojson` |
| **Tree / forest cover** | WorldCover Tree class + NALCMS forest classes | BC VRI crown closure (forested polygons) | FCM Canopy Cover 3 m | Urban Surrey: WorldCover > VRI for continuous cover |
| **Canopy height** | City of Surrey LiDAR 2022 DSM − DEM | BC VRI stand height (where polygons exist) | FCM Canopy Height 3 m | Provincial LidarBC unlikely in city; municipal LiDAR is best free structural source |
| **Greenness** | Sentinel-2 NDVI (Copernicus CDSE / openEO) | Landsat NDVI | ARPS / PlanetScope indices | Cloud masking via SCL; aggregate to corridor mean |
| **Moisture / dryness** | Sentinel-2 NDMI + ERA5-Land volumetric soil water | SMAP 1 km surface moisture | SWC 100 m PV | Composite into `vegetation_dryness_score` placeholder |
| **Change** | Sentinel-2 NDVI trend or WorldCover 2020 vs 2021 class delta | Landsat annual NDVI slope | FCM quarter delta / ARPS trend | Higher effort; start with 2-epoch WorldCover |
| **LST / heat stress** | MODIS MOD11A1 (1 km daily) | ECCC station air temperature | LST 100 m PV | MODIS gap-filled; air temp is weak surface proxy |
| **Soil moisture** | ERA5-Land layer 1 + SMAP downscaled 1 km | Precip anomaly from ECCC | SWC 100 m PV | Reanalysis lags; not ROW-specific |
| **Terrain / access** | BC CDED 25 m slope + Surrey elevation grid | OpenTopography Copernicus DEM 30 m | DEM + internal ROW GIS | Demo still uses synthetic `terrain_access_score` |
| **Corridor geometry** | BC transmission WFS + bundled Surrey buffer GeoJSON | Municipal boundary clip | Subscription AOI | Already in `data/demo/surrey_transmission_buffer_*.geojson` |

---

## Surrey-specific availability checks

### LidarBC (provincial)

| Check | Result |
| --- | --- |
| Portal | [https://portal.lidarbc.ca/](https://portal.lidarbc.ca/) — interactive tile map, DSM/DEM/point-cloud download |
| Licence | Open Government Licence – BC |
| API / index | [LiDAR_BC_S3_Public FeatureServer](https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/LiDAR_BC_S3_Public/FeatureServer) — project extents, DSM/DEM/point-cloud indices |
| **Surrey municipal boundary** | **No comprehensive provincial LidarBC coverage** for built-up Surrey; provincial acquisitions target forestry, watershed, and emergency-management areas elsewhere in BC |
| **Practical PoC path** | Use **City of Surrey 2022 LiDAR** for municipal AOI; use LidarBC only for forested transmission segments outside city limits (if a tile intersects) |

### City of Surrey — tree canopy / aerial

| Check | Result |
| --- | --- |
| Open Data catalogue | [https://data.surrey.ca/](https://data.surrey.ca/) |
| LiDAR 2022 (sample + full bulk) | [Raw LiDAR](https://data.surrey.ca/dataset/raw-lidar-data) · [Elevation grid](https://data.surrey.ca/dataset/elevation-grid-2022) |
| Aerial imagery services | [AerialImages MapServer](https://gisservices.surrey.ca/arcgis/rest/services/AerialImages/MapServer) — REST export/query (2013, MrSID, White Rock ortho layers) |
| Developer resources | [Surrey open data](https://www.surrey.ca/services-payments/online-services/open-data) — CKAN API at `https://data.surrey.ca/api/3/action/` |
| **Tree canopy product** | **No published city-wide tree-canopy percentage raster** found in open catalogue; canopy must be **derived** from LiDAR DSM−DEM or classified from orthophoto |
| Bulk transfer | ≥750 GB: email [gis@surrey.ca](mailto:gis@surrey.ca) with external 1 TB USB 3.0 drive |

### BC VRI around Surrey

| Check | Result |
| --- | --- |
| Latest R1 layer | [VRI 2024 R1](https://catalogue.data.gov.bc.ca/dataset/vri-2024-forest-vegetation-composite-rank-1-layer-r1-) |
| WFS endpoint | `https://openmaps.gov.bc.ca/geo/pub/WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY/wfs` |
| WMS endpoint | `https://openmaps.gov.bc.ca/geo/pub/WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY/ows?service=WMS&request=GetCapabilities` |
| Custom extract | [BC Geographic Warehouse custom download](https://catalogue.data.gov.bc.ca/dataset/vri-2024-forest-vegetation-composite-rank-1-layer-r1-/resource/0b45b37d-59e5-415f-8dff-99024c9d9264) — clip to Surrey or 200 m buffer |
| **Surrey coverage** | Polygons concentrate on **managed forest / Green Timbers / riparian** areas; much of urban Surrey has **no VRI polygon** |
| Key attributes | `HEIGHT`, `CROWN_CLOSURE`, `SPECIES_CD_1`, `STAND_AGE` — use mean/sum for corridor intersection |

---

## Comparison to Planet products (summary)

See [planet_surrey_data_request.md](planet_surrey_data_request.md) and [TMP/docs/archive/planet_products_for_surrey.md](../TMP/docs/archive/planet_products_for_surrey.md) for Planet product detail. Free data closes the **concept gap** (vegetation + environment + weather + public outages) but not the **operations gap** (feeders, treatments, validated causes, SAIDI/SAIFI).

---

## Immediate layers to implement

Recommended first integrations for the Surrey 200 m corridor buffer (~3,580 ha), ordered by effort vs demo value:

1. **ESA WorldCover 2021** — clip to buffer; compute `% Tree`, `% Built`, `% Grass/Shrub`; write `forest_cover_pct`, `built_cover_pct` to corridor summary CSV. *Immediate-ish* (single zonal stats pass).
2. **NALCMS / Canada LC 2020** — cross-check forest mask; backup if WorldCover tile edge artifacts.
3. **Sentinel-2 NDVI + NDMI** — openEO or CDSE Process API time series; monthly mean → `greenness_index`, `moisture_index` columns. *Processing required* (account + pipeline).
4. **WorldCover 2020 vs 2021** — simple `% class change` → `vegetation_change_score` stub.
5. **MODIS MOD11A1 LST** — zonal mean daytime LST → `land_surface_temperature_c` proxy. *Processing required*.
6. **ERA5-Land soil moisture** — monthly anomaly at corridor centroid → drought context for `heat_drought_stress_score`.
7. **BC VRI intersection** — WFS clip to buffer; mean `CROWN_CLOSURE` / `HEIGHT` where polygons exist. *Medium effort* (sparse urban coverage).
8. **City of Surrey LiDAR 2022** — sample tiles along transmission buffer for canopy height validation. *Higher effort* (large data).
9. **BC CDED slope** — derive `terrain_slope_deg` mean for buffer; replace synthetic terrain component incrementally.

**Skip for Surrey PoC:** Copernicus CLMS HRL (Europe only). **Already wired:** ECCC weather, BC Hydro live outages, unofficial archive, BC transmission overlay.

Pipeline steps: [free_data_pipeline_runbook.md](free_data_pipeline_runbook.md). Historical integration plan: [TMP/docs/archive/free_data_integration_plan.md](../TMP/docs/archive/free_data_integration_plan.md).
