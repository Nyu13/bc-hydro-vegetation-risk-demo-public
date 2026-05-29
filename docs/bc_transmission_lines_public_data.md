# BC public transmission lines — download guide

Use this guide when the demo needs **British Columbia** HV line geometry for outage / vegetation workflow discussion.

Bundled sample: `data/demo/demo_bc_transmission_lines_sample.geojson` · Map toggle: “Show BC transmission lines…”

## Metadata URLs (Geo.ca / CSW)

| Resource | URL |
| --- | --- |
| GeoCore JSON | https://geocore.metadata.geo.ca/384d551b-dee1-4df8-8148-b3fcf865096a.geojson |
| CSW ISO record | https://csw.open.canada.ca/geonetwork/srv/csw?service=CSW&version=2.0.2&request=GetRecordById&outputSchema=csw:IsoRecord&ElementSetName=full&id=384d551b-dee1-4df8-8148-b3fcf865096a |
| BC ER ArcGIS portal | https://data-bc-er.opendata.arcgis.com/ |

Full download notes (KML stub, ogr2ogr, blockers): [TMP/docs/BC_TRANSMISSION_DOWNLOAD.md](../TMP/docs/BC_TRANSMISSION_DOWNLOAD.md).

## Three recommended public sources

### 1. OpenMaps WFS (best for scripts / ogr2ogr)

| Item | Value |
| --- | --- |
| Catalogue | [BC Transmission Lines — DataBC](https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines) |
| Geo.ca record | [384d551b-dee1-4df8-8148-b3fcf865096a](https://app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a) |
| WFS endpoint | `https://openmaps.gov.bc.ca/geo/pub/wfs` |
| Layer name | `pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP` |
| Native CRS | EPSG:3005 (BC Albers) — **bbox filters must use 3005, not WGS84** |
| Province feature count | ~3,658 lines (public release; voltage often null) |

**Bundled demo sample (Lower Mainland bbox, 120 features):**

```powershell
cd C:\workspace\bc_hydro_vegetation_risk_demo
# Lower Mainland bbox (recommended for outage demo region)
python TMP\scripts\export_bc_transmission_sample.py --lower-mainland

# Province-wide stratified sample (~70 features, <500 KB)
python TMP\scripts\export_bc_transmission_sample.py
```

**Full province export (gitignored under `data/`):**

```powershell
# After installing GDAL (OSGeo4W or conda: conda install -c conda-forge gdal)
ogr2ogr -f GeoJSON data\raw\bc_transmission_lines_full.geojson ^
  WFS:"https://openmaps.gov.bc.ca/geo/pub/wfs" ^
  pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP
```

**Lower Mainland subset with ogr2ogr** (reproject bbox to EPSG:3005 in QGIS first, or use the Python script above):

```powershell
ogr2ogr -f GeoJSON data\raw\bc_transmission_lower_mainland.geojson ^
  WFS:"https://openmaps.gov.bc.ca/geo/pub/wfs" ^
  pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP ^
  -spat_srs EPSG:3005 -spat 1199488 452096 1267016 499457
```

### 2. Open Government / Geo.ca (metadata + custom download)

| Item | Value |
| --- | --- |
| Federal portal | [Open Government — BC Transmission Lines](https://open.canada.ca/data/en/dataset/384d551b-dee1-4df8-8148-b3fcf865096a) |
| Licence | Open Government Licence – British Columbia |
| Bulk download | **BC Geographic Warehouse Custom Download** on the DataBC catalogue page (browser workflow; may email a link) |

Use this when you need a documented dataset record for procurement or metadata. For day-to-day dev, WFS (source 1) is faster.

### 3. ArcGIS MapServer REST (QGIS / ArcGIS Pro / `ogr2ogr`)

| Item | Value |
| --- | --- |
| Service | `https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer` |
| Layer index | **77** — BC Transmission Lines |
| Example query | `.../MapServer/77/query?where=1%3D1&outFields=*&f=geojson&resultRecordCount=1000` |

```powershell
ogr2ogr -f GeoJSON data\raw\bc_transmission_arcgis_sample.geojson ^
  "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer/77" ^
  -where "1=1"
```

**KML loader (~1 KB NetworkLink stub — not vector geometry; gitignore `data/*.kml`):**

The file only references the live layer URL for Google Earth:

`https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP.kml`

```powershell
curl.exe -o data\WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml ^
  https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml
```

Use WFS or catalogue bulk download for real coordinates — see TMP/docs/BC_TRANSMISSION_DOWNLOAD.md.

Per-layer WMS capabilities:

`https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows?service=WMS&request=GetCapabilities`

Global WMS/WFS index (all public BCGW layers):

- WMS: `https://openmaps.gov.bc.ca/geo/ows?SERVICE=WMS&REQUEST=GetCapabilities`
- WFS: `https://openmaps.gov.bc.ca/geo/ows?SERVICE=WFS&REQUEST=GetCapabilities`

Official how-to: [DataBC WMS/WFS getting started](https://bcgov.github.io/data-publication/pages/map_wms_wfs_getting_started.html).

## What blocks downloads

| Blocker | Symptom | Mitigation |
| --- | --- | --- |
| Corporate firewall / proxy | Timeout or TLS errors to `openmaps.gov.bc.ca`, `delivery.maps.gov.bc.ca` | Use bundled `data/demo/demo_bc_transmission_lines_sample.geojson`; run download script from an unrestricted network; ask IT to allow DataBC hosts |
| No GDAL on Windows | `ogr2ogr` not found | Use `python TMP/scripts/download_bc_transmission_sample.py` (geopandas + requests) |
| Wrong bbox CRS | WFS returns 0 features for Vancouver | Use EPSG:3005 bbox (script handles conversion) |
| WFS `count` cap | Partial province in one request | Paginate with `startIndex` or download full layer via catalogue order |
| Public attribute limits | `VOLTAGE`, `OWNER` often null | Expected per BC Hydro publication agreement; not a bug |
| Streamlit Cloud | No outbound WFS at runtime | Ship updated demo GeoJSON in git; checkbox reads local file only |

## Streamlit integration

- Toggle: **Show BC transmission lines (BC Geographic Warehouse — reference overlay)** on Risk Map / Area selection.
- Default off; demo corridor markers remain **synthetic** (`demo_corridors.csv`).
- Do not treat public HV lines as BC Hydro feeder topology or join them to outage polygons without validation.

## Regenerating local overlay (PoC)

**Full Lower Mainland layer (preferred at runtime — gitignored):**

```powershell
python TMP\scripts\fetch_bc_transmission_layer.py
```

Writes `data\processed\bc_transmission_lines_lower_mainland.geojson` (~900 features). `network_loader` uses this when present.

**Bundled demo sample (Streamlit Cloud fallback):**

```powershell
python TMP\scripts\export_bc_transmission_sample.py --lower-mainland
python TMP\scripts\export_bc_transmission_sample.py --lower-mainland --max-features 200
```

Commit `data/demo/demo_bc_transmission_lines_sample.geojson` only; keep processed/raw exports gitignored.
