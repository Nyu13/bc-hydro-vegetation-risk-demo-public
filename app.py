from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from src.backtesting import compute_backtesting_metrics, load_backtesting_data
from src.config import (
    BC_TRANSMISSION_GEOJSON,
    BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON,
    DEMO_DATA_DIR,
    DEMO_DATA_MODES,
    DEMO_OFFLINE_MODE,
    DEMO_PILOT_BC_HYDRO_REGION,
    DEMO_PILOT_MUNICIPALITY,
    DEMO_PILOT_TRANSMISSION_BBOX,
    DEMO_PRIMARY_DISCLAIMER,
    DEMO_REGION_OPTIONS,
    PLANET_POC_DISCLAIMER,
    SURREY_FREE_DATA_SUMMARY_CSV,
    SURREY_SENTINEL2_STATS_CSV,
    SURREY_WORLDCOVER_STATS_CSV,
)
from src.data_provenance import (
    DatasetProvenance,
    outage_marker_color,
    provenance_badge,
    provenance_from_frame,
    round_weather_display,
    style_synthetic_rows,
    synthetic_risk_fill,
    tag_dataframe,
)
from src.data_sources import DATA_SOURCES
from src.outage_loader import (
    live_outage_metrics,
    load_bchydro_outage_json,
    load_bchydro_rss,
    outage_has_polygon_row,
)
from src.region_history_loader import (
    load_municipality_outage_summary,
    load_region_outage_summary,
    select_display_columns,
)
from src.area_selection import (
    default_area_map_view_state,
    fit_area_map_view_state,
    jitter_duplicate_map_coordinates,
    load_region_map_context,
    lookup_municipality_coordinates,
    lookup_region_coordinates,
    bc_transmission_path_layer,
    pilot_area_map_view_state,
    prepare_municipality_hotspot_map_df,
    prepare_region_hotspot_map_df,
    promote_pilot_row,
    risk_map_pilot_view_state,
    selection_area_map_view_state,
)
from src.network_loader import (
    BC_TRANSMISSION_UI_LABEL,
    load_all_demo_corridors,
    load_transmission_lines,
)
from src.planet_loader import (
    PlanetLoadResult,
    load_planet_surrey_sample,
    planet_sample_enabled,
    planet_scores_from_row,
    validate_data_mode,
)
from src.risk_scoring import (
    assign_risk_level,
    calculate_corridor_exposure_score,
    calculate_demo_risk_score,
    calculate_public_outage_history_score,
    calculate_surrey_planet_risk_score,
    identify_top_risk_driver,
    suggest_review_action,
)
from src.theme_ui import apply_streamlit_theme
from src.visualization import apply_plotly_chart_theme, make_top_drivers_chart
from src.weather_loader import (
    WeatherLoadResult,
    demo_weather_csv_mtime,
    filter_weather_pilot_region,
    load_weather_demo,
)

HISTORICAL_ARCHIVE_THROUGH = "2026-05-19"
RISK_MAP_OUTAGE_DOT_RADIUS_PX = 8
RISK_MAP_OUTAGE_POLYGON_FILL_ALPHA = 45
RISK_MAP_OUTAGE_POLYGON_PICK_FILL_ALPHA = 35
RISK_MAP_OUTAGE_POLYGON_LINE_ALPHA = 220
RISK_MAP_OUTAGE_POINT_JITTER_M = 120.0
RISK_MAP_CORRIDOR_DOT_RADIUS_PX = 5


def _pydeck_tooltip(text_field: str = "tooltip_text") -> dict[str, str]:
    """deck.gl tooltip template; precompose multi-line text in a dataframe column."""
    return {"text": f"{{{text_field}}}"}


def _risk_map_outage_tooltip_lines(row: pd.Series, *, feed_label: str) -> str:
    lines: list[str] = []
    outage_id = row.get("outage_id", "")
    if outage_id is not None and str(outage_id).strip():
        lines.append(f"Outage: {outage_id}")
    if feed_label:
        lines.append(f"Source: {feed_label}")
    area = row.get("area") or row.get("area_text") or ""
    if area is not None and str(area).strip():
        lines.append(f"Area: {area}")
    for label, key in (
        ("Municipality", "municipality"),
        ("Customers", "customers_affected"),
        ("Cause", "cause"),
        ("Status", "status"),
        ("Updated", "updated"),
    ):
        value = row.get(key, row.get("timestamp", "")) if key == "updated" else row.get(key, "")
        if value is not None and str(value).strip():
            lines.append(f"{label}: {value}")
    if not any(line.startswith("Updated:") for line in lines):
        ts = row.get("timestamp", "")
        if ts is not None and str(ts).strip():
            lines.append(f"Updated: {ts}")
    return "\n".join(lines)


def _pilot_outage_dot_radius_px(point_count: int) -> int:
    if point_count <= 1:
        return 14
    if point_count <= 5:
        return 11
    if point_count <= 15:
        return 9
    return RISK_MAP_OUTAGE_DOT_RADIUS_PX


def _prepare_outage_map_points(outage_df: pd.DataFrame, *, feed_label: str) -> pd.DataFrame:
    """Point layer rows only (no polygon geometry); jitter duplicate coordinates for display."""
    if outage_df.empty:
        return outage_df
    frame = _outage_coords_frame(outage_df)
    point_rows = frame.loc[~frame.apply(outage_has_polygon_row, axis=1)]
    points = _outage_map_points(point_rows)
    if points.empty:
        return points
    # Only offset stacked centroid fallbacks; keep feed lat/lon exact for map accuracy.
    has_feed_lat = "latitude" in points.columns and points["latitude"].notna().any()
    all_feed_coords = has_feed_lat and points["latitude"].notna().all()
    if not all_feed_coords:
        points = jitter_duplicate_map_coordinates(
            points, lat_col="out_lat", lon_col="out_lon", jitter_m=RISK_MAP_OUTAGE_POINT_JITTER_M
        )
    elif len(points) > 1:
        points = jitter_duplicate_map_coordinates(
            points, lat_col="out_lat", lon_col="out_lon", jitter_m=RISK_MAP_OUTAGE_POINT_JITTER_M
        )
    points = points.copy()
    points["tooltip_text"] = points.apply(
        lambda row: _risk_map_outage_tooltip_lines(row, feed_label=feed_label),
        axis=1,
    )
    return points


def _risk_map_view_coordinates(
    *,
    mapped: pd.DataFrame,
    show_corridor_markers: bool,
    json_points: pd.DataFrame,
    rss_points: pd.DataFrame,
    json_polygons: list[dict],
) -> tuple[list[float], list[float]]:
    lats: list[float] = []
    lons: list[float] = []

    def _add(lat: object, lon: object) -> None:
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            return
        lats.append(lat_f)
        lons.append(lon_f)

    if show_corridor_markers and not mapped.empty:
        for _, row in mapped.iterrows():
            _add(row.get("lat"), row.get("lon"))
    for points in (json_points, rss_points):
        if points.empty:
            continue
        for _, row in points.iterrows():
            _add(row.get("out_lat"), row.get("out_lon"))
    for feature in json_polygons:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            continue
        coords = geometry.get("coordinates")
        gtype = geometry.get("type")
        flat: list[tuple[float, float]] = []

        def _walk(values: object) -> None:
            if not isinstance(values, list) or not values:
                return
            if isinstance(values[0], (int, float)):
                for i in range(0, len(values) - 1, 2):
                    if i + 1 < len(values):
                        flat.append((float(values[i + 1]), float(values[i])))
                return
            if len(values) >= 2 and all(isinstance(v, (int, float)) for v in values[:2]):
                flat.append((float(values[1]), float(values[0])))
                return
            for item in values:
                _walk(item)

        if gtype in {"Polygon", "MultiPolygon"}:
            _walk(coords)
        for lat, lon in flat:
            _add(lat, lon)
    return lats, lons


def _risk_map_corridor_tooltip_lines(row: pd.Series) -> str:
    risk_level = str(row.get("risk_level", "") or "")
    risk_score = row.get("risk_score", "")
    risk_line = f"Risk: {risk_level}"
    if risk_score is not None and str(risk_score).strip() and pd.notna(risk_score):
        risk_line += f" ({risk_score})"
    lines = [
        f"Corridor: {row.get('demo_corridor_id', '')}",
        risk_line,
        f"Region: {row.get('region', '')}",
        f"Municipality: {row.get('municipality', '')}",
    ]
    if pd.notna(row.get("weather_severity_score")):
        lines.append(f"Weather severity: {row.get('weather_severity_score')}")
    if row.get("live_outage_density_applied") and pd.notna(row.get("public_outage_history_score")):
        lines.append(f"Outage density (Surrey live): {row.get('public_outage_history_score')}")
    top_driver = row.get("top_risk_driver")
    if top_driver:
        lines.append(f"Top driver: {top_driver}")
    if row.get("weather_code"):
        lines.append(f"Weather code: {row.get('weather_code')}")
    return "\n".join(line for line in lines if line.split(": ", 1)[-1].strip())


