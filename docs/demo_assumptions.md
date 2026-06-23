# Demo Assumptions

## Demo-Only Disclaimer

Demo only - uses public and proxy datasets. Final PoC would require BC Hydro internal outage history, feeder/circuit topology, vegetation records, asset condition, and operational data.

This dashboard is an illustrative prototype and must not be used for operational switching, dispatching, restoration planning, or customer-impact decision-making.

**PoC pilot region:** Surrey (Lower Mainland) — UI defaults only; bundled data still includes all BC Hydro regions and municipalities.

**Planet / Surrey PoC:** Sidebar **Data mode** controls whether `data/demo/planet_surrey_sample_placeholder.csv` participates in scoring (`src/planet_loader.py`). Planet mode enriches vegetation exposure/dryness (green/brown, canopy, change, soil moisture, LST) but does **not** replace BC Hydro internal outage, feeder, or vegetation records. No live Planet API in the demo — placeholder CSV only. Quote and AOI: [planet_surrey_data_request.md](planet_surrey_data_request.md). Expanded integration notes: [TMP/docs/archive/surrey_planet_integration_notes.md](../TMP/docs/archive/surrey_planet_integration_notes.md).

**Risk Map geometry:** **BC Hydro live** `outages-map-data.json` only; outages filtered to **Surrey** (municipality label when present, else `DEMO_PILOT_TRANSMISSION_BBOX`). Flat `polygon` lon/lat pairs are normalized to GeoJSON rings. Point markers appear only when no polygon exists.

**PoC risk score (0–100, illustrative):** Default demo: `0.40 × live weather_severity_score` (region mean from ECCC when available) `+ 0.30 × corridor exposure` (bundled `demo_corridors.csv` forest/historical/length proxy) `+ 0.20 × Surrey live outage density` (same Surrey-filtered map JSON as the Risk Map: 60% normalized outage count + 40% customers affected, caps in `src/risk_scoring.py`) `+ 0.10 × terrain/access` from demo corridors. **Planet sample enabled (Surrey):** `0.35 × weather + 0.30 × Planet vegetation exposure + 0.15 × vegetation dryness + 0.10 × public outage history + 0.10 × terrain/access`. Corridor rows stay **synthetic** (🟡); weather and outage density may be **live** (🟢) when fetches succeed.

## Public/Proxy Data Explanation

- **Streamlit Cloud:** live BC Hydro HTTPS may fail Python TLS verification. The app defaults to relaxed TLS on Cloud; set `BC_HYDRO_SSL_VERIFY = "0"` in Cloud **Secrets** if outages are empty (see `.streamlit/secrets.toml.example` and README).
- Public outage status sources (JSON/RSS) are used for current/recent visibility.
- Unofficial public snapshot archive is used only as a historical proxy reference.
- Public transmission geometry is treated as corridor proxy, not feeder topology.
- Demo corridor risk markers (`demo_corridors.csv`) remain **synthetic**; optional BC Geographic Warehouse overlay resolves: `data/processed/bc_transmission_lines_bc.geojson` (BC-wide), then `data/processed/bc_transmission_lines_lower_mainland.geojson`, then `data/demo/bc_transmission_lines_lower_mainland.geojson` (commit for Streamlit Cloud), then `data/demo/demo_bc_transmission_lines_sample.geojson` (~120 lines).
- **Refresh transmission overlay:** `python TMP/scripts/fetch_bc_transmission_layer.py` (Lower Mainland); `python TMP/scripts/fetch_bc_transmission_layer.py --full-province` (BC-wide); copy processed LM export to `data/demo/bc_transmission_lines_lower_mainland.geojson` for Cloud deploys.
- Public weather data is used for storm severity context.
- Public land-cover sources are used as vegetation exposure proxy.

## Synthetic Data Explanation

This prototype includes synthetic fallback datasets in `data/demo/` so the app works when live fetches fail.
Synthetic files:

- `demo_corridors.csv`
- `demo_weather.csv`
- `demo_outages.csv`
- `demo_risk_scores.csv`
- `demo_backtesting.csv`

Synthetic records are illustrative and should not be interpreted as operational BC Hydro history.

## What Not To Claim

- Do not claim this is a validated operational risk model.
- Do not claim feeder-level precision from public transmission geometry.
- Do not claim unofficial snapshots are BC Hydro-provided.
- Do not claim production readiness or decision-grade forecast quality.
- Do not claim calibration/validation against BC Hydro internal outage, topology, or vegetation treatment datasets.