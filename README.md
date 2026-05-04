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

The repo includes a light client-facing theme in `.streamlit/config.toml` (green accent). Remove or edit that file to fall back to Streamlit defaults.

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
- If real public fetch fails (or offline mode is enabled), the app uses synthetic fallback files to remain runnable.

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