#!/usr/bin/env python3
"""One-off probe: Okanagan/Kootenay places in outage archive."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.region_history_loader import _history_candidate_paths, _load_history_parquet  # noqa: E402
from src.config import DEMO_DATA_DIR, PROCESSED_DATA_DIR  # noqa: E402
from src.regions import OKANAGAN_BC_HYDRO_REGION, OKANAGAN_HISTORY_START_DATE  # noqa: E402

print("History paths:")
for p in _history_candidate_paths():
    print(f"  {p} exists={p.is_file()}")

history = _load_history_parquet()
if history is None:
    print("No history loaded")
    raise SystemExit(1)

print("Columns:", list(history.columns))
print("Shape:", history.shape)

rc = "region_name" if "region_name" in history.columns else "region"
print(f"Using region column: {rc}")
print("All region values:")
print(history[rc].value_counts())

ok = history[history[rc] == OKANAGAN_BC_HYDRO_REGION].copy()
print(f"\n{OKANAGAN_BC_HYDRO_REGION} rows: {len(ok)}")
print(f"Unique municipalities: {ok['municipality'].nunique()}")
print("\nTop municipalities by row count:")
print(ok["municipality"].value_counts().head(40).to_string())

print("\nAll municipalities (sorted):")
for m in sorted(ok["municipality"].dropna().astype(str).unique()):
    print(f"  {m}")

# Compound names
compound = ok[ok["municipality"].astype(str).str.contains(",", na=False)]
print(f"\nCompound municipality strings: {compound['municipality'].nunique()}")
if not compound.empty:
    print(compound["municipality"].value_counts().head(20).to_string())

# Date filter
date_col = next((c for c in ("snapshot_date", "date_off", "date", "pub_date") if c in ok.columns), None)
if date_col:
    ok["date"] = pd.to_datetime(ok[date_col], errors="coerce").dt.date.astype(str)
    recent = ok.loc[ok["date"] >= OKANAGAN_HISTORY_START_DATE]
    print(f"\nRows on/after {OKANAGAN_HISTORY_START_DATE}: {len(recent)}")
    print(f"Municipalities in recent window: {recent['municipality'].nunique()}")

# municipality_summary
for path in [PROCESSED_DATA_DIR / "municipality_summary.csv", DEMO_DATA_DIR / "demo_municipality_outage_summary.csv"]:
    if path.is_file():
        df = pd.read_csv(path)
        rcol = "region_name" if "region_name" in df.columns else "region"
        ok_sum = df[df[rcol] == OKANAGAN_BC_HYDRO_REGION]
        print(f"\n{path.name}: {len(ok_sum)} Okanagan/Kootenay municipalities")
        print(ok_sum[["municipality", "unique_outages"]].sort_values("unique_outages", ascending=False).head(30).to_string())
