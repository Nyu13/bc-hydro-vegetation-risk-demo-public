# Data Sources

## Public Outage Sources

- BC Hydro outage map JSON: [https://www.bchydro.com/power-outages/app/outages-map-data.json](https://www.bchydro.com/power-outages/app/outages-map-data.json)
- BC Hydro outage RSS documentation: [https://www.bchydro.com/safety-outages/power-outages/outages_rss.html](https://www.bchydro.com/safety-outages/power-outages/outages_rss.html)
- BC Hydro outage RSS feed: [https://www.bchydro.com/rss/outages/all.xml](https://www.bchydro.com/rss/outages/all.xml)

## Unofficial Historical Proxy

- Public snapshot archive (unofficial): [https://github.com/outages/bchydro-outages](https://github.com/outages/bchydro-outages)

## Network / Corridor Proxy (BC demo)

- Geo.ca BC Transmission Lines dataset record: [https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a](https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a)
- Demo corridor markers and scores use **synthetic** `data/demo/demo_corridors.csv` — not live BC line geometry.

## Optional reference: Ville de Montréal transmission lines (2020)

**Geographic coverage: Montréal metropolitan area (Québec) only — not BC Hydro, not province-wide Hydro-Québec.**

| Field | Value |
| --- | --- |
| Dataset (FR) | Lignes de transport électrique |
| Publisher | Ville de Montréal — Division de la géomatique |
| Portal | [donnees.montreal.ca](https://donnees.montreal.ca/en/dataset/lignes-transport-electrique) |
| Canada open data | [ouvert.canada.ca](https://ouvert.canada.ca/data/fr/dataset/ac3515d6-2753-47a5-8575-35be7d127f43) |
| License | Creative Commons Attribution 4.0 (CC-BY 4.0) |
| Vintage | Aerial photography 2020 (Communauté métropolitaine de Montréal — CMM) |
| CRS (source) | EPSG:2950 (MTM zone 8, NAD83) — reprojected to WGS84 (EPSG:4326) in the demo bundle |
| Bundled sample | `data/demo/demo_montreal_transmission_lines_sample.geojson` (~108 KB, 160 aerial line features) |
| Local full copy (gitignored) | `data/lignes-transport-electrique-2020.gpkg` / `.zip` (~0.9 MB / ~0.2 MB) |

### GPKG layers (local file)

| Layer | Geometry | Rows (2020 file) | Role |
| --- | --- | --- | --- |
| `carto_ser_ele_tel_aerien` | MultiLineString | 160 | Suspended HV conductors (pylon-to-pylon symbolization) — **used in demo map overlay** |
| `carto_ser_electricite` | MultiPolygon | 1005 | Concrete bases supporting conductors (not drawn in demo) |

### Key attributes (`carto_ser_ele_tel_aerien`)

- `ID` — feature identifier (exported as `line_id` in GeoJSON)
- `SOURCE` — e.g. `Photo aérienne 2020, CMM`
- `TRAITEMENT` — photogrammetry (stereo)
- `DIFFUSEUR` — `Division de la géomatique, Ville de Montréal`
- `EQM`, `VERSION` — planimetric/altimetric quality metadata

### WGS84 extent (sample)

Approximately lon −73.96 to −73.48, lat 45.40 to 45.70 (greater Montréal). **Does not overlap British Columbia.**

### Regenerating the bundled sample

Place the official GPKG at `data/lignes-transport-electrique-2020.gpkg`, then:

```bash
python TMP/scripts/export_montreal_transmission_sample.py
```

### Recommended use in this demo

- **UI label** explicitly states Montréal / Québec reference — never “BC Hydro lines”.
- Optional **Risk Map** and **Area selection** toggles draw orange `PathLayer` paths for workflow discussion (line–vegetation proximity, satellite context). They are **off by default**.
- **Do not** spatially join to BC Hydro outage polygons or BC demo corridor centroids — different jurisdiction and CRS context; outage archive is BC-only proxy.
- For a formal BC PoC, replace with BC Hydro internal feeder/corridor GIS or the Geo.ca BC transmission proxy above.

## Weather

- ECCC historical portal: [https://climate.weather.gc.ca/](https://climate.weather.gc.ca/)
- MSC GeoMet API: [https://api.weather.gc.ca/](https://api.weather.gc.ca/)

## Vegetation / Land-Cover Proxy

- ESA WorldCover: [https://esa-worldcover.org/en](https://esa-worldcover.org/en)
- 2020 Land Cover of Canada: [https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47](https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47)

## Notes

- All listed sources are public/proxy for this demo.
- Formal PoC should use BC Hydro internal operational and asset datasets.
- Unofficial snapshot data is not BC Hydro-provided and should be treated as non-authoritative proxy input.
- Demo outputs are illustrative and must not be presented as feeder-level operational truth.

## Internal BC Hydro Data Boundary (Formal PoC)

The following are explicitly **not** in this demo and are required for a formal PoC:

- Internal outage history with validated causes and restoration timelines
- Feeder/circuit topology and electrical connectivity
- Vegetation inspection/patrol/treatment history and ROW records
- GIS asset condition and maintenance state
- Operations telemetry (SCADA/ADMS/protection/work management)
