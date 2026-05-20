"""Copy extractor processed summaries into demo bundle (run from demo repo root)."""
from __future__ import annotations

import shutil
from pathlib import Path

EXTRACTOR_PROCESSED = Path(
    r"C:\workspace\bchydro-outage-history-extractor\data\processed"
)
DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

REGION_COLS = [
    "region_name",
    "unique_outages",
    "avg_customers_per_unique_outage",
    "median_customers_per_outage",
    "tree_related_outage_count",
    "weather_related_outage_count",
    "percent_with_latlon",
    "suggested_priority_score",
    "first_snapshot_date",
    "last_snapshot_date",
]

MUN_COLS = [
    "region_name",
    "municipality",
    "unique_outages",
    "avg_customers_per_unique_outage",
    "median_customers_per_outage",
    "tree_related_outage_count",
    "weather_related_outage_count",
    "suggested_priority_score",
]


def main() -> None:
    import pandas as pd

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    region_src = EXTRACTOR_PROCESSED / "region_summary.csv"
    mun_src = EXTRACTOR_PROCESSED / "municipality_summary.csv"

    region_df = pd.read_csv(region_src)[REGION_COLS]
    region_df.to_csv(DEMO_DIR / "demo_region_outage_summary.csv", index=False)
    shutil.copy2(region_src, PROCESSED_DIR / "region_summary.csv")

    mun_df = pd.read_csv(mun_src).sort_values("suggested_priority_score", ascending=False).head(40)
    mun_df[MUN_COLS].to_csv(DEMO_DIR / "demo_municipality_outage_summary.csv", index=False)
    shutil.copy2(mun_src, PROCESSED_DIR / "municipality_summary.csv")

    print("Wrote demo_region_outage_summary.csv and demo_municipality_outage_summary.csv")
    print("Copied full summaries to data/processed/")


if __name__ == "__main__":
    main()
