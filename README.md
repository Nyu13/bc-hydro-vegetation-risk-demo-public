# BC Hydro Vegetation-Weather Outage Risk Demo

## Purpose

This project is a **demo-only** Streamlit **concept dashboard** that illustrates how public and proxy datasets could support a **proxy-based ranking** workflow for vegetation–weather **review prioritization** (not outage prediction).

**Demo only — uses public and proxy datasets. A formal PoC would require BC Hydro internal outage history, feeder/circuit topology, vegetation records, asset condition, and operational data.**

This prototype illustrates analytical workflow only; it does not predict BC Hydro outages and must not be used for operational decisions.

**PoC pilot area:** Surrey (`DEMO_PILOT_MUNICIPALITY` in `src/config.py`; BC Hydro region `Lower Mainland`). On load: municipality view, Surrey listed first, maps at ~49.19°N / 122.85°W, demo corridors filtered to Surrey when present. **All BC regions** and **All BC demo corridors** expanders keep province-wide context.

## What This Demo Shows

- Where outage risk may be elevated (illustrative demo corridors)
- Why risk may be elevated (weather, vegetation proxy, outage proxy, terrain/access)
- How corridors can be ranked by risk level
- How an illustrative demo backtesting view can be presented (synthetic data)

## What This Demo Does NOT Claim

- It is not a production model
- It is not a validated outage forecast or operational decision system
- It does not represent BC Hydro feeder-level ground truth from internal GIS
- It does not include BC Hydro internal operational systems or private credentials

## Setup

1. Use Python 3.11+
2. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Run the dashboard:

```bash
streamlit run app.py
```

Choose **Light** or **Dark** under **Appearance** in the left sidebar (scoped runtime CSS + Plotly theme). `.streamlit/config.toml` sets a **default light** Streamlit theme for native widgets (e.g. dataframes); the sidebar still switches the shell and charts.

### Offline-First Mode (No Internet Required)
To force fully local behavior (no public fetch attempts), run:

```bash
set DEMO_OFFLINE_MODE=1
streamlit run app.py
```

In offline mode, loaders read local fallback files from `data/demo/`.

### BC Hydro live outages (TLS on corporate Python)

