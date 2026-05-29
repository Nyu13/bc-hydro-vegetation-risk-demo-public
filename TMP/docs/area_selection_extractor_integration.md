# Area selection ↔ outage-history extractor integration

How the **Area selection** tab in `bc_hydro_vegetation_risk_demo` gets rankings from `bchydro-outage-history-extractor` instead of bundled demo CSVs.

## What the extractor produces

**Directory:** `C:\workspace\bchydro-outage-history-extractor\data\processed\`

| File | Used by Area selection? | Purpose |
| --- | --- | --- |
| `region_summary.csv` | **Yes (primary)** | BC Hydro region rankings |
| `municipality_summary.csv` | **Yes (primary)** | Municipality rankings |
| `bchydro_public_outages_history.parquet` | **Optional enrich** | Recompute `avg_customers_per_unique_outage` if missing from summaries |
| `bchydro_public_outages_deduped.parquet` | No | Reference / other analysis |
| `candidate_regions.md` | No | Human-readable pilot notes |
| `*_merged.csv` / `*_merged.parquet` | Only if you point config there | After legacy JSON merge pipeline |

### Key columns (extractor → demo)

**Region (`region_summary.csv`):**

- `region_name` — must match `data/demo/demo_region_map_context.csv` for map centroids
- `unique_outages` — distinct `outage_id` (or dedupe key fallback)
- `tree_related_outage_count`, `weather_related_outage_count` — unique outages with cause flag on any snapshot row
- `avg_customers_per_unique_outage` — mean of peak `num_customers_out` per outage
- `suggested_priority_score` — weighted score (see extractor README)
- `first_snapshot_date`, `last_snapshot_date` — archive range banner in UI
- Extra columns (`total_customers_affected`, etc.) are **dropped** by the demo loader

**Municipality (`municipality_summary.csv`):**

- `region_name`, `municipality` — group key; municipality must match `demo_municipality_population.csv` for map coords
- Same metric columns as above (no date columns in bundled demo subset)

**History parquet** (row-level, not shown in tables):

- `region_name`, `municipality`, `outage_id`, `num_customers_out`, `is_tree_related`, `is_weather_related`, …

Legacy alias: `region` → renamed to `region_name`; `tree_related_unique_outages` → `tree_related_outage_count`.

## What the demo currently loads

**Loader:** `src/region_history_loader.py`

**Search order (first file wins):**

1. `$EXTRACTOR_OUTPUT_DIR/region_summary.csv` (or `municipality_summary.csv`)
2. `data/processed/region_summary.csv`
3. `data/demo/demo_region_outage_summary.csv` (bundled fallback)

History parquet search: `$EXTRACTOR_OUTPUT_DIR` → `data/processed/` → hardcoded extractor path.

**UI wiring:** `app.py` → `_area_selection_tab()` → `load_region_outage_summary()` / `load_municipality_outage_summary()` → `src/area_selection.py` for map layers.

**Map context (separate from outage counts):**

- Regions: `data/demo/demo_region_map_context.csv` (centroids, approximate population)
- Municipalities: `data/demo/demo_municipality_population.csv` (2021 CSD counts + lat/lon)

**Bundled snapshot today:** `data/demo/demo_*_outage_summary.csv` — values already match a prior extractor run; rows tagged 🟡 Demo/synthetic.

## Step-by-step workflow

### 1. Run the extractor pipeline

```powershell
cd C:\workspace\bchydro-outage-history-extractor
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Recommended first pass (daily samples since 2025)
python scripts/run_all.py --since 2025-01-01 --sample daily
```

Or stepwise: `clone_or_update_repo.py` → `export_commit_snapshots.py` → `build_historical_dataset.py` → `summarize_regions.py`.

Verify outputs exist and inspect top regions:

```powershell
python -c "import pandas as pd; print(pd.read_csv('data/processed/region_summary.csv').head())"
```

### 2. Point the demo at extractor output (fastest — no copy)

```powershell
cd C:\workspace\bc_hydro_vegetation_risk_demo
$env:EXTRACTOR_OUTPUT_DIR = "C:\workspace\bchydro-outage-history-extractor\data\processed"
streamlit run app.py
```

Open **Area selection**. Caption should show `region_summary.csv (extractor processed output)` and 🟢 Live badge (not 🟡 Demo/synthetic).

### 3. Or refresh bundled / local copies (portable demo)

From demo repo root:

```powershell
python TMP/scripts/refresh_area_selection_data.py
```

This script:

- Reads extractor `region_summary.csv` / `municipality_summary.csv`
- Writes `data/demo/demo_region_outage_summary.csv` (full regions)
- Writes `data/demo/demo_municipality_outage_summary.csv` (**top 40** by priority score only)
- Copies full summaries to `data/processed/`

Restart Streamlit (no env var required if `data/processed/` exists and takes precedence over demo files).

**Optional:** also copy history for offline customer-metric enrichment:

```powershell
Copy-Item "C:\workspace\bchydro-outage-history-extractor\data\processed\bchydro_public_outages_history.parquet" `
  "C:\workspace\bc_hydro_vegetation_risk_demo\data\processed\"
```

