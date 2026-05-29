"""Verify live loaders return recent weather and parse outages (TMP)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.outage_loader import load_bchydro_outage_json, load_bchydro_rss
from src.weather_loader import load_weather_demo


def main() -> None:
    w = load_weather_demo()
    print("WEATHER", w.data_source, "synthetic=", w.is_synthetic, "last=", w.last_updated, "rows=", len(w.df))
    if not w.df.empty:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent = w.df[w.df["timestamp"].astype(str).str[:10] >= today[:8]]
        print("  timestamps:", w.df["timestamp"].min(), "->", w.df["timestamp"].max())
        print("  rows on/after", today[:8], "in May 2026 window:", len(recent))

    from src.outage_loader import combine_live_outage_frames, live_outage_metrics

    j = load_bchydro_outage_json()
    print("JSON rows", len(j), "synthetic", j["is_synthetic"].iloc[0] if not j.empty else "n/a")
    if not j.empty:
        print("  source", str(j["source"].iloc[0])[:100])
    if not j.empty and "latitude" in j.columns:
        print("  sample lat/lon", j.iloc[0][["latitude", "longitude", "municipality", "region"]].to_dict())
        surrey = j.loc[j["municipality"] == "Surrey"]
        print("  Surrey JSON", len(surrey), "customers", int(surrey["customers_affected"].sum()))

    r = load_bchydro_rss()
    print("RSS rows", len(r), "synthetic", r["is_synthetic"].iloc[0] if not r.empty else "n/a")
    if not r.empty:
        print("  sample", r.iloc[0][["municipality", "customers_affected", "status"]].to_dict())
        active = r.loc[r["status"].astype(str).str.contains("active", case=False, na=False)]
        print("  RSS active", len(active))

    metrics = live_outage_metrics(combine_live_outage_frames(j, r))
    print("COMBINED metrics", metrics)


if __name__ == "__main__":
    main()