st.set_page_config(
    page_title="BC Hydro Vegetation-Weather Outage Risk Demo",
    layout="wide",
)

if "ui_theme_radio" not in st.session_state:
    st.session_state.ui_theme_radio = "Light"

if "area_selection_default_view" not in st.session_state:
    st.session_state.area_selection_default_view = "Municipality (top hotspots)"

if "data_refresh_nonce" not in st.session_state:
    st.session_state.data_refresh_nonce = 0

if "demo_region" not in st.session_state:
    st.session_state.demo_region = DEMO_REGION_OPTIONS[0]

if "demo_data_mode" not in st.session_state:
    st.session_state.demo_data_mode = DEMO_DATA_MODES[0]

if "planet_disclaimer_shown" not in st.session_state:
    st.session_state.planet_disclaimer_shown = False

with st.sidebar:
    st.markdown("### Appearance")
    st.radio(
        "Display theme",
        ["Light", "Dark"],
        horizontal=True,
        key="ui_theme_radio",
    )
    st.markdown("### PoC pilot")
    st.selectbox(
        "Demo region",
        DEMO_REGION_OPTIONS,
        key="demo_region",
    )
    st.selectbox(
        "Data mode",
        DEMO_DATA_MODES,
        key="demo_data_mode",
        help=(
            "Public/proxy only — standard demo scoring without Planet layers. "
            "Planet sample enabled — Surrey formula with Planet placeholder CSV. "
            "Synthetic fallback — bundled demo CSVs; Planet sample not loaded."
        ),
    )

apply_streamlit_theme(st.session_state.ui_theme_radio)
_chart_dark = st.session_state.ui_theme_radio == "Dark"
DEMO_DATA_MODE = validate_data_mode(st.session_state.demo_data_mode)
PLANET_SAMPLE = load_planet_surrey_sample(DEMO_DATA_MODE)
SURREY_PLANET_ACTIVE = planet_sample_enabled(DEMO_DATA_MODE) and PLANET_SAMPLE.status in {
    "placeholder",
    "loaded",
}


def _show_planet_disclaimer_once() -> None:
    if st.session_state.planet_disclaimer_shown:
        return
    st.info(PLANET_POC_DISCLAIMER)
    st.session_state.planet_disclaimer_shown = True


def _planet_sample_status_label() -> str:
    return PLANET_SAMPLE.status


def _surrey_municipality_outage_row() -> pd.Series | None:
    mun_df, _ = load_municipality_outage_summary()
    if mun_df.empty or "municipality" not in mun_df.columns:
        return None
    match = mun_df.loc[mun_df["municipality"].astype(str).str.casefold() == DEMO_PILOT_MUNICIPALITY.casefold()]
    if match.empty:
        return None
    return match.iloc[0]

st.title("BC Hydro Vegetation-Weather Outage Risk Demo")
st.warning(DEMO_PRIMARY_DISCLAIMER)
if DEMO_OFFLINE_MODE:
    st.caption("Offline mode — bundled demo CSVs.")


@st.cache_data(show_spinner=False)
def load_demo_risk_table() -> pd.DataFrame:
    return tag_dataframe(
        pd.read_csv(DEMO_DATA_DIR / "demo_risk_scores.csv"),
        is_synthetic=True,
        source="demo_risk_scores.csv (no public live risk feed)",
    )


def _weather_number_column_config(df: pd.DataFrame) -> dict:
    """Streamlit still shows float64 as 4.000000 unless format is set."""
    config: dict = {}
    for col in (
        "wind_gust_kmh",
        "precipitation_mm",
        "temperature_c",
        "weather_severity_score",
    ):
        if col in df.columns:
            config[col] = st.column_config.NumberColumn(format="%.1f")
    return config


def _show_weather_dataframe(
    df: pd.DataFrame,
    *,
    width: str = "stretch",
    height: int | None = None,
    **dataframe_kwargs,
) -> None:
    """Weather input tables: round metrics, Styler one-decimal format, NumberColumn fallback."""
    _show_dataframe_with_provenance(
        df,
        width=width,
        height=height,
        column_config=_weather_number_column_config(df),
        **dataframe_kwargs,
    )


def _render_outage_provenance_alerts(*provs: DatasetProvenance) -> None:
    """Surface fetch/fallback/TLS reasons when outage feeds are not live."""
    for prov in provs:
        if prov.is_synthetic and "demo fallback because" in prov.detail.lower():
            st.warning(prov.detail.split("  \n", 1)[0])
        elif prov.badge == "🔴 Unavailable":
            st.warning(prov.detail)
        elif "TLS verify relaxed" in prov.detail:
            st.info(prov.detail.split("  \n", 1)[0])


def _show_dataframe_with_provenance(
    df: pd.DataFrame,
    *,
    width: str = "stretch",
    height: int | None = None,
    column_config: dict | None = None,
    columns: list[str] | None = None,
    alt_highlight: bool = False,
    **dataframe_kwargs,
) -> None:
    """Render table with amber/pink row highlight for synthetic provenance."""
    if df.empty:
        st.info("No rows to display.")
        return
    table_df = round_weather_display(df)
    styled = style_synthetic_rows(table_df, alt=alt_highlight, columns=columns)
    kwargs = {"width": width, **dataframe_kwargs}
    if height is not None:
        kwargs["height"] = height
    merged_config = {**_weather_number_column_config(table_df), **(column_config or {})}
    if merged_config:
        kwargs["column_config"] = merged_config
    st.dataframe(styled, **kwargs)
    if "is_synthetic" in df.columns and bool(df["is_synthetic"].any()):
        st.caption("🟡 Highlighted rows = demo/synthetic data.")


@st.cache_data(show_spinner=False)
def load_outages_json_cached(live_public_only: bool) -> pd.DataFrame:
    return load_bchydro_outage_json(allow_synthetic_fallback=not live_public_only)


@st.cache_data(show_spinner=False)
def load_outages_rss_cached(live_public_only: bool) -> pd.DataFrame:
    return load_bchydro_rss(allow_synthetic_fallback=not live_public_only)


@st.cache_data(show_spinner=False)
def load_weather_cached(
    live_public_only: bool,
    refresh_nonce: int,
    demo_weather_mtime: float,
) -> WeatherLoadResult:
    return load_weather_demo(allow_synthetic_fallback=not live_public_only)


def _load_weather() -> WeatherLoadResult:
    return load_weather_cached(
        LIVE_PUBLIC_ONLY,
        st.session_state.data_refresh_nonce,
        demo_weather_csv_mtime(),
    )


with st.sidebar:
    st.markdown("### Live data")
    LIVE_PUBLIC_ONLY = st.toggle("Live public only", value=False)
    if st.button("Refresh live data"):
        st.session_state.data_refresh_nonce += 1
        load_outages_json_cached.clear()
        load_outages_rss_cached.clear()
        load_weather_cached.clear()
        st.rerun()


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
            "used_in_demo_for": "Current outages (live) — Risk Dashboard & Risk Map (map JSON)",
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
            "dataset": "Corridor geometry / risk scores",
            "primary_source_type": "Synthetic (no public live feed)",
            "used_in_demo_for": "Demo corridor map/ranking",
            "current_mode": "Always synthetic — labeled 🟡 in UI",
            "fallback_if_unavailable": "data/demo/demo_corridors.csv, demo_risk_scores.csv",
        },
        {
            "dataset": "BC transmission lines (optional overlay)",
            "primary_source_type": "Public — BC Geographic Warehouse / Geo.ca",
            "used_in_demo_for": "Optional PathLayer — HV reference underlay (Lower Mainland WFS export when present)",
            "current_mode": "data/processed/bc_transmission_lines_lower_mainland.geojson, else bundled sample",
            "fallback_if_unavailable": "data/demo/demo_bc_transmission_lines_sample.geojson",
        },
        {
            "dataset": "Backtesting",
            "primary_source_type": "Synthetic (no public live feed)",
            "used_in_demo_for": "Illustrative demo vs observed proxy illustration",
            "current_mode": "Always synthetic — labeled 🟡 in UI",
            "fallback_if_unavailable": "data/demo/demo_backtesting.csv",
        },
        {
            "dataset": "Municipality population (2021 Census)",
            "primary_source_type": "Public (Statistics Canada, bundled subset)",
            "used_in_demo_for": "Area selection map — population outline rings (context only)",
            "current_mode": "Bundled demo CSV",
            "fallback_if_unavailable": "data/demo/demo_municipality_population.csv",
        },
        {
            "dataset": "Region outage summary (unofficial archive)",
            "primary_source_type": "Public proxy (unofficial snapshots)",
            "used_in_demo_for": "Area selection — region hotspot ranking",
            "current_mode": "Bundled demo snapshot or data/processed/region_summary.csv",
            "fallback_if_unavailable": "data/demo/demo_region_outage_summary.csv",
        },
        {
            "dataset": "Municipality outage summary (unofficial archive)",
            "primary_source_type": "Public proxy (unofficial snapshots)",
            "used_in_demo_for": "Area selection — municipality hotspot ranking",
            "current_mode": "Bundled demo snapshot or data/processed/municipality_summary.csv",
            "fallback_if_unavailable": "data/demo/demo_municipality_outage_summary.csv",
        },
        {
            "dataset": "Region map context (centroids + approx. population)",
            "primary_source_type": "Demo aggregate (Census-inspired approximations)",
            "used_in_demo_for": "Area selection map — population outline rings",
            "current_mode": "Bundled demo CSV",
            "fallback_if_unavailable": "data/demo/demo_region_map_context.csv",
        },
        {
            "dataset": "Planet Surrey sample (placeholder)",
            "primary_source_type": "Placeholder remote-sensing proxy",
            "used_in_demo_for": "Surrey PoC vegetation / canopy / drought stress scores",
            "current_mode": (
                f"{DEMO_DATA_MODE} — Planet sample: {_planet_sample_status_label()}"
            ),
            "fallback_if_unavailable": "Corridor exposure from demo_corridors.csv (synthetic)",
        },
    ]
    return pd.DataFrame(rows)