### 4. Confirm in the UI

- **Rank by → BC Hydro region:** sorted by `unique_outages`; tooltips show tree/weather counts
- **Rank by → Municipality:** main table shows **Lower Mainland only** (pilot filter); full list under **All BC regions**
- Map disks scale with √(`unique_outages`); green rings = population context only
- Expander **Refresh area-selection data** documents env var / copy paths

## Column mapping / aggregation

| Level | Extractor aggregation | Demo expectation | Notes |
| --- | --- | --- | --- |
| Region | `groupby("region_name")` | Same | 7 BC Hydro regions in map context file |
| Municipality | `groupby(["region_name", "municipality"])` | Same | Map needs exact name match in population CSV |
| Unique outages | `outage_id.nunique()` | `unique_outages` | Not sum of snapshot rows |
| Tree-related | unique outages where `is_tree_related` any row | `tree_related_outage_count` | Not `percent_tree_related` |
| Ranking | `suggested_priority_score` | Used in municipality map sort; region table sorts by `unique_outages` | Scores differ if archive date range changes |

No extra aggregation is required if you use extractor CSVs as-is. Custom rollups (e.g. merge small municipalities) would need a one-off script before refresh.

## Municipality vs region behavior in the demo

- **Region view:** all regions ranked; map uses `demo_region_map_context.csv` centroids
- **Municipality view:** table limited to `DEMO_PILOT_REGION` (`Lower Mainland`); map overlay same filter
- Municipalities without lat/lon in `demo_municipality_population.csv` appear in tables but not on map

To rank BC-wide municipalities, change the filter in `app.py` (`pilot_mun = mun_df.loc[...]`) or expand the population CSV.

## Automation options

| Approach | Effort | Notes |
| --- | --- | --- |
| **`EXTRACTOR_OUTPUT_DIR` in shell profile / `.env`** | Small | Best for local dev; no code change |
| **Run `refresh_area_selection_data.py` in CI or pre-demo** | Small | Updates bundled CSVs for offline demos |
| **Auto-refresh on Streamlit start** | Medium | Add startup hook in `app.py` or document in README; watch path permissions |
| **Subprocess `run_all.py` from demo** | Medium–large | Long-running; needs git + network; not suitable for every app launch |

Sidebar **Refresh live data** only clears live outage/weather cache — **not** area-selection summaries.

## Effort & risks

**Effort: Small** — integration hooks already exist (`region_history_loader`, README, refresh script). First-time extractor run is **medium** (git clone, many snapshots).

**Risks:**

- **Name mismatches** — extractor `region_name` / `municipality` strings must match demo coord files or map markers missing
- **Bundled municipality cap** — refresh script keeps top 40 only in `demo_municipality_outage_summary.csv`
- **Stale bundled data** — without env var or refresh, app uses old demo CSVs (still unofficial archive, but older date range)
- **Not operational data** — public snapshot archive; cause flags are text-matched demo labels
- **Merged vs default files** — if using legacy JSON merge, point at `region_summary_merged.csv` via rename or env dir contents
- **Provenance UX** — extractor-backed rows show 🟢 Live though data is still unofficial archive (not BC Hydro internal)

## Related files

- Demo: `src/region_history_loader.py`, `src/area_selection.py`, `app.py` (`_area_selection_tab`)
- Demo refresh: `TMP/scripts/refresh_area_selection_data.py`
- Extractor: `scripts/run_all.py`, `scripts/summarize_regions.py`, `src/summary.py`
