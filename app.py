from __future__ import annotations

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from src.backtesting import compute_backtesting_metrics, load_backtesting_data
from src.config import (
    DEMO_DATA_DIR,
    DEMO_OFFLINE_MODE,
    DEMO_PRIMARY_DISCLAIMER,
    DEMO_SECONDARY_DISCLAIMER,
)
from src.data_sources import DATA_SOURCES
from src.network_loader import load_transmission_lines
from src.outage_loader import (
    load_bchydro_outage_json,
    load_bchydro_rss,
    load_unofficial_outage_snapshots_placeholder,
)
from src.risk_scoring import (
    assign_risk_level,
    calculate_demo_risk_score,
    identify_top_risk_driver,
    suggest_review_action,
)
from src.theme_ui import apply_streamlit_theme
from src.visualization import make_top_drivers_chart, risk_color
from src.weather_loader import load_weather_demo


st.set_page_config(
    page_title="BC Hydro Vegetation-Weather Outage Risk Demo",
    layout="wide",
)

if "ui_theme_radio" not in st.session_state:
    st.session_state.ui_theme_radio = "Light"

with st.sidebar:
    st.markdown("### Appearance")
    st.radio(
        "Display theme",
        ["Light", "Dark"],
        horizontal=True,
        key="ui_theme_radio",
    )

apply_streamlit_theme(st.session_state.ui_theme_radio)

st.title("BC Hydro Vegetation-Weather Outage Risk Demo")
st.warning(DEMO_PRIMARY_DISCLAIMER)
st.info(DEMO_SECONDARY_DISCLAIMER)
st.caption(f"Data mode: {'Offline local demo CSVs' if DEMO_OFFLINE_MODE else 'Online with local CSV fallback'}")
LIVE_PUBLIC_ONLY = st.toggle(
    "Live public only (no synthetic fallback for outage JSON/RSS, unofficial snapshots, weather)",
    value=False,
    help="When enabled, failed public requests return empty data instead of demo CSV fallback for selected sources.",
)
st.caption(
    "Online mode attempts to use available public data. If unavailable, the app falls back to local "
    "synthetic demo CSVs so the dashboard remains runnable."
)


@st.cache_data(show_spinner=False)
def load_demo_risk_table() -> pd.DataFrame:
    return pd.read_csv(DEMO_DATA_DIR / "demo_risk_scores.csv")


@st.cache_data(show_spinner=False)
def load_outages_json_cached(live_public_only: bool) -> pd.DataFrame:
    return load_bchydro_outage_json(allow_synthetic_fallback=not live_public_only)


@st.cache_data(show_spinner=False)
def load_outages_rss_cached(live_public_only: bool) -> pd.DataFrame:
    return load_bchydro_rss(allow_synthetic_fallback=not live_public_only)


@st.cache_data(show_spinner=False)
def load_unofficial_snapshots_cached(live_public_only: bool) -> pd.DataFrame:
    return load_unofficial_outage_snapshots_placeholder(allow_synthetic_fallback=not live_public_only)


@st.cache_data(show_spinner=False)
def load_weather_cached(live_public_only: bool) -> pd.DataFrame:
    return load_weather_demo(allow_synthetic_fallback=not live_public_only)


def _build_data_provenance_table() -> pd.DataFrame:
    mode = (
        "Synthetic (offline forced)"
        if DEMO_OFFLINE_MODE
        else ("Live public only (no synthetic fallback)" if LIVE_PUBLIC_ONLY else "Public preferred + synthetic fallback")
    )
    rows = [
        {
            "dataset": "BC Hydro outage JSON",
            "primary_source_type": "Real public",
            "used_in_demo_for": "Current/recent outage context",
            "current_mode": mode,
            "fallback_if_unavailable": "data/demo/demo_outages.csv (synthetic proxy)",
        },
        {
            "dataset": "BC Hydro outage RSS",
            "primary_source_type": "Real public",
            "used_in_demo_for": "Optional source checks / feed demo",
            "current_mode": mode,
            "fallback_if_unavailable": "data/demo/demo_outages.csv (synthetic proxy)",
        },
        {
            "dataset": "Unofficial outage snapshots (GitHub)",
            "primary_source_type": "Public proxy (unofficial)",
            "used_in_demo_for": "Historical outage proxy concept",
            "current_mode": mode,
            "fallback_if_unavailable": "data/demo/demo_outages.csv (synthetic proxy)",
        },
        {
            "dataset": "Weather",
            "primary_source_type": "Real public (ECCC/MSC) + demo file",
            "used_in_demo_for": "Weather severity component",
            "current_mode": mode,
            "fallback_if_unavailable": "data/demo/demo_weather.csv (synthetic demo weather)",
        },
        {
            "dataset": "Corridor geometry",
            "primary_source_type": "Public-proxy concept",
            "used_in_demo_for": "Demo corridor map/ranking",
            "current_mode": "Synthetic demo records",
            "fallback_if_unavailable": "data/demo/demo_corridors.csv",
        },
        {
            "dataset": "Backtesting",
            "primary_source_type": "Synthetic",
            "used_in_demo_for": "Illustrative demo vs observed proxy illustration",
            "current_mode": "Synthetic demo backtesting data",
            "fallback_if_unavailable": "data/demo/demo_backtesting.csv",
        },
    ]
    return pd.DataFrame(rows)