def _prepare_risk_data(
    live_public_only: bool,
    *,
    pilot_scope: bool = True,
    pilot_outages: pd.DataFrame | None = None,
    data_mode: str | None = None,
) -> pd.DataFrame:
    mode = validate_data_mode(data_mode or DEMO_DATA_MODE)
    planet_result = load_planet_surrey_sample(mode)
    use_planet_formula = planet_sample_enabled(mode) and planet_result.status in {
        "placeholder",
        "loaded",
    }

    corridors = load_transmission_lines(pilot_scope=pilot_scope)
    weather = load_weather_cached(
        live_public_only,
        st.session_state.data_refresh_nonce,
        demo_weather_csv_mtime(),
    ).df
    risk_df = load_demo_risk_table().copy()
    if pilot_scope and not corridors.empty and "demo_corridor_id" in corridors.columns:
        pilot_ids = set(corridors["demo_corridor_id"])
        risk_df = risk_df.loc[risk_df["demo_corridor_id"].isin(pilot_ids)]
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

    corridor_attrs = corridors[
        [
            c
            for c in (
                "demo_corridor_id",
                "lat",
                "lon",
                "municipality",
                "forest_exposure_score",
                "historical_outage_proxy_score",
                "overhead_length_km",
            )
            if c in corridors.columns
        ]
    ].copy()
    if "terrain_access_score" in corridors.columns:
        corridor_attrs["corridor_terrain_access_score"] = corridors["terrain_access_score"].values
    if not corridor_attrs.empty and "demo_corridor_id" in corridor_attrs.columns:
        merged = merged.merge(corridor_attrs, on="demo_corridor_id", how="left")

    mun_row = _surrey_municipality_outage_row()
    mun_priority = float(mun_row["suggested_priority_score"]) if mun_row is not None else None
    metrics = live_outage_metrics(pilot_outages) if pilot_outages is not None else {"count": 0, "customers": 0}
    outage_score, outage_source = calculate_public_outage_history_score(
        outage_count=metrics["count"],
        customers_affected=metrics["customers"],
        municipality_priority_score=mun_priority,
        prefer_live=pilot_outages is not None,
    )
    merged["live_outage_density_applied"] = outage_source == "live_density"
    merged["public_outage_history_score"] = outage_score

    planet_scores = planet_scores_from_row(planet_result.row if use_planet_formula else None)
    merged["surrey_planet_formula_applied"] = use_planet_formula
    merged["planet_sample_status"] = planet_result.status
    merged["vegetation_dryness_score"] = planet_scores["vegetation_dryness_score"]
    merged["canopy_exposure_score"] = planet_scores["canopy_exposure_score"]
    merged["heat_drought_stress_score"] = planet_scores["heat_drought_stress_score"]

    def _vegetation_exposure_row(row: pd.Series) -> float:
        if use_planet_formula:
            return planet_scores["vegetation_exposure_score"]
        if pd.notna(row.get("forest_exposure_score")) and pd.notna(row.get("historical_outage_proxy_score")):
            return calculate_corridor_exposure_score(
                float(row["forest_exposure_score"]),
                float(row["historical_outage_proxy_score"]),
                float(row.get("overhead_length_km") or 0.0),
            )
        return float(row.get("vegetation_exposure_score", 50.0))

    merged["vegetation_exposure_score"] = merged.apply(_vegetation_exposure_row, axis=1)
    if "corridor_terrain_access_score" in merged.columns:
        merged["terrain_access_score"] = merged["corridor_terrain_access_score"].fillna(
            merged["terrain_access_score"]
        )

    def _risk_score_row(row: pd.Series) -> float:
        if row.get("surrey_planet_formula_applied"):
            return calculate_surrey_planet_risk_score(
                weather_severity_score=row["weather_severity_score"],
                vegetation_exposure_score=row["vegetation_exposure_score"],
                vegetation_dryness_score=row["vegetation_dryness_score"],
                public_outage_history_score=row["public_outage_history_score"],
                terrain_access_score=row["terrain_access_score"],
            )
        return calculate_demo_risk_score(
            weather_severity_score=row["weather_severity_score"],
            vegetation_exposure_score=row["vegetation_exposure_score"],
            public_outage_history_score=row["public_outage_history_score"],
            terrain_access_score=row["terrain_access_score"],
        )

    merged["risk_score"] = merged.apply(_risk_score_row, axis=1)
    merged["risk_level"] = merged["risk_score"].apply(assign_risk_level)
    merged["top_risk_driver"] = merged.apply(identify_top_risk_driver, axis=1)
    merged["suggested_review_action"] = merged.apply(
        lambda row: suggest_review_action(row["risk_level"], row["top_risk_driver"]),
        axis=1,
    )
    if use_planet_formula:
        source = (
            "Surrey PoC: Planet sample + live weather + "
            f"{'Surrey live outage density' if merged['live_outage_density_applied'].any() else 'municipality outage proxy'}"
        )
    elif merged["live_outage_density_applied"].any():
        source = (
            "PoC composite: live weather + Surrey map JSON outage density; "
            "corridor/terrain from demo_corridors.csv (synthetic)"
        )
    else:
        source = "demo_risk_scores.csv + demo corridors (synthetic; weather may be live)"
    return tag_dataframe(
        merged,
        is_synthetic=True,
        source=source,
    )


def _summary_cards(
    risk_df: pd.DataFrame,
    pilot_outages: pd.DataFrame,
) -> None:
    high_count = int((risk_df["risk_level"] == "High").sum())
    metrics = live_outage_metrics(pilot_outages)
    outage_count = metrics["count"]
    customers = metrics["customers"]
    row1 = st.columns(3)
    row1[0].metric(
        "Forecast window",
        "24–72 h",
        help="Demo forecast horizon (hours).",
    )
    row1[1].metric(
        "High-risk corridors",
        high_count,
        help="Demo corridors scored High in the illustrative model.",
    )
    row1[2].metric(
        "Confidence",
        "Demo",
        help="Illustrative scoring only—not a calibrated forecast model.",
    )
    row2 = st.columns(3)
    row2[0].metric(
        "Outage impact",
        "Illustrative",
        help="Illustrative expected-impact placeholder—not an outage forecast.",
    )
    row2[1].metric(
        "Public outages",
        outage_count,
        help=f"Current count from BC Hydro map JSON in the {DEMO_PILOT_MUNICIPALITY} pilot slice.",
    )
    row2[2].metric(
        "Customers affected",
        f"{customers:,}",
        help="Customers affected per public outage feeds (when reported).",
    )


def _render_live_outages_section(
    outages_json_df: pd.DataFrame,
    *,
    json_provenance: DatasetProvenance,
) -> None:
    st.markdown("#### Current outages (live)")
    _render_outage_provenance_alerts(json_provenance)
    show_feed_details = (
        json_provenance.is_synthetic
        or json_provenance.badge == "🔴 Unavailable"
    )
    if show_feed_details:
        with st.expander("Outage feed status", expanded=True):
            st.markdown(json_provenance.caption)
    pilot_outages = _filter_outages_for_risk_map(outages_json_df)
    province_count = len(outages_json_df)
    pilot_count = len(pilot_outages)
    if outages_json_df.empty:
        st.info(
            "No outage JSON rows. "
            + (
                "Live public only is on — no rows loaded. Disable the sidebar toggle for demo CSV fallback, "
                "or use **Refresh live data** after fixing network/TLS."
                if LIVE_PUBLIC_ONLY
                else "Enable fallback (turn off Live public only) or check network/TLS."
            )
        )
        return
    row_label = "row" if province_count == 1 else "rows"
    st.caption(f"All regions — map JSON ({province_count} {row_label})")
    _show_dataframe_with_provenance(outages_json_df)
    if pilot_count > 0:
        pilot_row_label = "row" if pilot_count == 1 else "rows"
        with st.expander(
            f"{DEMO_PILOT_MUNICIPALITY} — map JSON ({pilot_count} of {province_count} {pilot_row_label})",
            expanded=False,
        ):
            _show_dataframe_with_provenance(pilot_outages)
    else:
        st.caption(
            f"No {DEMO_PILOT_MUNICIPALITY} rows in the current map JSON feed "
            f"({province_count} province-wide)."
        )


