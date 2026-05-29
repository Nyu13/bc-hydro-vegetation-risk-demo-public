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


def apply_plotly_chart_theme(fig, *, dark: bool) -> None:
    """Match Plotly to app theme (Streamlit dataframe theme follows host config)."""
    template = "plotly_dark" if dark else "plotly_white"
    fig.update_layout(
        template=template,
        paper_bgcolor="rgba(0,0,0,0)" if dark else "#ffffff",
        plot_bgcolor="#262730" if dark else "#f8f9fa",
        font=dict(color="#fafafa" if dark else "#212529"),
        title_font=dict(color="#fafafa" if dark else "#212529"),
    )
    if dark:
        fig.update_xaxes(color="#fafafa", gridcolor="#3d4454", zerolinecolor="#3d4454")
        fig.update_yaxes(color="#fafafa", gridcolor="#3d4454", zerolinecolor="#3d4454")
    else:
        fig.update_xaxes(color="#212529", gridcolor="#dee2e6", zerolinecolor="#dee2e6")
        fig.update_yaxes(color="#212529", gridcolor="#dee2e6", zerolinecolor="#dee2e6")


def make_top_drivers_chart(risk_df: pd.DataFrame, *, dark: bool = False):
    driver_cols = [
        "weather_severity_score",
        "vegetation_exposure_score",
        "public_outage_history_score",
        "terrain_access_score",
    ]
    live_outage = bool(risk_df["live_outage_density_applied"].any()) if "live_outage_density_applied" in risk_df.columns else False
    means = risk_df[driver_cols].mean().rename(
        {
            "weather_severity_score": "Wind gust / weather severity",
            "vegetation_exposure_score": "Corridor exposure (demo proxy)",
            "public_outage_history_score": (
                "Live Surrey outage density" if live_outage else "Historical outage frequency proxy"
            ),
            "terrain_access_score": "Terrain/access constraints",
        }
    )
    means.loc["Treatment recency placeholder"] = 35.0
    fig = px.bar(
        x=means.index,
        y=means.values,
        labels={"x": "Driver", "y": "Avg Score"},
        title="Top risk drivers (illustrative)",
    )
    fig.update_layout(xaxis_tickangle=-25)
    apply_plotly_chart_theme(fig, dark=dark)
    return fig