def _prepare_risk_data(live_public_only: bool) -> pd.DataFrame:
    corridors = load_transmission_lines()
    weather = load_weather_cached(live_public_only)
    risk_df = load_demo_risk_table().copy()
    if weather.empty or "region" not in weather.columns or "weather_severity_score" not in weather.columns:
        weather_by_region = pd.DataFrame(columns=["region", "weather_severity_score", "weather_code"])
    else:
        if "weather_code" not in weather.columns:
            weather = weather.copy()
            weather["weather_code"] = "UNKNOWN"
        weather_by_region = weather.groupby("region", as_index=False).agg(
            weather_severity_score=("weather_severity_score", "mean"),
            weather_code=("weather_code", lambda s: s.mode().iat[0] if not s.mode().empty else "UNKNOWN"),
        )
    merged = risk_df.drop(columns=["weather_severity_score"], errors="ignore").merge(
        weather_by_region, on="region", how="left"
    )
    merged["weather_severity_score"] = merged["weather_severity_score"].fillna(45.0)
    merged["weather_code"] = merged["weather_code"].fillna("UNKNOWN")
    merged["risk_score"] = merged.apply(
        lambda row: calculate_demo_risk_score(
            weather_severity_score=row["weather_severity_score"],
            vegetation_exposure_score=row["vegetation_exposure_score"],
            public_outage_history_score=row["public_outage_history_score"],
            terrain_access_score=row["terrain_access_score"],
        ),
        axis=1,
    )
    merged["risk_level"] = merged["risk_score"].apply(assign_risk_level)
    merged["top_risk_driver"] = merged.apply(identify_top_risk_driver, axis=1)
    merged["suggested_review_action"] = merged.apply(
        lambda row: suggest_review_action(row["risk_level"], row["top_risk_driver"]),
        axis=1,
    )
    return merged.merge(
        corridors[["demo_corridor_id", "lat", "lon", "municipality"]],
        on="demo_corridor_id",
        how="left",
    )


def _summary_cards(risk_df: pd.DataFrame, outage_df: pd.DataFrame) -> None:
    high_count = int((risk_df["risk_level"] == "High").sum())
    outage_count = int(len(outage_df))
    customer_col = next(
        (
            col
            for col in ("customers_affected", "customersAffected", "numCustomersOut", "custA")
            if col in outage_df.columns
        ),
        None,
    )
    if customer_col is None:
        customers = 0
    else:
        customers = int(pd.to_numeric(outage_df[customer_col], errors="coerce").fillna(0).sum())
    expected_impact = "Illustrative estimate"
    cols = st.columns(6)
    cols[0].metric("Forecast window", "24–72 hours")
    cols[1].metric("High-risk demo corridors", high_count)
    cols[2].metric("Forecast confidence", "Demo only")
    cols[3].metric("Expected outage impact", expected_impact)
    cols[4].metric("Current public outage count", outage_count)
    cols[5].metric("Customers affected (public)", f"{customers:,}")


