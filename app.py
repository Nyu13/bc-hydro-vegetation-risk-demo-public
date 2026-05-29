from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from src.backtesting import compute_backtesting_metrics, load_backtesting_data
from src.config import (
    BC_TRANSMISSION_BC_GEOJSON,
    BC_TRANSMISSION_GEOJSON,
    BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON,
    BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON,
    DEMO_DATA_DIR,
    DEMO_DATA_MODES,
    DEMO_OFFLINE_MODE,
    DEMO_PILOT_BC_HYDRO_REGION,
    DEMO_PILOT_MUNICIPALITY,
    DEMO_PILOT_TRANSMISSION_BBOX,
    DEMO_PRIMARY_DISCLAIMER,
    DEMO_REGION_OPTIONS,
    DOCS_DIR,
    PLANET_POC_DISCLAIMER,
    PROCESSED_DATA_DIR,
    SURREY_FREE_DATA_SUMMARY_CSV,
    SURREY_SENTINEL2_STATS_CSV,
    SURREY_WORLDCOVER_STATS_CSV,
)
from src.data_provenance import (
    DatasetProvenance,
    PROVENANCE_OPEN_FREE,
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
from src.free_data_loader import (
    free_data_scores_from_row,
    free_data_usable,
    load_surrey_free_data_summary,
    load_surrey_sentinel2_scene_qa,
    load_surrey_sentinel2_stats,
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


def _prepare_risk_data(
    live_public_only: bool,
    *,
    pilot_scope: bool = True,
    pilot_outages: pd.DataFrame | None = None,
    data_mode: str | None = None,
) -> pd.DataFrame:
    mode = validate_data_mode(data_mode or DEMO_DATA_MODE)
    planet_result = load_planet_surrey_sample(mode)
    free_data_result = load_surrey_free_data_summary()
    use_planet_formula = planet_sample_enabled(mode) and planet_result.status in {
        "placeholder",
        "loaded",
    }
    use_free_data = (not use_planet_formula) and free_data_usable(free_data_result)

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
    free_scores = free_data_scores_from_row(free_data_result.row if use_free_data else None)
    merged["surrey_planet_formula_applied"] = use_planet_formula
    merged["surrey_free_data_applied"] = use_free_data
    merged["planet_sample_status"] = planet_result.status
    merged["free_data_status"] = free_data_result.status
    merged["vegetation_dryness_score"] = (
        planet_scores["vegetation_dryness_score"]
        if use_planet_formula
        else free_scores["vegetation_dryness_score"]
    )
    merged["canopy_exposure_score"] = (
        planet_scores["canopy_exposure_score"]
        if use_planet_formula
        else free_scores["canopy_exposure_score"]
    )
    merged["heat_drought_stress_score"] = (
        planet_scores["heat_drought_stress_score"]
        if use_planet_formula
        else free_scores["heat_drought_stress_score"]
    )

    def _vegetation_exposure_row(row: pd.Series) -> float:
        if use_planet_formula:
            return planet_scores["vegetation_exposure_score"]
        if use_free_data:
            return free_scores["vegetation_exposure_score"]
        if pd.notna(row.get("forest_exposure_score")) and pd.notna(row.get("historical_outage_proxy_score")):
            return calculate_corridor_exposure_score(
                float(row["forest_exposure_score"]),
                float(row["historical_outage_proxy_score"]),
                float(row.get("overhead_length_km") or 0.0),
            )
        return float(row.get("vegetation_exposure_score", 50.0))

    merged["vegetation_exposure_score"] = merged.apply(_vegetation_exposure_row, axis=1)
    if use_free_data:
        merged["terrain_access_score"] = free_scores["terrain_access_score"]
    elif "corridor_terrain_access_score" in merged.columns:
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
        is_synthetic = True
        data_provenance = None
    elif use_free_data:
        source = (
            "PoC composite: live weather + open/free vegetation (WorldCover pipeline) + "
            f"{'Surrey live outage density' if merged['live_outage_density_applied'].any() else 'municipality outage proxy'}"
            f" — {free_data_result.detail}"
        )
        is_synthetic = free_data_result.status != "open_free_processed"
        data_provenance = (
            PROVENANCE_OPEN_FREE if free_data_result.status == "open_free_processed" else None
        )
    elif merged["live_outage_density_applied"].any():
        source = (
            "PoC composite: live weather + Surrey map JSON outage density; "
            "corridor/terrain from demo_corridors.csv (synthetic)"
        )
        is_synthetic = True
        data_provenance = None
    else:
        source = "demo_risk_scores.csv + demo corridors (synthetic; weather may be live)"
        is_synthetic = True
        data_provenance = None
    return tag_dataframe(
        merged,
        is_synthetic=is_synthetic,
        source=source,
        data_provenance=data_provenance,
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
        bc_layer = bc_transmission_path_layer()
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
                "Shows all lines in the loaded GeoJSON (Lower Mainland bundled export by default)."
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


def _metric_text(
    value: object,
    *,
    decimals: int = 2,
    suffix: str = "",
    signed: bool = False,
) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        num = float(value)
        formatted = f"{num:.{decimals}f}{suffix}"
        if signed and num >= 0:
            return f"+{formatted}"
        return formatted
    except (TypeError, ValueError):
        return "—"


def _first_present(*values: object) -> object | None:
    for value in values:
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            return value
    return None


def _aoi_display_label(aoi_id: object) -> str:
    text = str(aoi_id or "").strip().upper()
    if text == "SURREY-TX-BUF-200M":
        return "Surrey transmission corridor 200 m buffer"
    if text:
        return text.replace("-", " ").replace("_", " ").title()
    return "Surrey transmission corridor 200 m buffer"


@st.cache_data(show_spinner=False)
def _load_surrey_sentinel2_stats_df() -> pd.DataFrame:
    return load_surrey_sentinel2_stats().df


def _render_surrey_open_free_satellite_section() -> None:
    """Summary cards, trend chart, and scene QA for open/free satellite layers."""
    st.markdown("#### Open/free satellite data now active")

    free_data = load_surrey_free_data_summary()
    stats_df = _load_surrey_sentinel2_stats_df()
    stats_row = stats_df.iloc[0] if not stats_df.empty else None
    summary_row = free_data.row

    stats_processed = (
        stats_row is not None
        and str(stats_row.get("data_status", "")).strip().lower() == "open_free_processed"
    )
    summary_active = free_data.status == "open_free_processed" and summary_row is not None

    if not summary_active and not stats_processed:
        st.info(
            "Open/free satellite summary not built yet — run "
            "TMP/scripts/run_surrey_free_data_pipeline.py and "
            "TMP/scripts/build_surrey_sentinel2_indices.py --safe-dir."
        )
        return

    row = summary_row if summary_row is not None else stats_row
    if row is None:
        st.info("Open/free satellite summary not available.")
        return

    tree_pct = _first_present(
        summary_row.get("worldcover_tree_pct") if summary_row is not None else None,
        row.get("worldcover_tree_pct"),
    )
    built_pct = _first_present(
        summary_row.get("worldcover_built_pct") if summary_row is not None else None,
        row.get("worldcover_built_pct"),
    )
    ndvi = _first_present(
        stats_row.get("sentinel2_ndvi_mean") if stats_row is not None else None,
        row.get("sentinel2_ndvi_mean"),
    )
    ndmi = _first_present(
        stats_row.get("sentinel2_ndmi_mean") if stats_row is not None else None,
        row.get("sentinel2_ndmi_mean"),
    )
    ndvi_change = _first_present(
        stats_row.get("sentinel2_ndvi_change") if stats_row is not None else None,
        row.get("sentinel2_ndvi_change"),
    )
    dryness = _first_present(
        summary_row.get("vegetation_dryness_score") if summary_row is not None else None,
        row.get("vegetation_dryness_score"),
    )
    change_score = _first_present(
        summary_row.get("vegetation_change_score") if summary_row is not None else None,
        row.get("vegetation_change_score"),
    )
    scenes_processed = _first_present(
        stats_row.get("scenes_processed") if stats_row is not None else None,
        stats_row.get("scenes_used") if stats_row is not None else None,
        row.get("scenes_used"),
    )
    scenes_discovered = _first_present(
        stats_row.get("scenes_discovered") if stats_row is not None else None,
        scenes_processed,
    )
    cloud_pct = _first_present(
        stats_row.get("cloud_filtered_pct") if stats_row is not None else None,
        row.get("cloud_filtered_pct"),
    )

    scenes_label = "—"
    if pd.notna(scenes_processed):
        proc = int(scenes_processed)
        disc = int(scenes_discovered) if pd.notna(scenes_discovered) else proc
        scenes_label = f"{proc} / {disc}"

    card_rows = [
        st.columns(5),
        st.columns(5),
    ]
    card_rows[0][0].metric("AOI", _aoi_display_label(row.get("aoi_id")))
    card_rows[0][1].metric("WorldCover tree cover", _metric_text(tree_pct, suffix="%"))
    card_rows[0][2].metric("WorldCover built-up", _metric_text(built_pct, suffix="%"))
    card_rows[0][3].metric("Sentinel-2 NDVI mean", _metric_text(ndvi, decimals=4))
    card_rows[0][4].metric("Sentinel-2 NDMI mean", _metric_text(ndmi, decimals=4))
    card_rows[1][0].metric("NDVI change", _metric_text(ndvi_change, decimals=4, signed=True))
    card_rows[1][1].metric("Vegetation dryness score", _metric_text(dryness))
    card_rows[1][2].metric("Vegetation change score", _metric_text(change_score))
    card_rows[1][3].metric("Scenes processed", scenes_label)
    card_rows[1][4].metric(
        "Clear AOI pixels (cloud mask)",
        _metric_text(cloud_pct, suffix="%"),
    )

    st.markdown(
        "WorldCover provides static land-cover exposure. Sentinel-2 provides vegetation condition "
        "and moisture proxies using NDVI and NDMI. Together, these open/free layers reduce synthetic "
        "assumptions in **Public/proxy** mode before Planet data is purchased."
    )
    st.caption(
        "Clear AOI pixels are limited after cloud masking, which is expected in coastal BC. "
        "The Sentinel-2 layer is suitable for proof-of-process, but not operational decision-making. "
        "This limitation supports the case for Planet or other analysis-ready commercial products."
    )

    qa_df = load_surrey_sentinel2_scene_qa()
    if qa_df.empty:
        st.info("Scene-level Sentinel-2 QA file not available.")
    else:
        chart_df = qa_df.copy()
        date_col = "acquisition_date" if "acquisition_date" in chart_df.columns else "sensing_date"
        if date_col not in chart_df.columns:
            st.info("Scene-level Sentinel-2 QA file not available.")
        else:
            chart_df[date_col] = pd.to_datetime(chart_df[date_col], errors="coerce")
            chart_df = chart_df.dropna(subset=[date_col])
            if chart_df.empty:
                st.info("Scene-level Sentinel-2 QA file not available.")
            else:
                trend_df = (
                    chart_df.groupby(date_col, as_index=False)[["ndvi_mean", "ndmi_mean"]]
                    .mean(numeric_only=True)
                    .sort_values(date_col)
                )
                trend_long = trend_df.melt(
                    id_vars=[date_col],
                    value_vars=["ndvi_mean", "ndmi_mean"],
                    var_name="index",
                    value_name="value",
                )
                trend_long["index"] = trend_long["index"].map(
                    {"ndvi_mean": "NDVI mean", "ndmi_mean": "NDMI mean"}
                )
                fig = px.line(
                    trend_long,
                    x=date_col,
                    y="value",
                    color="index",
                    markers=True,
                    title="Sentinel-2 vegetation condition trend",
                )
                fig.update_layout(xaxis_title="Acquisition date", yaxis_title="Index value")
                apply_plotly_chart_theme(fig, dark=_chart_dark)
                st.plotly_chart(fig, width="stretch")

    with st.expander("Scene-level QA"):
        table_df = load_surrey_sentinel2_scene_qa()
        if table_df.empty:
            st.info("Scene-level Sentinel-2 QA file not available.")
        else:
            st.dataframe(table_df, width="stretch", hide_index=True)


def _open_free_layer_status(*paths: Any) -> str:
    """Return status for open/free processed layer artifacts."""
    for path in paths:
        if not getattr(path, "is_file", lambda: False)():
            continue
        try:
            import pandas as pd

            df = pd.read_csv(path)
            if not df.empty and "data_status" in df.columns:
                status = str(df["data_status"].iloc[0]).strip().lower()
                if status == "open_free_processed":
                    return "🟦 Loaded (open/free processed)"
                if status == "unavailable_credentials_or_missing_rasters":
                    return "Stub (manual download — see docs)"
                if status.startswith("stub"):
                    return "🟦 Stub (instructions in CSV)"
            return "🟦 Loaded (processed CSV)"
        except Exception:
            return "🟦 Loaded (processed CSV)"
    return "Available (open) — not wired"


def _sentinel2_metric_status(metric_col: str, *, label: str) -> str:
    """Status for a single Sentinel-2 metric column in the stats CSV."""
    path = SURREY_SENTINEL2_STATS_CSV
    if not path.is_file():
        return "Available (open) — not wired"
    try:
        df = pd.read_csv(path)
        if df.empty:
            return "Available (open) — not wired"
        row = df.iloc[0]
        status = str(row.get("data_status", "")).strip().lower()
        val = row.get(metric_col)
        if status == "open_free_processed" and val is not None and pd.notna(val):
            if metric_col in {"scenes_used", "tiles_used"}:
                return f"🟦 Loaded ({label}={val})"
            if metric_col == "cloud_filtered_pct":
                return f"🟦 Loaded ({label}={float(val):.1f}%)"
            return f"🟦 Loaded ({label}={float(val):.3f})"
        if status == "unavailable_credentials_or_missing_rasters":
            return "Stub (manual download — see docs)"
        if status.startswith("stub"):
            return "🟦 Stub (instructions in CSV)"
        return _open_free_layer_status(path, SURREY_FREE_DATA_SUMMARY_CSV)
    except Exception:
        return "Available (open) — not wired"


def _weather_layer_status_badge(weather_result: WeatherLoadResult) -> str:
    if weather_result.is_synthetic or weather_result.df.empty or DEMO_OFFLINE_MODE:
        return "🟡 Cached demo"
    return "🟢 Live/cached"


def _outage_layer_status_badge(
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame,
) -> str:
    if json_provenance.badge == "🔴 Unavailable" or outages_json_df.empty:
        return "🔴 Unavailable"
    if json_provenance.is_synthetic:
        return "🟡 Demo fallback"
    return "🟢 Loaded"


def _archive_layer_status_badge(mun_row: pd.Series | None) -> str:
    return "🟢 Loaded" if mun_row is not None else "🔴 Not loaded"


def _transmission_layer_status_badge() -> str:
    if BC_TRANSMISSION_BC_GEOJSON.exists():
        return "🟢 Loaded (BC-wide export)"
    if BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON.exists():
        return "🟢 Loaded (Lower Mainland processed)"
    if BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON.exists():
        return "🟢 Loaded (Lower Mainland bundled)"
    if BC_TRANSMISSION_GEOJSON.exists():
        return "🟡 Loaded (demo sample ~120 lines)"
    return "🔴 Not loaded"


def _planet_layer_status_badge(planet_status: str) -> str:
    return {
        "not loaded": "🔴 Not loaded",
        "placeholder": "🟡 Placeholder CSV",
        "loaded": "🟢 Loaded",
    }.get(planet_status, f"🟡 {planet_status}")


def _synthetic_vegetation_status_badge(*, free_data_active: bool, planet_active: bool) -> str:
    if planet_active:
        return "🟡 Superseded (Planet sample active)"
    if free_data_active:
        return "🟡 Superseded (open/free active)"
    return "🟡 Loaded (fallback)"


def _normalize_open_free_status(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith(("🟢", "🟡", "🟦", "🔴")):
        return text
    lower = text.lower()
    if "open/free processed" in lower or lower.startswith("loaded"):
        return f"🟦 {text}" if not text.startswith("🟦") else text
    if "stub" in lower or "plan written" in lower:
        return f"🟦 {text}" if not text.startswith("🟦") else text
    if "not wired" in lower or "not built" in lower or "not loaded" in lower:
        return f"🔴 {text}"
    return f"🟡 {text}"


def _build_unified_layer_inventory_table(
    *,
    weather_result: WeatherLoadResult,
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame,
    mun_row: pd.Series | None,
    planet_status: str,
) -> pd.DataFrame:
    free_data = load_surrey_free_data_summary()
    free_data_active = free_data.status == "open_free_processed"
    planet_active = planet_status in {"placeholder", "loaded"} and planet_sample_enabled(DEMO_DATA_MODE)

    summary_status = _normalize_open_free_status(_open_free_layer_status(SURREY_FREE_DATA_SUMMARY_CSV))
    worldcover_status = _normalize_open_free_status(
        _open_free_layer_status(SURREY_WORLDCOVER_STATS_CSV, SURREY_FREE_DATA_SUMMARY_CSV)
    )
    sentinel_ndvi_status = _normalize_open_free_status(
        _sentinel2_metric_status("sentinel2_ndvi_mean", label="NDVI")
    )
    sentinel_ndmi_status = _normalize_open_free_status(
        _sentinel2_metric_status("sentinel2_ndmi_mean", label="NDMI")
    )
    sentinel_change_status = _normalize_open_free_status(
        _sentinel2_metric_status("sentinel2_ndvi_change", label="change")
    )
    sentinel_scenes_status = _normalize_open_free_status(
        _sentinel2_metric_status("scenes_used", label="scenes")
    )
    sentinel_cloud_status = _normalize_open_free_status(
        _sentinel2_metric_status("cloud_filtered_pct", label="clear")
    )
    vri_status = _normalize_open_free_status(
        _open_free_layer_status(
            PROCESSED_DATA_DIR / "surrey_vri_corridor_stats.csv",
            SURREY_FREE_DATA_SUMMARY_CSV,
        )
    )
    lst_status = _normalize_open_free_status(
        _open_free_layer_status(
            PROCESSED_DATA_DIR / "surrey_environmental_stress_corridor_stats.csv",
            SURREY_FREE_DATA_SUMMARY_CSV,
        )
    )
    lidar_status = (
        "🟦 Plan written"
        if (DOCS_DIR / "surrey_lidar_canopy_height_plan.md").is_file()
        else "🔴 Available (open) — not wired"
    )

    weather_obs = weather_result.observation_time or weather_result.last_updated or "n/a"
    weather_limitation = (
        f"Point/station-based; observation {weather_obs} UTC"
        if not weather_result.is_synthetic
        else "Bundled demo_weather.csv when live fetch unavailable"
    )

    return pd.DataFrame(
        [
            {
                "Layer": "ECCC weather",
                "Source": weather_result.data_source,
                "Status": _weather_layer_status_badge(weather_result),
                "Demo use": "weather_severity_score in risk formula",
                "Limitation": weather_limitation,
            },
            {
                "Layer": "BC Hydro live outage JSON",
                "Source": "bchydro.com outages-map-data.json (+ RSS on Risk Map)",
                "Status": _outage_layer_status_badge(json_provenance, outages_json_df),
                "Demo use": "Live Surrey outage density on Risk Dashboard / Map",
                "Limitation": "Snapshot only; no validated cause codes",
            },
            {
                "Layer": "Unofficial outage archive",
                "Source": "github.com/outages/bchydro-outages snapshots",
                "Status": _archive_layer_status_badge(mun_row),
                "Demo use": "Municipality priority / tree-weather proxy counts",
                "Limitation": "Unofficial; incomplete geography",
            },
            {
                "Layer": "Public transmission geometry",
                "Source": "DataBC GBA_TRANSMISSION_LINES_SP WFS",
                "Status": _transmission_layer_status_badge(),
                "Demo use": "Corridor AOI buffers and map underlay",
                "Limitation": "HV transmission only; not distribution feeders",
            },
            {
                "Layer": "Open/free corridor summary",
                "Source": "Merged pipeline → surrey_free_data_corridor_summary.csv",
                "Status": summary_status,
                "Demo use": "Public/proxy vegetation + terrain scores",
                "Limitation": "PoC zonal stats; not BC Hydro ROW GIS",
            },
            {
                "Layer": "ESA WorldCover 2021",
                "Source": "ESA WorldCover 2021 v200",
                "Status": worldcover_status,
                "Demo use": "Static tree/forest/built fractions in corridor AOI",
                "Limitation": "Annual/static; no near-daily moisture or 3 m canopy",
            },
            {
                "Layer": "NALCMS (Canada land cover)",
                "Source": "NRCan 2020 land-cover grid",
                "Status": worldcover_status,
                "Demo use": "Forest fraction in open/free summary",
                "Limitation": "Static; coarser than ROW vegetation inventory",
            },
            {
                "Layer": "Sentinel-2 NDVI",
                "Source": "Local S2 L2A B04+B08 — build_surrey_sentinel2_indices.py",
                "Status": sentinel_ndvi_status,
                "Demo use": "Corridor mean NDVI after SCL cloud mask",
                "Limitation": "Manual CDSE download; 10 m; cloud gaps",
            },
            {
                "Layer": "Sentinel-2 NDMI",
                "Source": "Local S2 L2A B08+B11",
                "Status": sentinel_ndmi_status,
                "Demo use": "Vegetation dryness score when NDMI present",
                "Limitation": "Not Planet SWC; same cloud gaps as NDVI",
            },
            {
                "Layer": "Sentinel-2 NDVI change",
                "Source": "Multi-date .SAFE stack — earliest vs latest scene",
                "Status": sentinel_change_status,
                "Demo use": "vegetation_change_score in corridor summary",
                "Limitation": "Needs ≥2 acquisition dates",
            },
            {
                "Layer": "Sentinel-2 scenes / cloud filter",
                "Source": "Per-scene SCL mask — scenes_used, cloud_filtered_pct",
                "Status": f"{sentinel_scenes_status}; {sentinel_cloud_status}",
                "Demo use": "QA transparency for multi-scene aggregation",
                "Limitation": "SCL 20 m resampled to 10 m",
            },
            {
                "Layer": "BC VRI",
                "Source": "DataBC WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY",
                "Status": vri_status,
                "Demo use": "Stand height, crown closure in forested segments",
                "Limitation": "Sparse urban coverage",
            },
            {
                "Layer": "Landsat / MODIS LST",
                "Source": "USGS Landsat C2 + NASA MOD11A1",
                "Status": lst_status,
                "Demo use": "Land surface temperature / heat stress proxy",
                "Limitation": "30 m–1 km; coarser than Planet LST 100 m",
            },
            {
                "Layer": "LidarBC / City of Surrey LiDAR",
                "Source": "portal.lidarbc.ca + data.surrey.ca LiDAR 2022",
                "Status": lidar_status,
                "Demo use": "Canopy height, DSM/DEM structure (planned)",
                "Limitation": "Provincial LidarBC sparse in Surrey",
            },
            {
                "Layer": "Synthetic vegetation proxy",
                "Source": "demo_corridors.csv forest/historical scores",
                "Status": _synthetic_vegetation_status_badge(
                    free_data_active=free_data_active,
                    planet_active=planet_active,
                ),
                "Demo use": "Fallback when open/free or Planet layers unavailable",
                "Limitation": "Not LiDAR, patrol, or treatment records",
            },
            {
                "Layer": "Planet sample",
                "Source": "Placeholder or purchased Planet summary CSV",
                "Status": _planet_layer_status_badge(planet_status),
                "Demo use": "Surrey PoC vegetation/canopy/drought scores when enabled",
                "Limitation": "Commercial PoC scope; not operational BC Hydro feed",
            },
            {
                "Layer": "BC Hydro internal",
                "Source": "Internal outage history, feeders, assets, vegetation WM",
                "Status": "🔴 Not available",
                "Demo use": "Required for formal PoC calibration",
                "Limitation": "Not in public demo",
            },
        ]
    )


def _render_surrey_pilot_context_expander(
    *,
    pilot_outages: pd.DataFrame,
    json_provenance: DatasetProvenance,
    mun_row: pd.Series | None,
) -> None:
    with st.expander("Why Surrey & live outage context", expanded=False):
        st.markdown(
            """
            - **Pilot geography** — Surrey is a large Lower Mainland municipality with mixed urban–suburban ROW
              and tree exposure.
            - **Lower Mainland focus** — aligns with BC Hydro transmission demo corridors and public outage visibility.
            - **Public data availability** — live outage JSON/RSS, unofficial archive snapshots, ECCC weather, and
              open transmission geometry support a concept PoC without internal feeds.
            """
        )
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


def _render_data_sources_assumptions_tab(
    *,
    weather_result: WeatherLoadResult,
    json_provenance: DatasetProvenance,
    outages_json_df: pd.DataFrame,
    pilot_outages: pd.DataFrame,
    mun_row: pd.Series | None,
) -> None:
    st.subheader("Data sources & assumptions")
    st.markdown(
        """
        **How to read this tab**

        - **Layer inventory** — single consolidated view of every demo layer with live status.
        - **Source catalog** — canonical reference from `src/data_sources.py` (URLs and classifications).
        - **Planet commercial data** — Surrey PoC AOI, products, and quote questions.

        Legend: 🟢 live/loaded · 🟦 open/free processed · 🟡 demo/synthetic/fallback · 🔴 unavailable.
        Weather rows and tables: **Risk Dashboard** (storm summary + weather expander).
        """
    )

    planet_result = load_planet_surrey_sample(DEMO_DATA_MODE)

    st.subheader("Layer inventory")
    st.dataframe(
        _build_unified_layer_inventory_table(
            weather_result=weather_result,
            json_provenance=json_provenance,
            outages_json_df=outages_json_df,
            mun_row=mun_row,
            planet_status=planet_result.status,
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Open/free pipeline: docs/open_free_data_for_surrey.md and docs/free_data_pipeline_runbook.md."
    )

    _render_surrey_pilot_context_expander(
        pilot_outages=pilot_outages,
        json_provenance=json_provenance,
        mun_row=mun_row,
    )

    st.subheader("Source catalog")
    st.dataframe(pd.DataFrame(DATA_SOURCES), width="stretch", hide_index=True)

    _render_data_sources_planet_section()

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
        - Vegetation exposure is a **proxy score** when Planet is off — not LiDAR, patrol, or treatment records.
        - Sentinel-2 and WorldCover layers are **proof-of-process** — suitable for discovery, not operational use.
        """
    )


def _render_data_sources_planet_section() -> None:
    """Planet commercial PoC request — products, AOI, quote questions (Data Sources tab)."""
    st.subheader("Planet commercial data (Surrey PoC)")
    st.info(PLANET_POC_DISCLAIMER)
    planet_result = load_planet_surrey_sample(DEMO_DATA_MODE)
    st.caption(
        f"Demo data mode: **{DEMO_DATA_MODE}** · Planet sample file: **{planet_result.status}** — "
        f"{planet_result.detail}"
    )

    with st.expander("Recommended sample purchase & AOI options", expanded=True):
        st.markdown(
            """
            - **Preferred AOI:** Surrey transmission corridor buffer — **200 m**, **~3,580 ha**
            - **Low-cost option:** 100 m buffer, 1,873 ha
            - **Larger option:** 300 m buffer, 5,239 ha
            - **Alternative:** outage-prone sub-area, 3,859 ha
            - **Not recommended first:** municipal boundary, 36,475 ha
            """
        )
        st.caption(
            "The 200 m corridor buffer balances infrastructure exposure, sample cost, and tests for "
            "vegetation exposure, canopy structure, heat/drought stress, and corridor ranking."
        )
        st.dataframe(_surrey_aoi_comparison_df(), width="stretch", hide_index=True)

    with st.expander("Requested Planet products (PoC scope)"):
        st.markdown(
            """
            - **Forest Carbon Monitoring** — canopy cover and canopy height (3 m, quarterly)
            - **Soil Water Content** — 100 m preferred
            - **Land Surface Temperature** — 100 m preferred
            - **ARPS or PlanetScope-derived** vegetation condition indicators
            - **Greenness/dryness** or green/brown/non-vegetation indicators (derived analytics)
            - **Temporal change** — canopy and vegetation condition vs historical
            """
        )
        st.caption(
            "No standalone Planet catalog product named “Vegetation Cover”; request green/brown "
            "indicators as derived analytics from ARPS, PlanetScope, or Area Monitoring."
        )

    with st.expander("How Planet data improves the demo model"):
        st.dataframe(_surrey_planet_model_improvement_df(), width="stretch", hide_index=True)

    with st.expander("What Planet data does not replace"):
        st.markdown(
            """
            - BC Hydro internal outage history, feeder/circuit topology, asset condition
            - Vegetation treatment records, work management, restoration/crew response data
            - Customer interruption metrics (SAIDI, SAIFI, CAIDI)

            Planet strengthens the vegetation and environmental exposure layer; Fujitsu still integrates
            weather, outage, network, and operational data for decision support.
            """
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

    st.markdown("**Sidebar data modes (Planet-related)**")
    st.markdown(
        """
        - **Public/proxy only** — ECCC weather, public outage feeds, open/free WorldCover and Sentinel-2
          when built; synthetic vegetation fallback on demo corridors.
        - **Planet sample enabled** — Loads placeholder or purchased Planet summary CSV for Surrey AOI
          vegetation scores (see `src/planet_loader.py`).
        - **Synthetic fallback** — Bundled demo CSVs; Planet sample not loaded.
        """
    )
    st.success(
        "**Recommended next action** — Ask Planet for a quote for the Surrey 200 m transmission corridor "
        "buffer (~3,580 ha) with FCM canopy cover/height, SWC 100 m, LST 100 m, and ARPS/PlanetScope-derived "
        "vegetation indicators; use delivery to replace synthetic vegetation scores and test corridor ranking."
    )
    st.caption("Detailed request draft: `docs/planet_surrey_data_request.md`.")


def _surrey_poc_tab() -> None:
    st.subheader("Surrey PoC Sample")
    st.caption(
        f"Demo region: **{st.session_state.demo_region}** · Data mode: **{DEMO_DATA_MODE}** · "
        f"Planet sample: **{_planet_sample_status_label()}**"
    )
    _render_surrey_open_free_satellite_section()
    st.caption(
        "Full layer inventory (live status, open/free, Planet, internal gaps): "
        "**Data Sources & Assumptions** tab."
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
    if DEMO_DATA_MODE == "Public/proxy only":
        st.caption(
            "In Public/proxy mode, vegetation exposure and dryness may use open/free WorldCover "
            "and Sentinel-2 processed layers when available."
        )
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
    _surrey_poc_tab()

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
    _ds_weather = _load_weather()
    _ds_outages_json = load_outages_json_cached(LIVE_PUBLIC_ONLY)
    _render_data_sources_assumptions_tab(
        weather_result=_ds_weather,
        json_provenance=provenance_from_frame(
            _ds_outages_json,
            default_label="BC Hydro outage JSON",
            default_source="not loaded",
            live_public_only=LIVE_PUBLIC_ONLY,
        ),
        outages_json_df=_ds_outages_json,
        pilot_outages=_filter_outages_for_risk_map(_ds_outages_json),
        mun_row=_surrey_municipality_outage_row(),
    )

