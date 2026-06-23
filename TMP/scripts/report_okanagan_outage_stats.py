#!/usr/bin/env python3
"""Report Okanagan outage proxy stats after region-wide rebuild."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"

summary = pd.read_csv(PROC / "okanagan_outage_proxy_summary.csv")
daily = pd.read_csv(PROC / "okanagan_outage_daily_proxy.csv")
planning = pd.read_csv(PROC / "okanagan_vegetation_wildfire_planning_dataset.csv")

print("=== SUMMARY ===")
print(f"Places: {len(summary)}")
print("data_status counts:")
print(summary["data_status"].value_counts().to_string())
print("\nTop 15 by unique_outages:")
for _, r in summary.sort_values("unique_outages", ascending=False).head(15).iterrows():
    print(f"  {r['municipality']}: {int(r['unique_outages'])} unique, priority {r['suggested_priority_score']:.3f}")

print("\n=== DAILY ===")
print(f"Rows: {len(daily)}")
print(f"Dates: {daily['date'].nunique()} ({daily['date'].min()} .. {daily['date'].max()})")
print(f"Municipalities in daily: {daily['municipality'].nunique()}")
print(f"data_status: {list(daily['data_status'].unique())}")
print("\nTop 15 by total public_outage_count:")
for m, c in daily.groupby("municipality")["public_outage_count"].sum().sort_values(ascending=False).head(15).items():
    print(f"  {m}: {int(c)}")

compound = [m for m in summary["municipality"] if "," in str(m)]
print(f"\nCompound municipality labels: {len(compound)}")
for m in compound:
    print(f"  {m}")

synthetic = summary[summary["data_status"].astype(str).str.contains("synthetic", case=False, na=False)]
print(f"\nSynthetic placeholders in summary: {len(synthetic)}")
print(f"Planning outage_history_proxy_score mean: {planning['outage_history_proxy_score'].mean():.2f}")
