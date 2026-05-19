# BC Hydro Vegetation-Weather Outage Risk Demo

## Purpose

This project is a **demo-only** Streamlit **concept dashboard** that illustrates how public and proxy datasets could support a **proxy-based ranking** workflow for vegetation–weather **review prioritization** (not outage prediction).

**Demo only — uses public and proxy datasets. A formal PoC would require BC Hydro internal outage history, feeder/circuit topology, vegetation records, asset condition, and operational data.**

This prototype illustrates analytical workflow only; it does not predict BC Hydro outages and must not be used for operational decisions.

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

### Live Public Only Mode (No Synthetic Fallback For Selected Sources)
In the app UI, enable:
- `Live public only (no synthetic fallback for outage JSON/RSS, unofficial snapshots, weather)`

When enabled, those sources return empty data on fetch failure instead of using synthetic fallback files.

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
- Public transmission lines dataset reference:
  - [https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a](https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a)
- Environment and Climate Change Canada:
  - [https://climate.weather.gc.ca/](https://climate.weather.gc.ca/)
  - [https://api.weather.gc.ca/](https://api.weather.gc.ca/)
- Vegetation/land-cover proxy options:
  - [https://esa-worldcover.org/en](https://esa-worldcover.org/en)
  - [https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47](https://open.canada.ca/data/en/dataset/ee1580ab-a23d-4f86-a09b-79763677eb47)

## Data Provenance (Real vs Synthetic)

- **Real public (preferred):** BC Hydro outage JSON/RSS, ECCC/MSC weather endpoints.
- **Public proxy:** unofficial outage snapshots, public transmission/land-cover proxy concepts.
- **Synthetic demo files:** `data/demo/demo_corridors.csv`, `data/demo/demo_weather.csv`, `data/demo/demo_outages.csv`, `data/demo/demo_risk_scores.csv`, `data/demo/demo_backtesting.csv`.
- **Bundled public context:** `data/demo/demo_municipality_population.csv` (Statistics Canada 2021 Census subset), `data/demo/demo_region_outage_summary.csv` (2025 unofficial snapshot region ranking), `data/demo/demo_municipality_outage_summary.csv` (top municipality hotspots), `data/demo/demo_region_map_context.csv` (region centroids + approximate regional population for map context).
- If real public fetch fails (or offline mode is enabled), the app uses synthetic fallback files to remain runnable.

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

Or manually copy `region_summary.csv` and `municipality_summary.csv` into `data/processed/`. The **Area selection** tab ranks regions/municipalities by unofficial snapshot outage counts and overlays approximate 2021 population on the map (no basemap).

**Top regions by unique outages (2025 unofficial archive, bundled snapshot):** Lower Mainland (~16k), South VI (~4.8k), North VI (~4.6k), Northern (~4k), Central Interior (~2.6k), Okanagan/Kootenay (~3.1k), Thompson/Shuswap (~3.1k).

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