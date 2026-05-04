# Demo Assumptions

## Demo-Only Disclaimer

Demo only - uses public and proxy datasets. Final PoC would require BC Hydro internal outage history, feeder/circuit topology, vegetation records, asset condition, and operational data.

This dashboard is an illustrative prototype and must not be used for operational switching, dispatching, restoration planning, or customer-impact decision-making.

## Public/Proxy Data Explanation

- Public outage status sources (JSON/RSS) are used for current/recent visibility.
- Unofficial public snapshot archive is used only as a historical proxy reference.
- Public transmission geometry is treated as corridor proxy, not feeder topology.
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