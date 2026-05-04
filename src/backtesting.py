from __future__ import annotations

import pandas as pd

from src.config import DEMO_DATA_DIR


def load_backtesting_data() -> pd.DataFrame:
    return pd.read_csv(DEMO_DATA_DIR / "demo_backtesting.csv")


def compute_backtesting_metrics(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"capture_rate_pct": 0.0, "demo_vs_baseline_delta": 0.0}

    capture_rate = float(df["captured_in_top_risk_group"].mean() * 100.0)
    avg_demo = float(df["demo_model_score"].mean())
    avg_baseline = float(df["weather_only_baseline_score"].mean())
    return {
        "capture_rate_pct": round(capture_rate, 2),
        "demo_vs_baseline_delta": round(avg_demo - avg_baseline, 2),
    }