def _render_map_legend(*, show_weather_bubbles: bool, show_outage_markers: bool) -> None:
    """Legend matches map layers: filled disks for risk; blue outline for weather when shown."""
    swatches: list[str] = [
        '<div style="display:flex;align-items:center;gap:6px;margin-right:18px;">'
        '<span style="display:inline-block;width:16px;height:16px;border-radius:50%;'
        'background:rgb(220, 53, 69);opacity:0.9;border:1px solid rgba(0,0,0,0.2);"></span>'
        '<span style="font-size:0.9rem;">High risk</span></div>',
        '<div style="display:flex;align-items:center;gap:6px;margin-right:18px;">'
        '<span style="display:inline-block;width:16px;height:16px;border-radius:50%;'
        'background:rgb(255, 193, 7);opacity:0.9;border:1px solid rgba(0,0,0,0.2);"></span>'
        '<span style="font-size:0.9rem;">Medium risk</span></div>',
        '<div style="display:flex;align-items:center;gap:6px;margin-right:18px;">'
        '<span style="display:inline-block;width:16px;height:16px;border-radius:50%;'
        'background:rgb(40, 167, 69);opacity:0.9;border:1px solid rgba(0,0,0,0.2);"></span>'
        '<span style="font-size:0.9rem;">Low risk</span></div>',
    ]
    if show_weather_bubbles:
        swatches.append(
            '<div style="display:flex;align-items:center;gap:6px;margin-right:18px;">'
            '<span style="display:inline-block;width:16px;height:16px;border-radius:50%;'
            "border:3px solid rgb(52, 152, 219);background:transparent;box-sizing:border-box;"
            '"></span>'
            '<span style="font-size:0.9rem;">Regional weather context (when shown)</span></div>'
        )
    if show_outage_markers:
        swatches.append(
            '<div style="display:flex;align-items:center;gap:6px;margin-right:18px;">'
            '<span style="display:inline-block;width:16px;height:16px;border-radius:50%;'
            'background:rgb(80, 80, 80);opacity:0.75;border:1px solid rgba(0,0,0,0.2);"></span>'
            '<span style="font-size:0.9rem;">Public outage (region proxy)</span></div>'
        )
    cells = "".join(swatches)
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;margin:0.35rem 0 0.75rem 0;">'
        f"<strong>Legend</strong>&nbsp;&nbsp;{cells}</div>",
        unsafe_allow_html=True,
    )


def _risk_map_tab(risk_df: pd.DataFrame, outage_df: pd.DataFrame, weather_df: pd.DataFrame) -> None:
    st.subheader("Risk Map")
    map_density = st.radio(
        "Map markers",
        options=["One circle per demo corridor", "One circle per region (max risk)"],
        index=0,
        horizontal=True,
        help="Same region can have several demo corridors (e.g. Lower Mainland has two), each with its own marker. "
        "When enabled, regional weather appears as a blue outline ring under risk disks.",
    )
    basemap_choice = st.selectbox(
        "Basemap",
        options=["Light (Carto)", "OpenStreetMap", "No basemap"],
        index=0,
        help="Use a lighter basemap for presentation readability.",
    )
    if DEMO_OFFLINE_MODE:
        st.caption("Offline mode enabled: map renders risk overlays without internet basemap tiles.")
    else:
        st.caption("Online mode: choose a light basemap for clearer risk visualization.")
    mapped = risk_df.copy()
    mapped["color"] = mapped["risk_level"].apply(risk_color)

    show_weather_bubbles = True
    if map_density == "One circle per region (max risk)":
        idx = mapped.groupby("region")["risk_score"].idxmax()
        mapped = mapped.loc[idx].copy()
        mapped["demo_corridor_id"] = mapped["region"] + " (max risk)"
        mapped["color"] = mapped["risk_level"].apply(risk_color)
        # Avoid double stack: risk marker already encodes region; weather ring duplicates centroid.
        show_weather_bubbles = False

    corridor_layer = pdk.Layer(
        "ScatterplotLayer",
        data=mapped,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=8000,
        pickable=True,
    )

    layers: list[pdk.Layer] = []
    show_outage_markers = False

    if not DEMO_OFFLINE_MODE and basemap_choice != "No basemap":
        tile_url = (
            "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
            if basemap_choice == "Light (Carto)"
            else "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        layers.append(
            pdk.Layer(
                "TileLayer",
                data=tile_url,
                min_zoom=0,
                max_zoom=19,
                tile_size=256,
                opacity=1.0,
            ),
        )

    # Weather: outline-only ring, drawn *under* risk fills so colors do not blend into purple/mud.
    if (
        show_weather_bubbles
        and not weather_df.empty
        and {"region", "weather_severity_score"}.issubset(weather_df.columns)
    ):
        weather_centers = (
            mapped.groupby("region", as_index=False)[["lat", "lon"]].mean()
            .merge(
                weather_df.groupby("region", as_index=False)[
                    ["wind_gust_kmh", "precipitation_mm", "temperature_c", "weather_severity_score"]
                ].mean().merge(
                    weather_df.groupby("region", as_index=False).agg(
                        weather_code=("weather_code", lambda s: s.mode().iat[0] if not s.mode().empty else "UNKNOWN")
                    ),
                    on="region",
                    how="left",
                ),
                on="region",
                how="left",
            )
        )
        if not weather_centers.empty:
            risk_radius_m = 8000
            weather_centers["ring_radius"] = weather_centers["weather_severity_score"].fillna(0).apply(
                lambda s: int(risk_radius_m + 2200 + float(s) * 45)
            )
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=weather_centers,
                    get_position="[lon, lat]",
                    get_radius="ring_radius",
                    filled=False,
                    stroked=True,
                    get_line_color=[52, 152, 219, 240],
                    line_width_min_pixels=3,
                    pickable=False,
                )
            )

    if {"region", "municipality"}.issubset(outage_df.columns):
        region_centers = (
            mapped.groupby("region", as_index=False)[["lat", "lon"]].mean().rename(columns={"lat": "out_lat", "lon": "out_lon"})
        )
        outage_points = outage_df.merge(region_centers, on="region", how="left")
        if {"out_lat", "out_lon"}.issubset(outage_points.columns):
            outage_points = outage_points.dropna(subset=["out_lat", "out_lon"])
            if not outage_points.empty:
                show_outage_markers = True
                layers.append(
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=outage_points,
                        get_position="[out_lon, out_lat]",
                        get_fill_color=[80, 80, 80, 120],
                        get_radius=5000,
                        pickable=False,
                    )
                )

    layers.append(corridor_layer)

    st.info(
        "Map shows demo corridor risk by region using public/proxy data. "
        "It does not represent BC Hydro feeder-level topology."
    )
    _render_map_legend(
        show_weather_bubbles=show_weather_bubbles,
        show_outage_markers=show_outage_markers,
    )

    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(latitude=53.5, longitude=-124.5, zoom=4.5),
        layers=layers,
        tooltip={
            "text": (
                "Corridor: {demo_corridor_id}\nRisk: {risk_level}\nScore: {risk_score}\n"
                "Region: {region}\nWeather severity: {weather_severity_score}\nWeather code: {weather_code}"
            )
        },
    )
    st.pydeck_chart(deck, width="stretch")
    st.caption(
        "Colored disks = demo corridor risk (one per corridor, or one per region if aggregated). "
        "Blue ring = regional weather severity (outline only, under risk). "
        "Gray disks = public outage markers (under risk). "
        "Weather ring radius grows slightly with severity."
    )


