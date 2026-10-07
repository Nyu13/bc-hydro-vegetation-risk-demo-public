# Hydro One outage archive (GitHub Actions)

Unofficial public snapshots from Hydro One Storm Centre (Kubra).  
**Not** Hydro One operational data.

| File | Meaning |
|------|---------|
| `latest/` | Most recent fetch |
| `outages_history.csv` | Append-only history (`fetched_at_utc` per row) |
| `archive_index.csv` | One row per successful run |

Filled by `.github/workflows/hydro_one_outage_archive.yml` (`*/15 * * * *` UTC + manual dispatch).

Local:

```bash
python TMP/scripts/fetch_hydro_one_outages.py \
  --out-dir data/archives/hydro_one_outages \
  --append-history
```
