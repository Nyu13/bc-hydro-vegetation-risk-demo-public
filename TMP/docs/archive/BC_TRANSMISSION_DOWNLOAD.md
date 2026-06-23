# BC Transmission Lines — download reference (developer)

Province-wide HV transmission lines from **BC Geographic Warehouse** (`WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP`). Use this for the BC Hydro vegetation-risk demo overlay.

## Metadata entry points (Geo.ca / CSW)

| Source | URL |
| --- | --- |
| GeoCore metadata (JSON) | https://geocore.metadata.geo.ca/384d551b-dee1-4df8-8148-b3fcf865096a.geojson |
| CSW GetRecordById (ISO) | https://csw.open.canada.ca/geonetwork/srv/csw?service=CSW&version=2.0.2&request=GetRecordById&outputSchema=csw:IsoRecord&ElementSetName=full&id=384d551b-dee1-4df8-8148-b3fcf865096a |
| DataBC catalogue | https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines |
| Custom bulk download (browser) | https://catalogue.data.gov.bc.ca/dataset/bc-transmission-lines/resource/6aa63176-7e73-4ff6-8126-04fa748a6622 |
| BC ER ArcGIS open data hub | https://data-bc-er.opendata.arcgis.com/ (search “transmission” / dataset title) |

**From GeoCore JSON (`options` array):**

| Protocol | Name | URL |
| --- | --- | --- |
| HTTPS | BC Geographic Warehouse Custom Download | catalogue resource above |
| HTTPS | GBA_TRANSMISSION_LINES_SP (KML loader) | https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml |
| OGC:WMS | GBA_TRANSMISSION_LINES_SP | https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows?service=WMS&request=GetCapabilities |

**Licence (GeoCore):** [Open Government Licence – British Columbia](https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc)

**Caveat:** Public release often has `VOLTAGE` / `OWNER` null per BC Hydro publication agreement.

---

## Best method for real line geometry

| Priority | Method | Why |
| --- | --- | --- |
| **1 (recommended)** | **WFS GetFeature** → GeoJSON | Vector lines, scriptable, bbox in native CRS |
| 2 | ArcGIS MapServer layer 77 | Same warehouse table; good for QGIS / `ogr2ogr` |
| 3 | DataBC catalogue custom download | Full province file; slower, browser/email workflow |
| 4 | WMS | **Raster tiles only** — not usable as PathLayer geometry |
| Avoid for geometry | KML `*_loader.kml` | **NetworkLink stub** (~1 KB), not features |

### WFS layer name

```
pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP
```

### WFS endpoints

| Scope | GetCapabilities | GetFeature base |
| --- | --- | --- |
| Global pub WFS | `https://openmaps.gov.bc.ca/geo/pub/wfs?service=WFS&request=GetCapabilities` | `https://openmaps.gov.bc.ca/geo/pub/wfs` |
| Per-layer | `https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows?service=WFS&request=GetCapabilities` | same path + `service=WFS&request=GetFeature` |

Native CRS: **EPSG:3005** (BC Albers). Bbox filters must use 3005, not WGS84.

### WMS (display only)

```
https://openmaps.gov.bc.ca/geo/pub/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP/ows?service=WMS&request=GetCapabilities
```

WMS layer name in capabilities: `pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP`.

---

## Why KML “loader” files are empty stubs

DataBC publishes a **NetworkLink** KML (~1 KB) that points Google Earth at the live layer:

```xml
<Link>
  <href>https://openmaps.gov.bc.ca/kml/geo/layers/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP.kml</href>
</Link>
```

- `data/WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml` in this repo is that stub (no `<Placemark>` / coordinates).
- `ogr2ogr` / GeoPandas on the loader alone returns **no line geometry**.
- For vectors use **WFS** or download the full `.kml` / shapefile via catalogue or WFS.

`data/*.kml` is gitignored so full KML exports stay local.

---

## Scripted sample (bundled in git)

From repo root (network + `geopandas` + `requests`):

```powershell
python TMP\scripts\download_bc_transmission_sample.py
```

Defaults: Lower Mainland WGS84 bbox `(-123.25, 49.05, -122.35, 49.45)`, up to **120** features → `data/demo/demo_bc_transmission_lines_sample.geojson`.

Custom bbox:

```powershell
python TMP\scripts\download_bc_transmission_sample.py --bbox -123.5 48.9 -122.0 49.5 --max-features 200
```

---

## ogr2ogr examples

**Full province (gitignore output under `data/raw/`):**

```powershell
ogr2ogr -f GeoJSON data\raw\bc_transmission_lines_full.geojson ^
  WFS:"https://openmaps.gov.bc.ca/geo/pub/wfs" ^
  pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP
```

**Lower Mainland bbox (EPSG:3005 — approximate metro extent):**

```powershell
ogr2ogr -f GeoJSON data\raw\bc_transmission_lower_mainland.geojson ^
  WFS:"https://openmaps.gov.bc.ca/geo/pub/wfs" ^
  pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP ^
  -spat_srs EPSG:3005 -spat 1199488 452096 1267016 499457
```

**ArcGIS REST (layer 77):**

```powershell
ogr2ogr -f GeoJSON data\raw\bc_transmission_arcgis_sample.geojson ^
  "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer/77"
```

---

## Streamlit demo wiring

- Toggle: **Show BC transmission lines (BC Geographic Warehouse — reference overlay)**.
- Loader: `src/network_loader.load_bc_transmission_paths()` reads bundled GeoJSON only (no live WFS in app).
- Paths: `src/config.py` → `BC_TRANSMISSION_GEOJSON`, `BC_TRANSMISSION_KML` (optional local stub).

---

## If WFS is blocked (corporate network)

1. Use committed `data/demo/demo_bc_transmission_lines_sample.geojson` (demo runs offline).
2. Run `download_bc_transmission_sample.py` from a network that allows `openmaps.gov.bc.ca`.
3. Or use DataBC **Custom Download** on the catalogue page and place vectors under `data/raw/` (gitignored).
4. Ask IT to allow: `openmaps.gov.bc.ca`, `delivery.maps.gov.bc.ca`, `catalogue.data.gov.bc.ca`.

---

## Related repo docs

- `docs/data_sources.md` — provenance table
- `docs/bc_transmission_lines_public_data.md` — BC download guide
