# Ontario outage data: live Hydro One + historical-ish IESO

## Reality check

There is **no** BC-style public Hydro One *distribution* outage archive.
For “historical-ish” Ontario data you can use **today**:

| Source | What you get | Script |
|--------|----------------|--------|
| **IESO TxOutagesTodayAll** | ~30 days of daily XMLs; deduped requests with `PlannedStart` often years back (transmission equipment, not distribution polygons) | `TMP/scripts/fetch_ieso_tx_outages_history.py` |
| **Hydro One Kubra live** | Current distribution outages (~50–hundreds) | `TMP/scripts/fetch_hydro_one_outages.py` |
| **Hydro One 15‑min archive** | Real distribution history **from now forward** | Task Scheduler wrappers below |

# Hydro One live outage archive (every 15 min)

Unofficial public Kubra Storm Centre snapshots for Ontario outreach demos. Not Hydro One operational data.

## One-shot fetch

```powershell
python TMP\scripts\fetch_hydro_one_outages.py --archive
```

Outputs under `TMP/temp/hydro_one_outages/`:

- `latest/` — most recent snapshot
- `snapshots/YYYYMMDD_HHMMSSZ/` — kept history when `--archive` is set
- `archive_index.csv` — one row per archived run

## Automate on this Windows machine (recommended to start)

Register Task Scheduler (every 15 minutes):

```powershell
powershell -ExecutionPolicy Bypass -File TMP\scripts\register_hydro_one_outage_task.ps1
```

Manual single run via the same wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File TMP\scripts\run_hydro_one_outage_archive.ps1
```

Optional Muskoka-style clip (set before register / run):

```powershell
$env:HYDRO_ONE_BBOX = "-80.0 44.5 -78.5 45.5"
```

Remove the task:

```powershell
powershell -ExecutionPolicy Bypass -File TMP\scripts\register_hydro_one_outage_task.ps1 -Unregister
```

Machine must be awake/logged in for Interactive tasks; use “Run whether user is logged on or not” in Task Scheduler if you need headless.

## GitHub Actions cron (recommended — works while laptop sleeps)

Workflow: `.github/workflows/hydro_one_outage_archive.yml`

- Schedule: every 15 minutes UTC (`*/15 * * * *`) + manual **Run workflow**
- Writes/commits: `data/archives/hydro_one_outages/` (`latest/`, `outages_history.csv`, `archive_index.csv`)

**Enable it**

1. Commit and push at least:
   - `TMP/scripts/fetch_hydro_one_outages.py`
   - `.github/workflows/hydro_one_outage_archive.yml`
   - `data/archives/hydro_one_outages/README.md`
2. On GitHub: **Settings → Actions → General** → allow Actions / allow Actions to create PRs/commits if needed (workflow uses `contents: write` + `git push` with `GITHUB_TOKEN`)
3. **Actions** tab → *Hydro One outage archive* → **Run workflow** once to verify
4. Leave the repo’s default branch with this workflow; cron only runs from the default branch

**Caveats**

- Cron can drift or be delayed; inactive private repos may skip schedules
- Each successful run creates a commit (append-only CSV stays small vs full snapshot folders)
- For IESO transmission history (already backfilled locally), use `fetch_ieso_tx_outages_history.py` separately (daily is enough)

Local Task Scheduler remains optional as a laptop backup.
