# Demo Assumptions

## Demo-Only Disclaimer

Demo only - uses public and proxy datasets. Final PoC would require BC Hydro internal outage history, feeder/circuit topology, vegetation records, asset condition, and operational data.

This dashboard is an illustrative prototype and must not be used for operational switching, dispatching, restoration planning, or customer-impact decision-making.

**PoC pilot region:** Surrey (Lower Mainland) — UI defaults only; bundled data still includes all BC Hydro regions and municipalities.

**Risk Map geometry:** **BC Hydro live** `outages-map-data.json` only; outages filtered to **Surrey** (municipality label when present, else `DEMO_PILOT_TRANSMISSION_BBOX`). Flat `polygon` lon/lat pairs are normalized to GeoJSON rings. Point markers appear only when no polygon exists.

**PoC risk score (0–100, illustrative):** `0.40 × live weather_severity_score` (region mean from ECCC when available) `+ 0.30 × corridor exposure` (bundled `demo_corridors.csv` forest/historical/length proxy) `+ 0.20 × Surrey live outage density` (same Surrey-filtered map JSON as the Risk Map: 60% normalized outage count + 40% customers affected, caps in `src/risk_scoring.py`) `+ 0.10 × terrain/access` from demo corridors. Corridor rows stay **synthetic** (🟡); weather and outage density may be **live** (🟢) when fetches succeed.

## Public/Proxy Data Explanation

- Public outage status sources (JSON/RSS) are used for current/recent visibility.
- Unofficial public snapshot archive is used only as a historical proxy reference.
- Public transmission geometry is treated as corridor proxy, not feeder topology.
- Demo corridor risk markers (`demo_corridors.csv`) remain **synthetic**; optional BC Geographic Warehouse overlay prefers `data/processed/bc_transmission_lines_lower_mainland.geojson` (local WFS export) and falls back to `data/demo/demo_bc_transmission_lines_sample.geojson`.
- **Refresh transmission overlay:** `python TMP/scripts/fetch_bc_transmission_layer.py` (full Lower Mainland WFS layer); bundled sample: `python TMP/scripts/export_bc_transmission_sample.py --lower-mainland`.
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