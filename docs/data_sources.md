# Data Sources

## BC transmission geometry

**Step-by-step BC download:** [bc_transmission_lines_public_data.md](bc_transmission_lines_public_data.md) · [TMP/docs/archive/BC_TRANSMISSION_DOWNLOAD.md](../TMP/docs/archive/BC_TRANSMISSION_DOWNLOAD.md) (full URLs, KML stub note)

Preferred local export: `data/processed/bc_transmission_lines_lower_mainland.geojson` (gitignored) · Bundled fallback: `data/demo/demo_bc_transmission_lines_sample.geojson`

## Public Outage Sources

- BC Hydro outage map JSON: [https://www.bchydro.com/power-outages/app/outages-map-data.json](https://www.bchydro.com/power-outages/app/outages-map-data.json)
- BC Hydro outage RSS documentation: [https://www.bchydro.com/safety-outages/power-outages/outages_rss.html](https://www.bchydro.com/safety-outages/power-outages/outages_rss.html)
- BC Hydro outage RSS feed: [https://www.bchydro.com/rss/outages/all.xml](https://www.bchydro.com/rss/outages/all.xml)

## Unofficial Historical Proxy

- Public snapshot archive (unofficial): [https://github.com/outages/bchydro-outages](https://github.com/outages/bchydro-outages) — same JSON object schema as `outages-map-data.json`, but updated on a slower schedule; prefer the live BC Hydro URL for current outages and map polygons.

## Network / Corridor Proxy (BC demo)

### BC transmission lines (recommended for this project)

| Field | Value |
| --- | --- |
| Dataset | BC Transmission Lines |
| Publisher | Province of BC — BC Geographic Warehouse (DataBC) |
| Catalogue | [catalogue.data.gov.bc.ca/dataset/bc-transmission-lines](https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines) |
| Geo.ca | [384d551b-dee1-4df8-8148-b3fcf865096a](https://app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a) |
| GeoCore metadata JSON | [geocore.metadata.geo.ca/...geojson](https://geocore.metadata.geo.ca/384d551b-dee1-4df8-8148-b3fcf865096a.geojson) |
| CSW (ISO record) | [csw.open.canada.ca GetRecordById](https://csw.open.canada.ca/geonetwork/srv/csw?service=CSW&version=2.0.2&request=GetRecordById&outputSchema=csw:IsoRecord&ElementSetName=full&id=384d551b-dee1-4df8-8148-b3fcf865096a) |
| Open Government | [open.canada.ca dataset](https://open.canada.ca/data/en/dataset/384d551b-dee1-4df8-8148-b3fcf865096a) |
| WFS layer | `pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP` |
| WFS URL | `https://openmaps.gov.bc.ca/geo/pub/wfs` (per-layer: `.../WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows`) |
| WMS capabilities | [layer GetCapabilities](https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows?service=WMS&request=GetCapabilities) |
| KML loader (stub) | [openmaps loader.kml](https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml) — NetworkLink only; use WFS for geometry |
| ArcGIS layer | [whse/bcgw_pub_whse_basemapping MapServer /77](https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer/77) |
| Licence | Open Government Licence – British Columbia |
| Local PoC export (preferred) | `data/processed/bc_transmission_lines_lower_mainland.geojson` (~900 lines, Lower Mainland WFS bbox) |
| Bundled sample (fallback) | `data/demo/demo_bc_transmission_lines_sample.geojson` (~70–120 lines) |
| Province / manual (gitignored) | `data/raw/bc_transmission_lines_full.geojson`, `data/*.kml` loader stub |

Regenerate sample:

```bash
python TMP/scripts/fetch_bc_transmission_layer.py
python TMP/scripts/export_bc_transmission_sample.py --lower-mainland
```

**Caveats:** Public layer is a **province-wide HV transmission proxy**, not BC Hydro distribution/feeder GIS. Voltage and owner fields are often suppressed in the public release. Demo corridor risk scores remain **synthetic** (`demo_corridors.csv`).

### Synthetic demo corridors (default risk map)

- `data/demo/demo_corridors.csv` — illustrative corridor centroids/scores, not derived from live BC line geometry.

## Weather

- ECCC historical portal: [https://climate.weather.gc.ca/](https://climate.weather.gc.ca/)
- MSC GeoMet API: [https://api.weather.gc.ca/](https://api.weather.gc.ca/)

## Vegetation / Land-Cover Proxy

- ESA WorldCover: [https://esa-worldcover.org/en](https://esa-worldcover.org/en)
- 2020 Land Cover of Canada: [https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47](https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47)

## Notes

- All listed sources are public/proxy for this demo.
- Formal PoC should use BC Hydro internal operational and asset datasets (see [bc_hydro_internal_data_needed.md](bc_hydro_internal_data_needed.md)).
- Unofficial snapshot data is not BC Hydro-provided and should be treated as non-authoritative proxy input.
- Demo outputs are illustrative and must not be presented as feeder-level operational truth.

## Internal BC Hydro Data Boundary (Formal PoC)

The following are explicitly **not** in this demo and are required for a formal PoC:

- Internal outage history with validated causes and restoration timelines
- Feeder/circuit topology and electrical connectivity
- Vegetation inspection/patrol/treatment history and ROW records
- GIS asset condition and maintenance state
- Operations telemetry (SCADA/ADMS/protection/work management)
