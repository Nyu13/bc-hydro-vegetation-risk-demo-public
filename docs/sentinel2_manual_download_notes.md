# Sentinel-2 Manual Download Notes (Surrey PoC)

The demo **does not download Sentinel-2 at Streamlit runtime**. Process products locally with `TMP/scripts/build_surrey_sentinel2_indices.py`:

- **MODE 1 (recommended):** `--safe-dir` — scan `.SAFE` folders and `.zip` L2A products
- **MODE 2 (legacy):** `--red/--nir/--swir` — single-scene band GeoTIFFs
- **MODE 3 (stub):** no inputs — writes placeholder CSV with manual instructions

Store all raw products under **`data/raw/surrey/`** (gitignored — do not commit `.SAFE/`, `.zip`, `.jp2`, or `.tif`).

Common layouts:

- `data/raw/surrey/Sentinel-2 L2A/*.zip` (CDSE bulk download)
- `data/raw/surrey/sentinel2/*.SAFE` (extracted products)
- `data/raw/surrey/sentinel2/B04_*.tif` (legacy band exports)

---

## 1. Copernicus Data Space (CDSE) — register

1. Create a free account: [https://dataspace.copernicus.eu/](https://dataspace.copernicus.eu/)
2. No API credentials are required for the **manual Browser download** workflow below.

---

## 2. Copernicus Browser — download L2A products

1. Open [Copernicus Browser](https://browser.dataspace.copernicus.eu/) and sign in.
2. **Search** → Sentinel-2 → **S2 L2A**.
3. Draw a bbox over Surrey / the transmission corridor (~49.19°N, 122.85°W) or upload `data/demo/surrey_transmission_buffer_200m.geojson`.
4. Filter:
   - **Cloud cover** &lt; 20% (adjust for winter)
   - **Date range** — e.g. growing season or multi-month stack for change
   - **Tiles** — Surrey corridor spans **T10UDV** and **T10UEV**
5. Download full **`.SAFE`** products or **`.zip`** archives (MSIL2A).
6. Place files under `data/raw/surrey/Sentinel-2 L2A/` or `data/raw/surrey/sentinel2/`.

Example product names:

```
S2C_MSIL2A_20260119T191721_N0511_R056_T10UEV_20260119T203312.SAFE
S2B_MSIL2A_20260124T191559_N0511_R056_T10UDV_20260124T211343.zip
```

The script discovers products recursively (including subfolders like `Sentinel-2 L2A`), extracts `.zip` to a temp folder, and reads bands from `GRANULE/*/IMG_DATA/R10m` and `R20m`.

---

## 3. Run SAFE processing (MODE 1)

```powershell
python TMP/scripts/build_surrey_sentinel2_indices.py `
  --aoi data/demo/surrey_transmission_buffer_200m.geojson `
  --safe-dir "data/raw/surrey/Sentinel-2 L2A" `
  --out data/processed/surrey_sentinel2_corridor_stats.csv
```

**Outputs:**

| File | Contents |
|------|----------|
| `data/processed/surrey_sentinel2_corridor_stats.csv` | Aggregated corridor NDVI/NDMI, change, scenes_used, tiles_used |
| `data/processed/surrey_sentinel2_scene_qa.csv` | Per-scene QA row (status, cloud filter, notes) |

**Processing steps (per scene):**

1. Locate **B04/B08** (10 m) and **B11/SCL** (20 m) under `GRANULE/*/IMG_DATA/`
2. Clip to AOI, resample B11/SCL to 10 m
3. Compute **NDVI** = (B08 − B04) / (B08 + B04), **NDMI** = (B08 − B11) / (B08 + B11)
4. **SCL mask** — exclude classes **0, 1, 3, 8, 9, 10, 11** (no data, saturated, cloud shadow, clouds, cirrus, snow)
5. Skip bad scenes with log message; pipeline does not crash

**Aggregation (multi-scene):**

- `sentinel2_ndvi_mean` / `sentinel2_ndmi_mean` — mean of per-scene means
- `period_start` / `period_end` — earliest / latest acquisition dates
- `scenes_used` — count of successfully processed scenes
- `tiles_used` — comma-separated MGRS tiles (e.g. `T10UDV,T10UEV`)
- `sentinel2_ndvi_change` — if ≥2 dates: latest-date mean minus earliest-date mean
- `cloud_filtered_pct` — mean share of AOI pixels kept after SCL mask

---

## 4. Legacy band GeoTIFF mode (MODE 2)

For single-scene band exports from Browser/QGIS:

```powershell
python TMP/scripts/build_surrey_sentinel2_indices.py `
  --aoi data/demo/surrey_transmission_buffer_200m.geojson `
  --red data/raw/surrey/sentinel2/B04_20250815.tif `
  --nir data/raw/surrey/sentinel2/B08_20250815.tif `
  --swir data/raw/surrey/sentinel2/B11_20250815.tif `
  --scl data/raw/surrey/sentinel2/SCL_20250815.tif `
  --period-start 2025-06-01 `
  --period-end 2025-08-31
```

**Optional NDVI change** — prior-period bands or `--prior-csv`.

**SCL masking (legacy mode):** classes **3, 8, 9, 10** excluded by default; add `--mask-snow` for class **11**.

---

## 5. Stub mode (MODE 3 — no products)

```powershell
python TMP/scripts/build_surrey_sentinel2_indices.py
# or full pipeline:
python TMP/scripts/run_surrey_free_data_pipeline.py
```

Writes `data/processed/surrey_sentinel2_corridor_stats.csv` with  
`data_status=unavailable_credentials_or_missing_rasters` and manual instructions in `instructions`.

---

## 6. Merge into corridor summary

```powershell
python TMP/scripts/build_surrey_free_data_summary.py
```

Updates `data/processed/surrey_free_data_corridor_summary.csv`:

- `vegetation_dryness_score` from NDMI: `clip((0.4 − ndmi) / 0.8 × 100, 0, 100)`
- `vegetation_change_score` from `sentinel2_ndvi_change` when present
- `scenes_used`, `tiles_used` from Sentinel-2 stats CSV
- WorldCover-based `vegetation_exposure_score` unchanged

The Surrey PoC tab shows 🟦 status for NDVI, NDMI, change, scenes_used, and cloud_filtered_pct when processed.

---

## References

- [CDSE Sentinel-2 L2A](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2)
- [Copernicus Browser](https://browser.dataspace.copernicus.eu/)
- [SCL class definitions](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)
