# Surrey AOI Options for Planet Data Request

Three area-of-interest (AOI) options for the BC Hydro / Fujitsu Surrey vegetation–weather outage risk PoC. Hectares were computed from downloaded geometry on **2026-05-29** using `TMP/scripts/compute_surrey_aoi_options.py` (BC Albers EPSG:3005 for area).

**Important:** Public transmission geometry is a **province-wide HV proxy**, not BC Hydro feeder GIS. Outage sub-area is a **demo placeholder**, not validated feeder-level hotspot data.

---

## Hectare summary

| Option | AOI ID | Area (ha) | Notes |
| --- | --- | ---: | --- |
| 1 — Municipal boundary | `SURREY-MUNICIPAL` | **36,475.1** | City of Surrey official boundary (see verification below) |
| 2a — Transmission + 100 m buffer | `SURREY-TX-BUF-100M` | **1,873.1** | Intersection of buffer with municipal boundary |
| 2b — Transmission + 200 m buffer | `SURREY-TX-BUF-200M` | **3,580.0** | Same |
| 2c — Transmission + 300 m buffer | `SURREY-TX-BUF-300M` | **5,239.1** | Same |
| 3 — Outage-prone sub-area (demo) | `SURREY-OUTAGE-SUBAREA` | **3,859.3** | ~4 km radius box clipped to Surrey (centroid proxy) |

Machine-readable summary: `TMP/docs/surrey_aoi_hectares.json`

---

## Option 1 — Surrey municipal boundary

**Purpose:** Full-municipality pilot matching UI default (`DEMO_PILOT_MUNICIPALITY = Surrey`) and municipality-level outage archive proxy.

**Source:** City of Surrey ArcGIS REST — [Surrey City Boundary (layer 165)](https://gisservices.surrey.ca/arcgis/rest/services/Base_Map_All_Scales/MapServer/165)

**Download (GeoJSON):**

```
https://gisservices.surrey.ca/arcgis/rest/services/Base_Map_All_Scales/MapServer/165/query?where=1%3D1&outSR=4326&f=geojson
```

**Local export:** `data/demo/surrey_municipal_boundary.geojson`

**Area verification:** Computed **36,475 ha** from official polygon. Commonly cited figure **~31,600 ha** (~316 km²) likely reflects a different definition (e.g., land area excluding water, Fraser River foreshore, or Statistics Canada municipal boundary variant). **Use 36,475 ha for Planet quota discussions** unless BC Hydro specifies StatsCan/Census boundary; request clarification in quote.

**Planet fit:** Suitable for **100 m / 1000 m** LST and SWC; **FCM 3 m** over full municipal AOI is larger but feasible for subscription. **20 m beta** LST/SWC products are **not** suitable (single agricultural field constraint per Planet docs).

---

## Option 2 — Surrey + transmission corridor buffers (100 / 200 / 300 m)

**Purpose:** Focus Planet spend on **ROW-adjacent vegetation and stress** where tree contact and fall-in risk matter most, without claiming feeder-level precision.

**Transmission source:** BC Geographic Warehouse — bundled sample `data/demo/demo_bc_transmission_lines_sample.geojson` (40 segments intersecting Surrey in sample). Full Lower Mainland export: run `python TMP/scripts/fetch_bc_transmission_layer.py`.

**Method:**

1. Clip transmission lines to Surrey municipal boundary.
2. Buffer lines by 100 m, 200 m, and 300 m in EPSG:3005.
3. Union buffers and clip to municipal boundary.

**Local exports:**

- `data/demo/surrey_transmission_buffer_100m.geojson`
- `data/demo/surrey_transmission_buffer_200m.geojson`
- `data/demo/surrey_transmission_buffer_300m.geojson`

**Recommendation for Planet quote:** Lead with **200 m buffer (~3,580 ha)** as balanced ROW coverage vs. cost; offer 100 m (~1,873 ha) as budget option and 300 m (~5,239 ha) as conservative ROW + edge-tree capture.

**Caveats:** Public layer lacks voltage/owner fields in many records; distribution lines not included. Buffer is geometric, not electrical connectivity distance.

---

## Option 3 — Outage-prone sub-area in Surrey

**Purpose:** Smallest AOI for **targeted PoC** linking public outage history proxy to vegetation/weather scores.

**Public outage data available:**

| Source | URL | Surrey signal |
| --- | --- | --- |
| BC Hydro live map JSON | https://www.bchydro.com/power-outages/app/outages-map-data.json | Live density (demo app filter) |
| BC Hydro RSS | https://www.bchydro.com/rss/outages/all.xml | Current events only |
| Unofficial archive proxy | https://github.com/outages/bchydro-outages | Surrey **#1** municipality priority in bundled `demo_municipality_outage_summary.csv` (3,651 unique outages; 346 tree-related; priority 0.705) |

**Limitation:** No public **geocoded historical outage heat map** by feeder/span. Option 3 uses a **demo sub-area** (~4 km radius around Surrey centroid 49.19°N, 122.85°W) clipped to municipal boundary — **not** a validated hotspot polygon.

**Local export:** `data/demo/surrey_outage_prone_subarea.geojson` (~**3,859 ha**)

**Formal PoC upgrade:** Replace with BC Hydro internal outage–asset linkage or kernel density from validated causes.

---

## Recommended AOI for first Planet purchase

| Priority | AOI | Ha | Rationale |
| --- | --- | ---: | --- |
| 1 (quote lead) | 200 m transmission buffer | ~3,580 | Aligns with vegetation–corridor use case; manageable PV quota |
| 2 (budget) | 100 m buffer | ~1,873 | Lower cost; may miss edge-canopy |
| 3 (municipal context) | Full Surrey | ~36,475 | Needed for municipality-level dashboard row; higher PV cost |
| 4 (sandbox workflow only) | Alberta SWC/LST sandbox | ~58,000 | **Not Surrey** — use for API/ETL proof before Surrey delivery |

---

## Regenerating geometry

```powershell
cd C:\workspace\bc_hydro_vegetation_risk_demo
python TMP/scripts/compute_surrey_aoi_options.py
```

Refresh transmission sample first if needed:

```powershell
python TMP/scripts/fetch_bc_transmission_layer.py
python TMP/scripts/export_bc_transmission_sample.py --lower-mainland
```