tabs = st.tabs(["Overview", "Risk Dashboard", "Risk Map", "Backtesting", "Data Sources & Assumptions"])

with tabs[0]:
    st.markdown("### What this demo shows")
    st.markdown(
        """
        - **Concept workflow** — how vegetation, weather, and outage-proxy signals could inform a review queue
        - **Dashboard structure** — summary metrics, ranking, drivers, map, and a synthetic backtesting view
        - **Public/proxy data integration** — BC Hydro public outage feeds, unofficial snapshots, and open datasets as proxies
        - **Illustrative risk scoring** — transparent, weighted demo score (not a calibrated model)
        - **Example PoC outputs** — corridor-style markers and tables suitable for a discovery conversation
        """
    )
    st.markdown("### What this demo does not show")
    st.markdown(
        """
        - **Validated BC Hydro outage prediction** — this is a concept dashboard, not a forecast of outages
        - **Real feeder/circuit risk** — public transmission/corridor proxies are not distribution topology
        - **Internal vegetation treatment data** — treatment recency and patrol history are placeholders only
        - **Operational readiness** — no integration with control room, GIS asset systems, or crew dispatch
        - **Production deployment** — no SLAs, governance, or model lifecycle management
        """
    )
    st.success(
        "**Recommended next step** — Confirm a pilot region, identify data owners, and run a discovery workshop "
        "to validate data availability, joinability, and success criteria."
    )