Browsers often reach [bchydro.com](https://www.bchydro.com) while **Python 3.14+ on Windows** fails with `CERTIFICATE_VERIFY_FAILED` / *Missing Authority Key Identifier* on the same host.

**Windows (recommended startup):** if `BC_HYDRO_SSL_VERIFY` is unset, the app uses `verify=False` on the first request (no failed verify attempt, no TLS retry log). To force certificate verification on Windows, set `BC_HYDRO_SSL_VERIFY=1` before starting Streamlit.

**Windows (PowerShell, current session)** — explicit disable (same as default on Windows):

```powershell
$env:BC_HYDRO_SSL_VERIFY='0'
streamlit run app.py
```

**Windows (cmd):**

```cmd
set BC_HYDRO_SSL_VERIFY=0
streamlit run app.py
```

**Linux/macOS:** verification is **on** when unset. To disable:

```bash
export BC_HYDRO_SSL_VERIFY=0
streamlit run app.py
```

After changing env vars, **restart** Streamlit (env is read at process start) and use sidebar **Refresh live data**. On non-Windows platforms, if verify is enabled and TLS fails, loaders retry once without verification (one warning per process).

**Expected live counts (May 2026 example):** ~40 JSON outages province-wide; RSS ~60 items (~40 active). **Surrey** pilot slice: **3** current outages, **54** customers in public JSON/RSS (BC Hydro website totals can differ by aggregation).

### Live Public Only Mode (No Synthetic Fallback For Selected Sources)
In the app UI, enable:
- `Live public only (no synthetic fallback for outage JSON/RSS, weather)`

When enabled, those sources return empty data on fetch failure instead of using synthetic fallback files.

**Risk Map defaults:** **BC Hydro live (JSON)** for outage polygons; corridor risk markers and weather rings off; outage geometry **Both** with outline-only polygons; 2px outage points (corridor markers are purple-tinted when enabled).

### Live vs historical data in the UI

| View | What it shows | Sources |
| --- | --- | --- |
| **Risk Dashboard** | **Current** outages and **recent** weather (last 48h) | BC Hydro `outages-map-data.json`, outage RSS, MSC GeoMet `swob-realtime` + `climate-hourly` |
| **Risk Map** | **Current** Surrey outages (map geometry) + corridor context | BC Hydro `outages-map-data.json` only (Surrey-filtered) |
| **Area selection** | **Historical** unique-outage rankings (archive proxy through **2026-05-19**) | Bundled `demo_*_outage_summary.csv` or extractor `data/processed/` |

Use sidebar **Refresh live data** to refetch JSON, RSS, and weather. Area-selection archive CSVs are not refreshed by that button.

### Refreshing live public feeds in a running session

Public outage JSON/RSS and the weather loader are cached for the Streamlit session (`@st.cache_data` with no TTL). Use the sidebar **Refresh live data** button to clear that cache and refetch without restarting the app. Bundled demo corridors, risk scores, backtesting, and area-selection archive tables are not refreshed by that button — update those via `EXTRACTOR_OUTPUT_DIR` or `TMP/scripts/refresh_area_selection_data.py` (see below).

## Project Structure

- `app.py`: Streamlit app
- `src/`: loaders, scoring, backtesting, visualization helpers
- `data/demo/`: fallback synthetic demo datasets
- `docs/`: assumptions, sources, and internal data requirements
- `notebooks/`: optional exploration notebook placeholder

## Public/Proxy Data Sources Referenced

- BC Hydro public outage JSON:
  - [https://www.bchydro.com/power-outages/app/outages-map-data.json](https://www.bchydro.com/power-outages/app/outages-map-data.json)
- BC Hydro outage RSS docs/feed:
  - [https://www.bchydro.com/safety-outages/power-outages/outages_rss.html](https://www.bchydro.com/safety-outages/power-outages/outages_rss.html)
  - [https://www.bchydro.com/rss/outages/all.xml](https://www.bchydro.com/rss/outages/all.xml)
- Unofficial public outage snapshot archive:
  - [https://github.com/outages/bchydro-outages](https://github.com/outages/bchydro-outages)
- BC public transmission lines (BC Geographic Warehouse): see [docs/bc_transmission_lines_public_data.md](docs/bc_transmission_lines_public_data.md); bundled sample `data/demo/demo_bc_transmission_lines_sample.geojson`
- Geo.ca / Open Government catalogue record:
  - [https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a](https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a)
- Environment and Climate Change Canada:
  - [https://climate.weather.gc.ca/](https://climate.weather.gc.ca/)
  - [https://api.weather.gc.ca/](https://api.weather.gc.ca/)
- Vegetation/land-cover proxy options:
  - [https://esa-worldcover.org/en](https://esa-worldcover.org/en)
  - [https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47](https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47)

## Data Provenance (Real vs Synthetic)

The app tags rows with `is_synthetic`, `data_provenance`, and `source`, and highlights synthetic rows in tables (amber `#fff3cd` or pink `#ffe0e0`). Map markers use **orange** for live public outages, **gray** for synthetic outage fallback, and **purple-tinted** disks for demo corridor risk (always synthetic).

| Dataset | Default (online) | `DEMO_OFFLINE_MODE=1` | Live public only ON + fetch fails | No public live source |
| --- | --- | --- | --- | --- |
| BC Hydro outage JSON | Live fetch → 🟢 | `demo_outages.csv` → 🟡 | Empty + warning → no hidden fallback | — |
| BC Hydro outage RSS | Live fetch → 🟢 | `demo_outages.csv` → 🟡 | Empty | — |
| Weather (ECCC / MSC GeoMet) | Live `swob-realtime` + `climate-hourly` (pilot bbox, 48h) → 🟢 | `demo_weather.csv` → 🟡 | Empty | — |
| Demo corridors / risk scores | Always `demo_*.csv` → 🟡 | Same | Same (labeled, not disguised as live) | Yes |
| Backtesting | Always `demo_backtesting.csv` → 🟡 | Same | Same | Yes |
| Area selection summaries | Bundled `demo_*` or extractor `data/processed/` | Bundled demo → 🟡 | N/A (local files) | Demo CSV if no extractor output |
| BC transmission overlay | Bundled public GeoJSON sample | Same | Same | Reference geometry only |

**Modes**

- **Online default:** try live for each fetchable source; synthetic CSV only on network/API failure.
- **Offline:** `set DEMO_OFFLINE_MODE=1` — all fetchable sources read `data/demo/` synthetic CSVs.
- **Live public only:** sidebar toggle — failed fetches return empty data and a message instead of synthetic fallback (outage JSON/RSS, unofficial snapshots, weather).

Implementation: `src/data_provenance.py`, loaders (`outage_loader`, `weather_loader`, `network_loader`, `backtesting`, `region_history_loader`), and `app.py` UI badges (🟢 Live / 🟡 Demo/synthetic).

### Refreshing area-selection data (from outage-history extractor)

After updating summaries in `bchydro-outage-history-extractor`:

```bash
# Option A — point the app at extractor output (no copy)
set EXTRACTOR_OUTPUT_DIR=C:\workspace\bchydro-outage-history-extractor\data\processed
streamlit run app.py
```

```bash
# Option B — refresh bundled demo CSVs (from demo repo root)
python TMP/scripts/refresh_area_selection_data.py
```

Or manually copy `region_summary.csv` and `municipality_summary.csv` into `data/processed/`. The **Area selection** tab shows **unique-outage metrics only** (not sums of snapshot rows):

- **Counts:** `unique_outages` — distinct `outage_id` values in the archive.
- **Customer impact:** `avg_customers_per_unique_outage` — mean of peak `num_customers_out` per outage (max across snapshots).
- **Cause flags:** `tree_related_outage_count` / `weather_related_outage_count` — unique outages with that cause on any snapshot row.
- **Ranking:** `suggested_priority_score` from the extractor (weighted on the metrics above plus map coverage fractions).

Snapshot-row sums such as `total_customers_affected` or `average_customers_affected` are omitted from the UI. Map disk size scales with √(unique_outages); population rings are context only.

**Top regions by unique outages (bundled snapshot):** Lower Mainland (~30k), South VI (~4.8k), North VI (~4.6k), Northern (~4k), Central Interior (~2.6k), Okanagan/Kootenay (~3.1k), Thompson/Shuswap (~3.1k).

**Population on map:** municipality disks use Statistics Canada 2021 CSD counts where available; regional green rings use approximate regional totals in `demo_region_map_context.csv` (demo-only, not official BC Hydro statistics).

## Demo Risk Formula (Illustrative)

```
risk_score =
    0.40 * weather_severity_score
  + 0.30 * vegetation_exposure_score
  + 0.20 * public_outage_history_score
  + 0.10 * terrain_access_score
```

All component scores are normalized to 0-100.

## Demo vs Formal PoC

This demo uses synthetic fallback records so it works even when live public fetch fails.
It does not include BC Hydro internal operational systems or validated feeder-level history.

A formal PoC would replace proxies with BC Hydro internal data including:

- internal outage history
- feeder/circuit topology
- vegetation inspection/treatment history
- asset condition and maintenance data
- restoration/crew response records
- operational telemetry and event logs

See `docs/bc_hydro_internal_data_needed.md` for detailed data requirements.