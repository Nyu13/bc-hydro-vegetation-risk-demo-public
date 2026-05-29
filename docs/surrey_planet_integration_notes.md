# Surrey Planet Integration Notes

This document describes how proposed Planet remote-sensing layers fit into the BC Hydro vegetation–weather outage risk **concept demo** for Surrey, BC. It is not a production integration specification.

See also: [demo_assumptions.md](demo_assumptions.md) for overall demo boundaries.

## What Planet adds

Planet-style products are intended to enrich **vegetation and environmental stress** signals that public/proxy datasets do not cover well:

| Planet-oriented signal | Demo use |
| --- | --- |
| Green / brown vegetation fraction | Exposure and dryness proxies along the pilot AOI |
| Canopy cover & height | Structure-based exposure (contact / fall-in risk context) |
| Vegetation change score | Recent growth or loss near corridors |
| Soil water content | Drought / moisture stress before storm windows |
| Land surface temperature (LST) | Heat stress compounding dryness |

In the app, these feed illustrative scores in `src/risk_scoring.py` and are loaded from `data/demo/planet_surrey_sample_placeholder.csv` when **Data mode → Planet sample enabled** is selected in the sidebar.

## Feature mapping (demo)

| UI / score field | Source in Planet mode | Weight in Surrey formula |
| --- | --- | --- |
| `weather_severity_score` | ECCC / MSC live or `demo_weather.csv` | 35% |
| `vegetation_exposure_score` | Planet CSV (green + canopy + change) | 30% |
| `vegetation_dryness_score` | Planet CSV (brown + soil moisture) | 15% |
| `public_outage_history_score` | Live Surrey JSON density **or** municipality archive proxy | 10% |
| `terrain_access_score` | Bundled `demo_corridors.csv` | 10% |

Additional computed fields (`canopy_exposure_score`, `heat_drought_stress_score`) are shown on the **Surrey PoC Sample** tab for transparency; they inform the exposure/dryness composites but are not separate terms in the headline formula.

When Planet mode is **off**, the app keeps the original demo formula (`calculate_demo_risk_score`) and corridor-based vegetation exposure.

## BC Hydro data still required

Planet layers **do not replace** internal BC Hydro systems. A formal PoC would still need:

- Validated outage history with causes and asset linkage
- Feeder / circuit topology and protection zones
- Vegetation patrol, treatment, and work-management records
- Asset condition and clearance standards
- Operational telemetry and dispatch constraints

The in-app disclaimer states this explicitly.

## Assumptions and limitations

1. **Placeholder CSV only** — `planet_surrey_sample_placeholder.csv` uses synthetic values with `data_status=placeholder`. It demonstrates wiring, not calibrated Planet analytics.
2. **AOI granularity** — One Surrey pilot row (`SURREY-PILOT-001`); not feeder- or span-level.
3. **No live Planet API** — The demo does not call Planet APIs; integration would require licensing, AOI management, and ETL.
4. **Public outage proxy** — Live JSON and unofficial archive summaries are incomplete and not BC Hydro–authoritative.
5. **Corridor / terrain remain synthetic** — `terrain_access_score` still comes from bundled demo corridors when Planet mode is on.
6. **Not operational** — Scores are illustrative; thresholds and weights are for discovery conversations only.

## Related files

- `src/planet_loader.py` — load status (`not loaded` / `placeholder` / `loaded`) and row → score mapping
- `src/config.py` — `DEMO_DATA_MODES`, `PLANET_SURREY_SAMPLE_CSV`, `PLANET_POC_DISCLAIMER`
- `app.py` — sidebar data mode, **Surrey PoC Sample** tab, Risk Dashboard status label