with tabs[1]:
    st.subheader("Risk Dashboard")
    st.caption(
        "Summary uses live public feeds where available."
        if LIVE_PUBLIC_ONLY
        else "Summary may combine public feeds with local synthetic demo CSVs when feeds are unavailable."
    )
    weather_df = load_weather_cached(LIVE_PUBLIC_ONLY)
    risk_df = _prepare_risk_data(LIVE_PUBLIC_ONLY)
    outages_json_df = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    st.markdown("#### Storm risk summary")
    _summary_cards(risk_df, outages_json_df)

    st.markdown("#### Risk ranking")
    level_filter = st.multiselect(
        "Filter by risk level",
        ["High", "Medium", "Low"],
        default=["High", "Medium", "Low"],
    )
    ranking = risk_df[risk_df["risk_level"].isin(level_filter)].sort_values("risk_score", ascending=False)
    st.dataframe(
        ranking[
            [
                "demo_corridor_id",
                "region",
                "municipality",
                "risk_score",
                "risk_level",
                "top_risk_driver",
                "suggested_review_action",
            ]
        ],
        width="stretch",
    )

    st.markdown("#### Top risk drivers")
    st.plotly_chart(make_top_drivers_chart(risk_df), width="stretch")
    st.caption(
        "Treatment recency is a placeholder only — a formal PoC would use BC Hydro vegetation patrol and treatment history."
    )
    with st.expander("Show regional weather input data"):
        if weather_df.empty:
            st.info("No weather rows loaded in the current mode.")
        else:
            st.dataframe(weather_df, width="stretch")

with tabs[2]:
    weather_df = load_weather_cached(LIVE_PUBLIC_ONLY)
    risk_df = _prepare_risk_data(LIVE_PUBLIC_ONLY)
    outages_json_df = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    _risk_map_tab(risk_df, outages_json_df, weather_df)

with tabs[3]:
    st.subheader("Backtesting")
    st.warning("Synthetic demo backtesting only — not validated historical outage performance.")
    st.caption("All metrics and charts on this tab use synthetic demo records for illustration.")
    backtesting_df = load_backtesting_data()
    metrics = compute_backtesting_metrics(backtesting_df)
    cols = st.columns(3)
    cols[0].metric("Demo outages captured in top-risk areas", f"{metrics['capture_rate_pct']}%")
    cols[1].metric("Demo model vs weather-only baseline (synthetic)", metrics["demo_vs_baseline_delta"])
    cols[2].metric("Dataset", "Synthetic / demo")

    fig = px.scatter(
        backtesting_df,
        x="demo_model_score",
        y="observed_public_outage_count",
        color="region",
        size="weather_only_baseline_score",
        title="Demo model score vs synthetic observed outage counts (by region)",
    )
    st.plotly_chart(fig, width="stretch")
    with st.expander("Show synthetic backtesting input table"):
        st.dataframe(backtesting_df, width="stretch")

with tabs[4]:
    st.subheader("Data sources & assumptions")
    st.markdown(
        """
        **How to read this tab**

        - **Real public data** — BC Hydro public outage JSON/RSS; Environment Canada / MSC endpoints referenced for weather context.
        - **Unofficial public snapshot data** — third-party public outage archives (not BC Hydro–validated; illustrative proxy only).
        - **Proxy data** — public transmission/corridor geometry and land-cover–style vegetation exposure scores used as stand-ins for internal asset and ROW data.
        - **Synthetic data** — local CSVs under `data/demo/` so the concept dashboard runs when live feeds are unavailable.
        - **Formal PoC would require BC Hydro internal data** — outage history with validated causes, feeder/circuit topology, vegetation patrol and treatment records, asset condition, and operational telemetry for calibration and trust.
        """
    )
    st.dataframe(pd.DataFrame(DATA_SOURCES), width="stretch")
    st.subheader("Data provenance (real vs synthetic)")
    st.dataframe(_build_data_provenance_table(), width="stretch")
    st.subheader("Public/proxy vs internal data boundary")
    st.markdown(
        """
        - **Public/proxy data** supports concept demonstration and proxy-based ranking only.
        - **Internal BC Hydro data** is required for formal PoC calibration, validation, and any operational use.
        - **No production claim** should be made without validated internal BC Hydro data and governance.
        """
    )

    st.subheader("Assumptions and limitations")
    st.markdown(
        """
        - This app is an **illustrative prototype** — it illustrates a risk workflow, not outage timing or certainty.
        - Public outage feeds reflect **current/recent visibility**, not a complete historical archive.
        - Unofficial snapshot archives are **not BC Hydro–provided** and are not authoritative for history.
        - Corridor markers are **demo segments** — not distribution feeder topology from BC Hydro systems.
        - Vegetation exposure is a **proxy score** — not LiDAR, patrol, or treatment records.
        """
    )

    st.subheader("Live Source Checks (Optional)")
    if st.button("Run lightweight source checks"):
        rss_df = load_outages_rss_cached(LIVE_PUBLIC_ONLY)
        unofficial_df = load_unofficial_snapshots_cached(LIVE_PUBLIC_ONLY)
        st.write(f"RSS rows loaded: {len(rss_df)}")
        st.write(f"Unofficial snapshot rows loaded: {len(unofficial_df)}")
