# Data Sources

## Public Outage Sources

- BC Hydro outage map JSON: [https://www.bchydro.com/power-outages/app/outages-map-data.json](https://www.bchydro.com/power-outages/app/outages-map-data.json)
- BC Hydro outage RSS documentation: [https://www.bchydro.com/safety-outages/power-outages/outages_rss.html](https://www.bchydro.com/safety-outages/power-outages/outages_rss.html)
- BC Hydro outage RSS feed: [https://www.bchydro.com/rss/outages/all.xml](https://www.bchydro.com/rss/outages/all.xml)

## Unofficial Historical Proxy

- Public snapshot archive (unofficial): [https://github.com/outages/bchydro-outages](https://github.com/outages/bchydro-outages)

## Network / Corridor Proxy

- Geo.ca BC Transmission Lines dataset record: [https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a](https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a)

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