from __future__ import annotations

import pandas as pd
import plotly.express as px


def risk_color(level: str) -> list[int]:
    # Higher alpha so fills read closer to legend swatches and blend less with the basemap.
    if level == "High":
        return [220, 53, 69, 235]
    if level == "Medium":
        return [255, 193, 7, 230]
    return [40, 167, 69, 225]


def make_top_drivers_chart(risk_df: pd.DataFrame):
    driver_cols = [
        "weather_severity_score",
        "vegetation_exposure_score",
        "public_outage_history_score",
        "terrain_access_score",
    ]
    means = risk_df[driver_cols].mean().rename(
        {
            "weather_severity_score": "Wind gust / weather severity",
            "vegetation_exposure_score": "Vegetation exposure",
            "public_outage_history_score": "Historical outage frequency proxy",
            "terrain_access_score": "Terrain/access constraints",
        }
    )
    means.loc["Treatment recency placeholder"] = 35.0
    fig = px.bar(
        x=means.index,
        y=means.values,
        labels={"x": "Driver", "y": "Avg Score"},
        title="Top Risk Drivers (Demo)",
    )
    fig.update_layout(xaxis_tickangle=-25)
    return fig

