# Daily outage archive for Causal AI Surrey dataset

`TMP/scripts/build_causal_ai_surrey_dataset.py` matches outage fields to exact `scene_date` using `bchydro_public_outages_history.parquet`.

## Search order

1. `$EXTRACTOR_OUTPUT_DIR/bchydro_public_outages_history.parquet`
2. `data/processed/bchydro_public_outages_history.parquet`
3. `C:\workspace\bchydro-outage-history-extractor\data\processed\bchydro_public_outages_history.parquet`

## If missing locally

Copy from the [bchydro-outage-history-extractor](https://github.com/outages/bchydro-outages) processed output, or set:

```powershell
$env:EXTRACTOR_OUTPUT_DIR = "C:\workspace\bchydro-outage-history-extractor\data\processed"
```

Without the parquet file, outage columns are left null and a warning is logged at build time.

## Daily matching rules (Surrey)

- Prefer rows where `snapshot_date` = `scene_date` (unique `outage_id`).
- Else nearest `snapshot_date` ≤ `scene_date` with outages active on that calendar day (`date_off` ≤ day end and `date_on` null or ≥ day start).
- `tree_related_outage_count_proxy` / `weather_related_outage_count_proxy` from `is_tree_related`, `is_weather_related`, or `cause` text.

Archive snapshot coverage extends through **2026-06-11** (daily sampling); Surrey rows through **2026-06-10**. Scene dates after the latest snapshot may still show zero when no outages were active that day.