def _area_selection_column_config() -> dict:
    return {
        "unique_outages": st.column_config.NumberColumn(
            "Unique outages",
            help="Distinct outage_ids in the unofficial archive (not a sum of snapshot rows).",
            format="%.0f",
        ),
        "avg_customers_per_unique_outage": st.column_config.NumberColumn(
            "Avg customers per unique outage",
            help="Mean of peak num_customers_out per outage_id (max across snapshot rows).",
            format="%.0f",
        ),
        "tree_related_outage_count": st.column_config.NumberColumn(
            "Tree-related outages",
            help="Unique outages with tree/vegetation cause on any snapshot row.",
            format="%.0f",
        ),
        "weather_related_outage_count": st.column_config.NumberColumn(
            "Weather-related outages",
            help="Unique outages with weather cause on any snapshot row.",
            format="%.0f",
        ),
        "suggested_priority_score": st.column_config.NumberColumn(
            "Priority score",
            help="Weighted score from unique-outage metrics only (see extractor README).",
            format="%.3f",
        ),
    }


def _outage_coords_frame(outage_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize lat/lon columns for pilot bbox filtering (may still have NaNs)."""
    if outage_df.empty:
        return outage_df
    frame = outage_df.copy()
    if not {"out_lat", "out_lon"}.issubset(frame.columns):
        if {"latitude", "longitude"}.issubset(frame.columns):
            frame["out_lat"] = pd.to_numeric(frame["latitude"], errors="coerce")
            frame["out_lon"] = pd.to_numeric(frame["longitude"], errors="coerce")
        else:
            frame["out_lat"] = pd.NA
            frame["out_lon"] = pd.NA
    else:
        frame["out_lat"] = pd.to_numeric(frame["out_lat"], errors="coerce")
        frame["out_lon"] = pd.to_numeric(frame["out_lon"], errors="coerce")
    return frame


def _outage_geometry_in_pilot_bbox(feature: object) -> bool:
    """True when any polygon vertex lies inside DEMO_PILOT_TRANSMISSION_BBOX."""
    if not isinstance(feature, dict):
        return False
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        return False
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    min_lon, min_lat, max_lon, max_lat = DEMO_PILOT_TRANSMISSION_BBOX
    points: list[tuple[float, float]] = []

    def _collect_pairs(values: object) -> None:
        if not isinstance(values, list):
            return
        if len(values) >= 2 and all(isinstance(v, (int, float)) for v in values[:2]):
            points.append((float(values[0]), float(values[1])))
            return
        for item in values:
            _collect_pairs(item)

    if gtype in {"Polygon", "MultiPolygon"} and isinstance(coords, list):
        _collect_pairs(coords)
    if not points:
        return False
    for lon, lat in points:
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return True
    return False


def _filter_outages_for_risk_map(outage_df: pd.DataFrame) -> pd.DataFrame:
    """
    Risk Map scope: Surrey only (DEMO_PILOT_MUNICIPALITY).
    Rows with a municipality label must match Surrey (case-insensitive).
    Rows without a municipality use pilot bbox on coordinates or polygon geometry.
    """
    if outage_df.empty:
        return outage_df
    frame = _outage_coords_frame(outage_df)
    min_lon, min_lat, max_lon, max_lat = DEMO_PILOT_TRANSMISSION_BBOX
    pilot_mun = DEMO_PILOT_MUNICIPALITY.casefold()
    keep_idx: list[Any] = []
    for idx, row in frame.iterrows():
        mun_text = str(row.get("municipality", "") or "").strip()
        if mun_text:
            if mun_text.casefold() != pilot_mun:
                continue
            keep_idx.append(idx)
            continue
        lat = row.get("out_lat")
        lon = row.get("out_lon")
        if pd.notna(lat) and pd.notna(lon):
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                lat_f = lon_f = float("nan")
            if min_lon <= lon_f <= max_lon and min_lat <= lat_f <= max_lat:
                keep_idx.append(idx)
                continue
        if "outage_geojson" in frame.columns and _outage_geometry_in_pilot_bbox(row.get("outage_geojson")):
            keep_idx.append(idx)
    return frame.loc[keep_idx].copy()


def _outage_map_points(outage_df: pd.DataFrame) -> pd.DataFrame:
    if outage_df.empty:
        return outage_df
    points = outage_df.copy()
    if {"out_lat", "out_lon"}.issubset(points.columns):
        points = points.dropna(subset=["out_lat", "out_lon"])
        return points
    if {"latitude", "longitude"}.issubset(points.columns):
        points["out_lat"] = pd.to_numeric(points["latitude"], errors="coerce")
        points["out_lon"] = pd.to_numeric(points["longitude"], errors="coerce")
        return points.dropna(subset=["out_lat", "out_lon"])
    if {"region", "municipality"}.issubset(points.columns):
        region_centers = load_region_map_context()
        if not region_centers.empty:
            points = points.merge(
                region_centers.rename(columns={"region_name": "region", "lat": "out_lat", "lon": "out_lon"}),
                on="region",
                how="left",
            )
            return points.dropna(subset=["out_lat", "out_lon"])
    return pd.DataFrame()


def _outage_polygon_features(outage_df: pd.DataFrame, *, feed_label: str = "BC Hydro JSON") -> list[dict]:
    if outage_df.empty or "outage_geojson" not in outage_df.columns:
        return []
    features: list[dict] = []
    for _, row in outage_df.iterrows():
        if "outage_has_polygon" in outage_df.columns and not bool(row.get("outage_has_polygon")):
            continue
        feature = row.get("outage_geojson")
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        props = dict(feature.get("properties") or {})
        props.setdefault("outage_id", str(row.get("outage_id", "")))
        props.setdefault("region", str(row.get("region", "")))
        props.setdefault("municipality", str(row.get("municipality", "")))
        props.setdefault("status", str(row.get("status", "")))
        props.setdefault("cause", str(row.get("cause", "")))
        props.setdefault("updated", str(row.get("updated", row.get("timestamp", ""))))
        props.setdefault(
            "customers_affected",
            int(pd.to_numeric(row.get("customers_affected", 0), errors="coerce") or 0),
        )
        props["tooltip_text"] = _risk_map_outage_tooltip_lines(row, feed_label=feed_label)
        features.append({"type": "Feature", "geometry": geometry, "properties": props})
    return features


def _risk_map_tab(
    risk_df: pd.DataFrame,
    outages_json_df: pd.DataFrame,
    *,
    json_provenance: DatasetProvenance,
) -> None:
    st.subheader("Risk Map")
    if json_provenance.is_synthetic or json_provenance.badge == "🔴 Unavailable":
        _render_outage_provenance_alerts(json_provenance)
    json_before = len(outages_json_df)
    map_outages = _filter_outages_for_risk_map(outages_json_df)
    map_after = len(map_outages)
    map_feed_label = "BC Hydro JSON"
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        show_bc_lines = st.checkbox(BC_TRANSMISSION_UI_LABEL, value=False)
    with ctrl2:
        show_corridor_markers = st.checkbox("Corridor risk markers", value=False)
    with ctrl3:
        outage_outline_only = st.checkbox("Outline-only polygons", value=True)
    outage_geometry_mode = st.selectbox(
        "Outage geometry",
        options=["Both", "Polygons only", "Points only"],
        index=0,
    )
    mapped = risk_df.copy()
    if "region" in mapped.columns:
        mapped = mapped[mapped["region"] == DEMO_PILOT_BC_HYDRO_REGION]
    if "municipality" in mapped.columns:
        mapped = mapped[mapped["municipality"] == DEMO_PILOT_MUNICIPALITY]
    if mapped.empty:
        st.warning(
            f"No demo corridors in the pilot ({DEMO_PILOT_MUNICIPALITY}, {DEMO_PILOT_BC_HYDRO_REGION}). "
            "Check bundled demo_corridors.csv."
        )
        return
    mapped["color"] = mapped["risk_level"].apply(synthetic_risk_fill)
    mapped["tooltip_text"] = mapped.apply(_risk_map_corridor_tooltip_lines, axis=1)

    corridor_layer = pdk.Layer(
        "ScatterplotLayer",
        data=mapped,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=RISK_MAP_CORRIDOR_DOT_RADIUS_PX,
        radius_units="pixels",
        radius_min_pixels=RISK_MAP_CORRIDOR_DOT_RADIUS_PX,
        radius_max_pixels=RISK_MAP_CORRIDOR_DOT_RADIUS_PX,
        pickable=True,
        tooltip=_pydeck_tooltip(),
    )

    layers: list[pdk.Layer] = []

    if show_bc_lines:
        bc_layer = bc_transmission_path_layer(clip_to_pilot_bbox=True)
        if bc_layer is not None:
            layers.append(bc_layer)

    show_polygons = outage_geometry_mode in {"Both", "Polygons only"}
    show_points = outage_geometry_mode in {"Both", "Points only"}

    if map_outages.empty:
        st.warning("No Surrey outages in the current feed.")

    json_polygons = _outage_polygon_features(map_outages, feed_label=map_feed_label)
    if show_polygons and json_polygons:
        poly_color = outage_marker_color(json_provenance.is_synthetic)
        polygon_fill_alpha = (
            RISK_MAP_OUTAGE_POLYGON_PICK_FILL_ALPHA
            if outage_outline_only
            else RISK_MAP_OUTAGE_POLYGON_FILL_ALPHA
        )
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": json_polygons},
                filled=True,
                stroked=True,
                get_fill_color=[poly_color[0], poly_color[1], poly_color[2], polygon_fill_alpha],
                get_line_color=[poly_color[0], poly_color[1], poly_color[2], RISK_MAP_OUTAGE_POLYGON_LINE_ALPHA],
                line_width_min_pixels=3,
                auto_highlight=True,
                pickable=True,
                tooltip=_pydeck_tooltip(),
            )
        )

    map_points = (
        _prepare_outage_map_points(map_outages, feed_label=map_feed_label) if show_points else pd.DataFrame()
    )
    pilot_point_count = len(map_points)
    outage_dot_radius = _pilot_outage_dot_radius_px(pilot_point_count)

    if show_points and not map_points.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=map_points,
                get_position="[out_lon, out_lat]",
                get_fill_color=outage_marker_color(json_provenance.is_synthetic),
                get_radius=outage_dot_radius,
                radius_units="pixels",
                radius_min_pixels=outage_dot_radius,
                radius_max_pixels=outage_dot_radius,
                auto_highlight=True,
                pickable=True,
                tooltip=_pydeck_tooltip(),
            )
        )
    if show_corridor_markers:
        layers.append(corridor_layer)

    view_lats, view_lons = _risk_map_view_coordinates(
        mapped=mapped,
        show_corridor_markers=show_corridor_markers,
        json_points=map_points,
        rss_points=pd.DataFrame(),
        json_polygons=json_polygons if show_polygons else [],
    )
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=risk_map_pilot_view_state(lats=view_lats, lons=view_lons),
        layers=layers,
        tooltip=_pydeck_tooltip(),
    )
    st.pydeck_chart(deck, width="stretch")
    st.caption(f"{DEMO_PILOT_MUNICIPALITY}: {map_after}/{json_before} live JSON rows · hover for details")


def _area_hotspot_map_layers(map_df: pd.DataFrame, *, municipality: bool) -> list[pdk.Layer]:
    del municipality  # same layer stack; tooltip_text precomposed on map_df
    return [
        pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_fill_color="outage_color",
            get_radius="outage_radius_m",
            pickable=True,
            tooltip=_pydeck_tooltip(),
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_radius="population_radius_m",
            filled=False,
            stroked=True,
            get_line_color=[40, 167, 69, 220],
            line_width_min_pixels=3,
            pickable=False,
        ),
    ]


def _area_selection_tab() -> None:
    st.subheader("Area selection (PoC)")
    region_df, region_source = load_region_outage_summary()
    mun_df, mun_source = load_municipality_outage_summary()

    archive_range = "public archive proxy"
    if not region_df.empty and {
        "first_snapshot_date",
        "last_snapshot_date",
    } <= set(region_df.columns):
        start = region_df["first_snapshot_date"].min()
        end = region_df["last_snapshot_date"].max()
        archive_range = f"{start} to {end}, public archive proxy"

    st.warning(
        f"**Historical archive (not live)** — unofficial proxy ({archive_range}) through "
        f"**{HISTORICAL_ARCHIVE_THROUGH}**. Current outages: **Risk Dashboard** / **Risk Map**."
    )

    view = st.radio(
        "Rank by",
        ["BC Hydro region", "Municipality (top hotspots)"],
        horizontal=True,
        key="area_selection_default_view",
    )
    is_region_view = view == "BC Hydro region"
    ranked = pd.DataFrame()
    display_cols: list[str] = []
    table_source = region_source if is_region_view else mun_source

    if is_region_view:
        if not region_df.empty:
            display_cols = select_display_columns(region_df, municipality=False)
            ranked = promote_pilot_row(
                region_df.sort_values("unique_outages", ascending=False),
                municipality=False,
            )
    elif not mun_df.empty:
        display_cols = select_display_columns(mun_df, municipality=True)
        pilot_mun = mun_df
        if "region_name" in mun_df.columns:
            pilot_mun = mun_df.loc[mun_df["region_name"] == DEMO_PILOT_BC_HYDRO_REGION]
        ranked = promote_pilot_row(
            pilot_mun.sort_values("unique_outages", ascending=False).head(25),
            municipality=True,
        )

    col_table, col_map = st.columns([1, 1.35])
    table_state = None

    table_prov = provenance_from_frame(
        ranked if not ranked.empty else (region_df if is_region_view else mun_df),
        default_label="Area selection summary",
        default_source=table_source,
    )

    with col_table:
        st.markdown("#### Ranked areas")
        st.caption(f"{table_prov.badge} Source: {table_source}")
        if ranked.empty:
            st.info(
                "No region summary available."
                if is_region_view
                else "No municipality summary available."
            )
        else:
            table_columns = display_cols + [
                c for c in ("data_provenance", "source") if c in ranked.columns
            ]
            table_state = st.dataframe(
                style_synthetic_rows(ranked, columns=table_columns),
                column_config=_area_selection_column_config(),
                width="stretch",
                height=420,
                on_select="rerun",
                selection_mode="single-row",
                key=f"area_selection_table_{view}",
            )
            if "is_synthetic" in ranked.columns and bool(ranked["is_synthetic"].any()):
                st.caption("🟡 Highlighted rows = demo/synthetic data.")

    selected_id: str | None = None
    selected_coords: tuple[float, float] | None = None
    missing_coords = False
    use_pilot_default_map = False
    if table_state is not None and table_state.selection.rows:
        row_idx = table_state.selection.rows[0]
        row = ranked.iloc[row_idx]
        if is_region_view:
            selected_id = str(row["region_name"])
            selected_coords = lookup_region_coordinates(selected_id)
        else:
            selected_id = str(row["municipality"])
            selected_coords = lookup_municipality_coordinates(selected_id)
        if selected_coords is None:
            missing_coords = True
    elif not ranked.empty:
        use_pilot_default_map = True
        if is_region_view:
            selected_id = DEMO_PILOT_BC_HYDRO_REGION
            selected_coords = lookup_region_coordinates(selected_id)
        else:
            selected_id = DEMO_PILOT_MUNICIPALITY
            selected_coords = lookup_municipality_coordinates(selected_id)
        if selected_coords is None:
            missing_coords = True
            use_pilot_default_map = False

    with col_map:
        st.markdown("#### Outage intensity + population")
        st.caption(
            "Basemap disabled (demo portability). Disk size ∝ √(unique_outages); "
            "green outline ring ∝ √(population). Hover for unique-outage metrics."
        )
        if missing_coords and selected_id:
            st.info(
                f"No map coordinates for **{selected_id}** in the demo population file. "
                "Map view unchanged — select another row or use region view."
            )
        show_municipalities = st.checkbox(
            "Overlay top municipalities (region view only)",
            value=False,
            disabled=not is_region_view,
        )
        show_bc_lines = st.checkbox(
            BC_TRANSMISSION_UI_LABEL,
            value=False,
            help=(
                "BC Geographic Warehouse HV transmission lines (reference overlay). "
                f"Clipped to the **{DEMO_PILOT_MUNICIPALITY}** pilot bbox when enabled."
            ),
        )
        layers: list[pdk.Layer] = []
        if show_bc_lines:
            bc_layer = bc_transmission_path_layer()
            if bc_layer is not None:
                layers.append(bc_layer)
        map_df = pd.DataFrame()

        if is_region_view:
            map_df, _ = prepare_region_hotspot_map_df()
            if map_df.empty:
                st.info("Could not build region map (missing summary or centroids).")
            else:
                layers.extend(_area_hotspot_map_layers(map_df, municipality=False))
        else:
            map_df = prepare_municipality_hotspot_map_df(limit=25)
            if map_df.empty:
                st.info("No municipality rows with map coordinates.")
            else:
                layers.extend(_area_hotspot_map_layers(map_df, municipality=True))

        if show_municipalities and is_region_view:
            mun_map = prepare_municipality_hotspot_map_df(limit=15)
            if not mun_map.empty:
                layers.append(
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=mun_map,
                        get_position="[lon, lat]",
                        get_fill_color=[100, 100, 100, 180],
                        get_radius="outage_radius_m",
                        pickable=True,
                        tooltip=_pydeck_tooltip(),
                    )
                )

        if selected_coords is not None:
            view_state = selection_area_map_view_state(
                selected_coords[0],
                selected_coords[1],
                municipality=not is_region_view,
            )
        elif use_pilot_default_map:
            view_state = pilot_area_map_view_state(municipality=not is_region_view)
        elif not map_df.empty:
            view_state = fit_area_map_view_state(map_df)
        else:
            view_state = default_area_map_view_state()

        if layers:
            deck = pdk.Deck(
                map_style=None,
                initial_view_state=view_state,
                layers=layers,
            )
            st.pydeck_chart(deck, width="stretch")

    with st.expander("All BC regions"):
        if region_df.empty:
            st.info("No region summary loaded.")
        else:
            region_sorted = promote_pilot_row(
                region_df.sort_values("unique_outages", ascending=False),
                municipality=False,
            )
            region_cols = select_display_columns(region_df, municipality=False) + [
                c for c in ("data_provenance", "source") if c in region_sorted.columns
            ]
            st.dataframe(
                style_synthetic_rows(region_sorted, columns=region_cols),
                column_config=_area_selection_column_config(),
                width="stretch",
            )
            if "is_synthetic" in region_sorted.columns and bool(region_sorted["is_synthetic"].any()):
                st.caption("🟡 Highlighted rows = demo/synthetic data.")
        if mun_df.empty:
            st.info("No municipality summary loaded.")
        else:
            mun_sorted = promote_pilot_row(
                mun_df.sort_values("unique_outages", ascending=False),
                municipality=True,
            )
            mun_cols = select_display_columns(mun_df, municipality=True) + [
                c for c in ("data_provenance", "source") if c in mun_sorted.columns
            ]
            st.dataframe(
                style_synthetic_rows(mun_sorted, columns=mun_cols),
                column_config=_area_selection_column_config(),
                width="stretch",
            )
            if "is_synthetic" in mun_sorted.columns and bool(mun_sorted["is_synthetic"].any()):
                st.caption("🟡 Highlighted rows = demo/synthetic data.")

    with st.expander("Refresh area-selection data"):
        st.caption(
            "Copy extractor `region_summary.csv` / `municipality_summary.csv` into `data/processed/` "
            "or set `EXTRACTOR_OUTPUT_DIR`. See README."
        )


def _surrey_aoi_comparison_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "AOI option": "Surrey municipal boundary",
                "Area, ha": "36,475",
                "Recommended use": "Not recommended for first purchase",
                "Notes": "Too large / expensive for sample",
            },
            {
                "AOI option": "Transmission buffer 100 m",
                "Area, ha": "1,873",
                "Recommended use": "Low-cost option",
                "Notes": "Narrow corridor exposure",
            },
            {
                "AOI option": "Transmission buffer 200 m",
                "Area, ha": "3,580",
                "Recommended use": "Recommended first purchase",
                "Notes": "Best balance",
            },
            {
                "AOI option": "Transmission buffer 300 m",
                "Area, ha": "5,239",
                "Recommended use": "Larger option",
                "Notes": "More context, higher cost",
            },
            {
                "AOI option": "Outage-prone sub-area",
                "Area, ha": "3,859",
                "Recommended use": "Alternative",
                "Notes": "Good if corridor AOI is not accepted",
            },
        ]
    )


def _surrey_planet_model_improvement_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Model feature": "Vegetation exposure",
                "Current demo source": "Synthetic corridor score",
                "With Planet sample": "Canopy cover / height near corridors",
            },
            {
                "Model feature": "Vegetation dryness",
                "Current demo source": "Synthetic or unavailable",
                "With Planet sample": "SWC + LST + greenness/dryness indicators",
            },
            {
                "Model feature": "Change over time",
                "Current demo source": "Not available",
                "With Planet sample": "Canopy / vegetation condition change",
            },
            {
                "Model feature": "Corridor risk ranking",
                "Current demo source": "Weather + public outage proxy",
                "With Planet sample": "Weather + outage proxy + real remote-sensing vegetation layer",
            },
            {
                "Model feature": "Map layer",
                "Current demo source": "Synthetic / public proxy",
                "With Planet sample": "Real AOI-based satellite-derived indicators",
            },
        ]
    )


def _open_free_layer_status(*paths: Any) -> str:
    """Return Loaded when any processed open-data artifact exists on disk."""
    if any(getattr(p, "exists", lambda: False)() for p in paths):
        return "Loaded (processed CSV)"
    return "Available (open) — not wired"


def _surrey_free_data_fallback_table(
    *,
    weather_result: WeatherLoadResult,
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame,
    mun_row: pd.Series | None,
) -> pd.DataFrame:
    if weather_result.is_synthetic or weather_result.df.empty:
        eccc_status = "Cached demo"
    elif DEMO_OFFLINE_MODE:
        eccc_status = "Cached demo"
    else:
        eccc_status = "Loaded / live or cached"

    if json_provenance.is_synthetic or outages_json_df.empty:
        live_outage_status = "Demo fallback" if not outages_json_df.empty else "Unavailable"
    elif json_provenance.badge == "🔴 Unavailable":
        live_outage_status = "Unavailable"
    else:
        live_outage_status = "Loaded"

    archive_status = "Loaded" if mun_row is not None else "Not loaded"

    if BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON.exists():
        tx_status = "Loaded (Lower Mainland export)"
    elif BC_TRANSMISSION_GEOJSON.exists():
        tx_status = "Loaded / optional (bundled sample)"
    else:
        tx_status = "Not loaded"

    worldcover_status = _open_free_layer_status(
        SURREY_WORLDCOVER_STATS_CSV,
        SURREY_FREE_DATA_SUMMARY_CSV,
    )
    sentinel_status = _open_free_layer_status(SURREY_SENTINEL2_STATS_CSV, SURREY_FREE_DATA_SUMMARY_CSV)

    return pd.DataFrame(
        [
            {
                "Layer": "Sentinel-2 (Copernicus CDSE)",
                "Free source": "Copernicus Data Space — S2 L2A, NDVI/NDMI",
                "Status": sentinel_status,
                "Demo use": "Greenness, moisture, vegetation change",
                "Limitation": "10 m; cloud gaps; processing pipeline required",
            },
            {
                "Layer": "WorldCover / Canada LC (NALCMS)",
                "Free source": "ESA WorldCover 2021 + NRCan 2020",
                "Status": worldcover_status,
                "Demo use": "Static tree/forest/built fractions in corridor AOI",
                "Limitation": "Annual/static; no near-daily moisture or 3 m canopy",
            },
            {
                "Layer": "LidarBC / City of Surrey LiDAR",
                "Free source": "portal.lidarbc.ca + data.surrey.ca LiDAR 2022",
                "Status": "City 2022 available (open) — not wired",
                "Demo use": "Canopy height, DSM/DEM structure",
                "Limitation": "Provincial LidarBC sparse in Surrey; large bulk downloads",
            },
            {
                "Layer": "BC VRI",
                "Free source": "DataBC WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY WFS",
                "Status": "Available (WFS) — not wired",
                "Demo use": "Stand height, crown closure in forested segments",
                "Limitation": "Sparse urban coverage; photo inventory not satellite NRT",
            },
            {
                "Layer": "Landsat / MODIS LST",
                "Free source": "USGS Landsat C2 + NASA MOD11A1",
                "Status": "Available (open) — not wired",
                "Demo use": "Land surface temperature / heat stress proxy",
                "Limitation": "30 m–1 km; gap-filled; coarser than Planet LST 100 m",
            },
            {
                "Layer": "ECCC weather",
                "Free source": "MSC GeoMet / api.weather.gc.ca",
                "Status": eccc_status,
                "Demo use": "Weather severity term in risk formula",
                "Limitation": "Point/station-based; not land-surface moisture",
            },
            {
                "Layer": "BC Hydro live outages",
                "Free source": "outages-map-data.json + RSS",
                "Status": live_outage_status,
                "Demo use": "Live Surrey outage density",
                "Limitation": "Snapshot only; no validated cause codes in public feed",
            },
            {
                "Layer": "GitHub outage archive",
                "Free source": "github.com/outages/bchydro-outages",
                "Status": archive_status,
                "Demo use": "Municipality priority / tree-weather proxy counts",
                "Limitation": "Unofficial; incomplete geography",
            },
            {
                "Layer": "BC transmission geometry",
                "Free source": "DataBC GBA_TRANSMISSION_LINES_SP WFS",
                "Status": tx_status,
                "Demo use": "Corridor AOI buffers and map underlay",
                "Limitation": "HV transmission only; not distribution feeders",
            },
        ]
    )


def _surrey_poc_status_table(
    *,
    weather_result: WeatherLoadResult,
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame,
    mun_row: pd.Series | None,
    planet_status: str,
) -> pd.DataFrame:
    if weather_result.is_synthetic or weather_result.df.empty:
        weather_status = "Cached demo"
    elif DEMO_OFFLINE_MODE:
        weather_status = "Cached demo"
    else:
        weather_status = "Loaded / live or cached"

    if json_provenance.is_synthetic or outages_json_df.empty:
        outage_status = "Demo fallback" if not outages_json_df.empty else "Unavailable"
    elif json_provenance.badge == "🔴 Unavailable":
        outage_status = "Unavailable"
    else:
        outage_status = "Loaded"

    archive_status = "Loaded" if mun_row is not None else "Not loaded"

    if BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON.exists():
        tx_status = "Loaded (Lower Mainland export)"
    elif BC_TRANSMISSION_GEOJSON.exists():
        tx_status = "Loaded / optional (bundled sample)"
    else:
        tx_status = "Not loaded"

    planet_label = {
        "not loaded": "Not loaded",
        "placeholder": "Placeholder CSV",
        "loaded": "Loaded",
    }.get(planet_status, planet_status)

    return pd.DataFrame(
        [
            {"Layer": "ECCC weather", "Status": weather_status},
            {"Layer": "BC Hydro live outage feed", "Status": outage_status},
            {"Layer": "Unofficial outage archive summary", "Status": archive_status},
            {"Layer": "Public transmission geometry", "Status": tx_status},
            {"Layer": "Synthetic vegetation proxy", "Status": "Loaded"},
            {"Layer": "Planet sample data", "Status": planet_label},
            {"Layer": "BC Hydro internal outage / feeders / assets", "Status": "Not available"},
        ]
    )


def _render_surrey_poc_context_expanders(
    *,
    pilot_outages: pd.DataFrame,
    json_provenance: DatasetProvenance,
    mun_row: pd.Series | None,
    weather_result: WeatherLoadResult,
    planet_result: PlanetLoadResult,
) -> None:
    with st.expander("Why Surrey was selected"):
        st.markdown(
            """
            - **Pilot geography** — Surrey is a large Lower Mainland municipality with mixed urban–suburban ROW and tree exposure.
            - **Lower Mainland focus** — aligns with BC Hydro transmission demo corridors and public outage visibility.
            - **Public data availability** — BC Hydro live outage JSON/RSS, unofficial outage archive snapshots, ECCC weather, and open transmission geometry are accessible for a concept PoC without internal feeds.
            """
        )

    with st.expander("Available public outage data"):
        _render_outage_provenance_alerts(json_provenance)
        if pilot_outages.empty and mun_row is None:
            st.info("No live Surrey outages and no unofficial archive municipality row loaded.")
        else:
            summary_cols = st.columns(2)
            with summary_cols[0]:
                st.markdown("**Live map JSON (Surrey filter)**")
                if pilot_outages.empty:
                    st.caption("No current Surrey outages in the live feed.")
                else:
                    metrics = live_outage_metrics(pilot_outages)
                    st.markdown(
                        f"- Active outages: **{metrics['count']}**\n"
                        f"- Customers affected: **{metrics['customers']:,}**"
                    )
            with summary_cols[1]:
                st.markdown("**Unofficial archive snapshot (municipality summary)**")
                if mun_row is None:
                    st.caption("No Surrey row in municipality summary CSV.")
                else:
                    st.markdown(
                        f"- Unique outages (proxy): **{int(mun_row.get('unique_outages', 0)):,}**\n"
                        f"- Tree-related count: **{int(mun_row.get('tree_related_outage_count', 0)):,}**\n"
                        f"- Weather-related count: **{int(mun_row.get('weather_related_outage_count', 0)):,}**\n"
                        f"- Suggested priority score: **{float(mun_row.get('suggested_priority_score', 0)):.3f}**"
                    )

    with st.expander("ECCC weather coverage"):
        st.caption(
            f"{weather_result.data_source} — observation "
            f"{weather_result.observation_time or weather_result.last_updated or 'n/a'} UTC"
        )
        if weather_result.freshness_warning:
            st.warning(weather_result.freshness_warning)
        pilot_weather = filter_weather_pilot_region(weather_result.df)
        if pilot_weather.empty:
            st.info("Lower Mainland / Surrey weather slice not loaded in the current mode.")
        else:
            st.caption(
                f"{len(pilot_weather)} weather row(s) for pilot region; mean severity "
                f"{pilot_weather['weather_severity_score'].mean():.1f} (illustrative)."
            )

    with st.expander("Public / proxy vegetation layer status"):
        st.markdown(
            """
            - **Corridor forest exposure** — bundled `demo_corridors.csv` scores (🟡 synthetic proxy).
            - **BC Geographic Warehouse transmission** — optional HV underlay when local GeoJSON is present.
            - **No public LiDAR / treatment records** — internal vegetation work-management data still required for operations.
            """
        )

    with st.expander("Planet sample data status"):
        st.markdown(f"- Status: **{planet_result.status}**")
        st.caption(planet_result.detail)
        if planet_result.row is not None:
            scores = planet_scores_from_row(planet_result.row)
            score_cols = st.columns(4)
            score_cols[0].metric("Vegetation exposure", scores["vegetation_exposure_score"])
            score_cols[1].metric("Vegetation dryness", scores["vegetation_dryness_score"])
            score_cols[2].metric("Canopy exposure", scores["canopy_exposure_score"])
            score_cols[3].metric("Heat / drought stress", scores["heat_drought_stress_score"])
            st.dataframe(planet_result.df, width="stretch")


def _surrey_poc_tab(
    *,
    live_public_only: bool,
    pilot_outages: pd.DataFrame,
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame | None = None,
) -> None:
    del live_public_only  # tab uses session-level LIVE_PUBLIC_ONLY via loaders
    st.subheader("Surrey PoC Sample")
    _show_planet_disclaimer_once()
    st.caption(
        f"Demo region: **{st.session_state.demo_region}** · Data mode: **{DEMO_DATA_MODE}** · "
        f"Planet sample data: **{_planet_sample_status_label()}**"
    )

    st.markdown("#### Recommended Planet sample purchase")
    st.markdown(
        """
        - **Preferred AOI:** Surrey transmission corridor buffer
        - **Recommended buffer:** 200 m
        - **Approximate area:** 3,580 ha
        - **Backup low-cost option:** 100 m buffer, 1,873 ha
        - **Larger option:** 300 m buffer, 5,239 ha
        - **Alternative AOI:** outage-prone sub-area, 3,859 ha
        - **Municipal boundary:** 36,475 ha — likely too large for first sample
        """
    )
    st.markdown(
        "The 200 m corridor buffer is recommended because it is focused on infrastructure exposure, "
        "small enough for a paid sample, and large enough to test vegetation exposure, canopy structure, "
        "heat/drought stress, and corridor-level risk ranking."
    )

    st.markdown("#### AOI comparison")
    st.dataframe(_surrey_aoi_comparison_df(), width="stretch", hide_index=True)

    st.markdown("#### Requested Planet products (PoC scope)")
    st.markdown(
        """
        - **Forest Carbon Monitoring / forest structure** — canopy cover and canopy height (3 m, quarterly)
        - **Soil Water Content** — 100 m preferred
        - **Land Surface Temperature** — 100 m preferred
        - **ARPS or PlanetScope-derived vegetation condition indicators**
        - **Greenness/dryness or green/brown/non-vegetation indicators** if available as derived analytics
        - **Temporal change** — canopy change, vegetation change, recent vs historical comparison
        """
    )
    st.caption(
        "Planet documentation review found no standalone Planet catalog product named “Vegetation Cover”; "
        "green/brown/non-vegetation indicators should be requested as derived analytics from ARPS, "
        "PlanetScope, or another appropriate workflow."
    )

    st.markdown("#### How Planet data improves the model")
    st.dataframe(_surrey_planet_model_improvement_df(), width="stretch", hide_index=True)

    st.markdown("#### What Planet data does not replace")
    st.markdown(
        """
        - BC Hydro internal outage history
        - Feeder / circuit topology
        - Asset condition
        - Vegetation treatment records
        - Work management data
        - Restoration / crew response data
        - Customer interruption metrics such as SAIDI, SAIFI, CAIDI
        """
    )
    st.markdown(
        "Planet can strengthen the vegetation and environmental exposure layer, but Fujitsu still needs "
        "to integrate it with weather, outage, network, and operational data to produce decision support."
    )

    with st.expander("Questions for Planet"):
        for question in (
            "Can you quote the Surrey 200 m transmission corridor buffer, approx. 3,580 ha?",
            "Is 100 m / 200 m / 300 m corridor buffer pricing different only by hectare?",
            "Which products are available for Surrey, BC?",
            "Can you provide FCM canopy cover and canopy height at 3 m?",
            "Can you provide SWC and LST at 100 m?",
            "Can you provide greenness/dryness or green/brown/non-vegetation indicators through ARPS or PlanetScope-derived analytics?",
            "Can outputs be delivered as GeoTIFF, CSV summary, API, cloud delivery, or ArcGIS-compatible layer?",
            "Can results be summarized by our AOI / corridor buffer?",
            "Can Fujitsu use derived outputs in internal and client-facing proof-of-process demos?",
            "Is there any trial/sample option before paid purchase?",
        ):
            st.markdown(f"- {question}")

    st.markdown("#### Data mode explanation")
    st.markdown(
        f"""
        **Public/proxy only** — Uses ECCC weather, BC Hydro public outage feeds, unofficial outage archive
        summaries, public transmission geometry, and synthetic vegetation scores.

        **Planet sample enabled** — Replaces synthetic vegetation assumptions with Planet-derived canopy,
        vegetation condition, soil moisture, and land surface temperature indicators for the Surrey AOI.

        **BC Hydro internal mode — future** — Would use internal outage history, feeders/circuits,
        vegetation treatment records, asset data, and work-management data.
        """
    )

    st.markdown("#### Recommended next action")
    st.info(
        "Ask Planet for a quote for the Surrey 200 m transmission corridor buffer, approximately 3,580 ha, "
        "with FCM canopy cover/height, SWC 100 m, LST 100 m, and ARPS/PlanetScope-derived vegetation "
        "condition indicators. Use the result to replace synthetic vegetation scores in the demo and test "
        "whether satellite-derived vegetation indicators improve corridor-level risk ranking."
    )

    weather_result = _load_weather()
    mun_row = _surrey_municipality_outage_row()
    planet_result = load_planet_surrey_sample(DEMO_DATA_MODE)
    province_outages = outages_json_df if outages_json_df is not None else pd.DataFrame()

    st.markdown("#### Layer status")
    st.dataframe(
        _surrey_poc_status_table(
            weather_result=weather_result,
            json_provenance=json_provenance,
            outages_json_df=province_outages,
            mun_row=mun_row,
            planet_status=planet_result.status,
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("#### Free/open data fallback")
    st.caption(
        "Public datasets that can stand in for Planet layers during discovery. "
        "See docs/open_free_data_for_surrey.md and docs/free_data_integration_plan.md."
    )
    st.dataframe(
        _surrey_free_data_fallback_table(
            weather_result=weather_result,
            json_provenance=json_provenance,
            outages_json_df=province_outages,
            mun_row=mun_row,
        ),
        width="stretch",
        hide_index=True,
    )
    st.info(
        "Free/open data can demonstrate the workflow and reduce early purchase risk, "
        "but it does not replace Planet commercial products or BC Hydro internal operational data."
    )

    _render_surrey_poc_context_expanders(
        pilot_outages=pilot_outages,
        json_provenance=json_provenance,
        mun_row=mun_row,
        weather_result=weather_result,
        planet_result=planet_result,
    )


tabs = st.tabs(
    [
        "Overview",
        "Risk Dashboard",
        "Risk Map",
        "Area selection",
        "Surrey PoC Sample",
        "Backtesting",
        "Data Sources & Assumptions",
    ]
)

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
    if SURREY_PLANET_ACTIVE:
        _show_planet_disclaimer_once()
    weather_result = _load_weather()
    weather_df = weather_result.df
    outages_json_df = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    pilot_outages = _filter_outages_for_risk_map(outages_json_df)
    risk_df = _prepare_risk_data(LIVE_PUBLIC_ONLY, pilot_outages=pilot_outages, data_mode=DEMO_DATA_MODE)
    json_prov = provenance_from_frame(
        outages_json_df,
        default_label="BC Hydro outage JSON",
        default_source="not loaded",
        live_public_only=LIVE_PUBLIC_ONLY,
    )
    weather_prov = DatasetProvenance(
        label="Weather",
        is_synthetic=weather_result.is_synthetic,
        source=weather_result.data_source,
        detail=weather_result.detail,
    )
    st.markdown("#### Storm risk summary")
    obs_time = weather_result.observation_time or weather_result.last_updated
    st.caption(
        f"{provenance_badge(True)} Risk · {weather_prov.badge} Weather ({obs_time} UTC) · "
        f"{json_prov.badge} Outages (map JSON, {DEMO_PILOT_MUNICIPALITY}) · "
        f"Planet sample data: **{_planet_sample_status_label()}** · Data mode: **{DEMO_DATA_MODE}**"
    )
    if weather_result.freshness_warning:
        st.warning(weather_result.freshness_warning)
    if pilot_outages.empty and LIVE_PUBLIC_ONLY and outages_json_df.empty:
        st.warning(
            "No live outage rows (Live public only is on). Disable the sidebar toggle for demo fallback, "
            "or refresh after fixing network/TLS."
        )
    _summary_cards(risk_df, pilot_outages)
    _render_live_outages_section(outages_json_df, json_provenance=json_prov)

    with st.expander(f"All BC demo corridors — {provenance_badge(True)}"):
        _show_dataframe_with_provenance(load_all_demo_corridors())

    st.markdown("#### Risk ranking")
    level_filter = st.multiselect(
        "Filter by risk level",
        ["High", "Medium", "Low"],
        default=["High", "Medium", "Low"],
    )
    ranking = risk_df[risk_df["risk_level"].isin(level_filter)].sort_values("risk_score", ascending=False)
    _show_dataframe_with_provenance(
        ranking,
        columns=[
            "demo_corridor_id",
            "region",
            "municipality",
            "risk_score",
            "risk_level",
            "top_risk_driver",
            "suggested_review_action",
            "data_provenance",
            "source",
        ],
    )

    st.markdown("#### Top risk drivers")
    st.plotly_chart(
        make_top_drivers_chart(risk_df, dark=_chart_dark, planet_mode=SURREY_PLANET_ACTIVE),
        width="stretch",
    )
    with st.expander(f"Show regional weather input data — {weather_prov.badge}"):
        if weather_df.empty:
            st.info("No weather rows loaded in the current mode.")
        else:
            pilot_weather = filter_weather_pilot_region(weather_df)
            if weather_result.freshness_warning:
                st.warning(weather_result.freshness_warning)
            _show_weather_dataframe(pilot_weather)
            if len(weather_df) > len(pilot_weather):
                with st.expander(f"All loaded weather rows ({len(weather_df)})"):
                    _show_weather_dataframe(weather_df)

with tabs[2]:
    outages_json_df = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    pilot_outages = _filter_outages_for_risk_map(outages_json_df)
    risk_df = _prepare_risk_data(LIVE_PUBLIC_ONLY, pilot_outages=pilot_outages, data_mode=DEMO_DATA_MODE)
    _risk_map_tab(
        risk_df,
        outages_json_df,
        json_provenance=provenance_from_frame(
            outages_json_df,
            default_label="BC Hydro outage JSON",
            default_source="not loaded",
            live_public_only=LIVE_PUBLIC_ONLY,
        ),
    )

with tabs[3]:
    _area_selection_tab()

with tabs[4]:
    outages_json_df = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    pilot_outages = _filter_outages_for_risk_map(outages_json_df)
    _surrey_poc_tab(
        live_public_only=LIVE_PUBLIC_ONLY,
        pilot_outages=pilot_outages,
        outages_json_df=outages_json_df,
        json_provenance=provenance_from_frame(
            outages_json_df,
            default_label="BC Hydro outage JSON",
            default_source="not loaded",
            live_public_only=LIVE_PUBLIC_ONLY,
        ),
    )

with tabs[5]:
    st.subheader("Backtesting")
    st.warning("Synthetic demo backtesting only — not validated historical outage performance.")
    st.caption(f"{provenance_badge(True)} No public live backtesting feed — `demo_backtesting.csv` only.")
    backtesting_df = load_backtesting_data()
    metrics = compute_backtesting_metrics(backtesting_df)
    cols = st.columns(3)
    cols[0].metric("Demo outages captured in top-risk areas", f"{metrics['capture_rate_pct']}%")
    cols[1].metric("Demo model vs weather-only baseline (synthetic)", metrics["demo_vs_baseline_delta"])
    cols[2].metric("Dataset", provenance_badge(True))

    fig = px.scatter(
        backtesting_df,
        x="demo_model_score",
        y="observed_public_outage_count",
        color="region",
        size="weather_only_baseline_score",
        title="Demo model score vs synthetic observed outage counts (by region)",
    )
    apply_plotly_chart_theme(fig, dark=_chart_dark)
    st.plotly_chart(fig, width="stretch")
    with st.expander(f"Show backtesting input table — {provenance_badge(True)}"):
        _show_dataframe_with_provenance(backtesting_df, alt_highlight=True)

with tabs[6]:
    st.subheader("Data sources & assumptions")
    st.markdown(
        """
        **How to read this tab**

        - **Real public data** — BC Hydro public outage map JSON (Risk Dashboard & Risk Map); Environment Canada / MSC endpoints referenced for weather context.
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

