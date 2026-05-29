"""Print max observation timestamp from the weather loader (MSC GeoMet live path)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DEMO_OFFLINE_MODE
from src.weather_loader import load_weather_demo


def main() -> None:
    print("DEMO_OFFLINE_MODE", DEMO_OFFLINE_MODE)
    print("now_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    result = load_weather_demo()
    print("data_source", result.data_source)
    print("is_synthetic", result.is_synthetic)
    print("observation_time", result.observation_time)
    print("last_updated", result.last_updated)
    print("freshness_warning", result.freshness_warning or "(none)")
    print("detail", result.detail)
    print("rows", len(result.df))
    if not result.df.empty and "timestamp" in result.df.columns:
        print("df_timestamp_min", result.df["timestamp"].min())
        print("df_timestamp_max", result.df["timestamp"].max())


if __name__ == "__main__":
    main()
