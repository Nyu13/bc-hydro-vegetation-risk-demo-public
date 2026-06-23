from __future__ import annotations

import os
import base64
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


def _apply_streamlit_secrets_to_env() -> None:
    try:
        for key in ("BC_HYDRO_SSL_VERIFY", "DEMO_OFFLINE_MODE"):
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except Exception:  # noqa: BLE001
        pass


_apply_streamlit_secrets_to_env()

from src.config import (
    DEMO_OFFLINE_MODE,
    DEMO_PRIMARY_DISCLAIMER,
    OKANAGAN_FWI_SAMPLE_CSV,
    OKANAGAN_PLANNING_DATASET_CSV,
    OKANAGAN_PLANNING_DISCLAIMER,
    OKANAGAN_WORLDCOVER_STATS_CSV,
    PROCESSED_DATA_DIR,
)
from src.cwfis_fwi import CWFIS_FWI_SOURCE_LABEL, fetch_fwi_samples
from src.okanagan_leaflet_map import MAP_HEIGHT_PX, build_okanagan_leaflet_map_html
from src.okanagan_map_layers import (
    filter_outages_for_okanagan_map,
    fwi_legend_html,
    planning_priority_legend_html,
    prepare_okanagan_outage_map_points,
)
from src.okanagan_temporal_map import (
    OKANAGAN_OUTAGE_ARCHIVE_LABEL,
    fetch_fwi_raster_for_date,
    fwi_source_caption,
    load_fires_for_date,
    load_outages_for_date,
    okanagan_map_date_bounds,
)
from src.okanagan_planning_loader import (
    OKANAGAN_LAYER_PATHS,
    WORLDCOVER_BUILD_CMD,
    load_okanagan_fwi_sample,
    load_okanagan_planning_dataset,
    load_okanagan_sentinel2_corridor_stats,
    load_okanagan_sentinel2_scene_qa,
    merge_sentinel2_into_planning,
    okanagan_data_source_status,
)
from src.outage_loader import bchydro_fetch_error, load_bchydro_outage_json
from src.regions import (
    OKANAGAN_BC_HYDRO_REGION,
    OKANAGAN_HISTORY_START_DATE,
    OKANAGAN_REGION_NAME,
)
from src.theme_ui import apply_streamlit_theme
from src.visualization import apply_plotly_chart_theme

LIVE_PUBLIC_ONLY = True

st.set_page_config(
    page_title="BC Hydro Okanagan Vegetation-Wildfire Planning Demo",
    layout="wide",
)

if "ui_theme_radio" not in st.session_state:
    st.session_state.ui_theme_radio = "Light"

with st.sidebar:
    st.radio(
        "Display theme",
        ["Light", "Dark"],
        horizontal=True,
        key="ui_theme_radio",
    )

apply_streamlit_theme(st.session_state.ui_theme_radio)
_chart_dark = st.session_state.ui_theme_radio == "Dark"

st.title("BC Hydro Okanagan Vegetation-Wildfire Planning Demo")
st.warning(DEMO_PRIMARY_DISCLAIMER)
if DEMO_OFFLINE_MODE:
    st.caption("Offline mode — bundled demo CSVs.")


@st.cache_data(show_spinner=False)
def load_outages_json_cached(live_public_only: bool) -> pd.DataFrame:
    return load_bchydro_outage_json(allow_synthetic_fallback=not live_public_only)


BC_HYDRO_VEG_STORY_CAPTION = (
    "Public satellite layers (WorldCover land cover + Sentinel-2 NDVI/NDMI) provide corridor-level "
    "vegetation context. With BC Hydro internal LiDAR, vegetation inventory, and Planet/commercial "
    "imagery, these proxies become validated planning inputs."
)


def _mean_or_none(series: pd.Series) -> float | None:
    if series.empty:
        return None
    val = series.mean()
    return float(val) if pd.notna(val) else None


def _data_status_badge(status: str | None, *, loaded: bool = True) -> str:
    if not loaded:
        return "missing"
    if not status:
        return "unknown"
    s = str(status).lower()
    if "open_free" in s or s == "computed":
        return "satellite proxy"
    if "stub" in s or "neutral" in s:
        return "placeholder"
    return str(status)


def _okanagan_vegetation_executive_summary(planning_df: pd.DataFrame) -> None:
    """Executive vegetation / satellite metrics for BC Hydro presentation."""
    st.markdown("#### Vegetation & satellite context")
    st.caption(BC_HYDRO_VEG_STORY_CAPTION)

    wc_path = OKANAGAN_WORLDCOVER_STATS_CSV
    s2_path = PROCESSED_DATA_DIR / "okanagan_sentinel2_corridor_stats.csv"
    wc_loaded = wc_path.is_file()
    s2_loaded = s2_path.is_file()

    mean_tree = _mean_or_none(planning_df["worldcover_tree_pct"]) if "worldcover_tree_pct" in planning_df.columns else None
    mean_built = _mean_or_none(planning_df["worldcover_built_pct"]) if "worldcover_built_pct" in planning_df.columns else None
    mean_ndvi = _mean_or_none(planning_df["sentinel2_ndvi_mean"]) if "sentinel2_ndvi_mean" in planning_df.columns else None
    mean_ndmi = _mean_or_none(planning_df["sentinel2_ndmi_mean"]) if "sentinel2_ndmi_mean" in planning_df.columns else None
    mean_dryness = (
        _mean_or_none(planning_df["vegetation_dryness_score"])
        if "vegetation_dryness_score" in planning_df.columns
        else None
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric(
        "Mean tree cover (WorldCover)",
        f"{mean_tree:.1f}%" if mean_tree is not None else "—",
        help="ESA WorldCover 2021 — % tree class in corridor segment buffers (static proxy).",
    )
    metric_cols[1].metric(
        "Mean built-up (WorldCover)",
        f"{mean_built:.1f}%" if mean_built is not None else "—",
        help="ESA WorldCover 2021 — % built-up class (urban / developed proxy).",
    )
    metric_cols[2].metric(
        "Mean NDVI (Sentinel-2)",
        f"{mean_ndvi:.3f}" if mean_ndvi is not None else "—",
        help="Sentinel-2 L2A greenness index — higher = more active vegetation.",
    )
    metric_cols[3].metric(
        "Mean NDMI (Sentinel-2)",
        f"{mean_ndmi:.3f}" if mean_ndmi is not None else "—",
        help="Sentinel-2 L2A moisture index — lower = drier canopy / stress proxy.",
    )
    metric_cols[4].metric(
        "Mean dryness score",
        f"{mean_dryness:.1f}" if mean_dryness is not None else "—",
        help="Derived proxy 0–100 from NDMI — higher = drier (not field moisture).",
    )

    veg_status = None
    if "vegetation_data_status" in planning_df.columns and planning_df["vegetation_data_status"].notna().any():
        veg_status = str(planning_df["vegetation_data_status"].dropna().iloc[0])
    wc_status = "open_free_processed" if wc_loaded else "missing"
    s2_status = "open_free_processed" if s2_loaded else "missing"
    if s2_loaded:
        try:
            s2_df = pd.read_csv(s2_path, usecols=["data_status"], nrows=5)
            if not s2_df.empty and s2_df["data_status"].notna().any():
                s2_status = str(s2_df["data_status"].iloc[0])
        except Exception:  # noqa: BLE001
            pass

    badge_cols = st.columns(3)
    wc_badge = _data_status_badge(wc_status, loaded=wc_loaded)
    if not wc_loaded:
        wc_badge = f"{wc_badge} — run: `{WORLDCOVER_BUILD_CMD}`"
    badge_cols[0].caption(f"**WorldCover:** {wc_badge}")
    badge_cols[1].caption(f"**Sentinel-2:** {_data_status_badge(s2_status, loaded=s2_loaded)}")
    badge_cols[2].caption(f"**Vegetation score:** {_data_status_badge(veg_status, loaded=not planning_df.empty)}")


def _okanagan_satellite_vegetation_section(planning_df: pd.DataFrame) -> None:
    """Compact Sentinel-2 L2A summary for the planning tab."""
    st.markdown("#### Satellite vegetation (Sentinel-2 L2A)")
    qa = load_okanagan_sentinel2_scene_qa()
    s2_stats = load_okanagan_sentinel2_corridor_stats()
    l2a_dir = PROCESSED_DATA_DIR.parent / "raw" / "okanagan" / "L2A"
    product_count = len(list(l2a_dir.glob("*.zip"))) if l2a_dir.is_dir() else None

    if qa.empty and s2_stats.empty and not product_count:
        st.info(
            "Sentinel-2 corridor stats not built yet. Run "
            "`python TMP/scripts/build_okanagan_sentinel2_indices.py` (or the full Okanagan pipeline)."
        )
        return

    processed_scenes = int((qa["status"] == "processed").sum()) if not qa.empty and "status" in qa.columns else None
    total_qa_rows = len(qa) if not qa.empty else None
    date_min = date_max = None
    if not qa.empty and "sensing_date" in qa.columns:
        dates = pd.to_datetime(qa["sensing_date"], errors="coerce").dropna()
        if not dates.empty:
            date_min = dates.min().date().isoformat()
            date_max = dates.max().date().isoformat()

    corridor_ndvi = corridor_ndmi = None
    if not planning_df.empty:
        if "sentinel2_ndvi_mean" in planning_df.columns:
            corridor_ndvi = planning_df["sentinel2_ndvi_mean"].mean()
        if "sentinel2_ndmi_mean" in planning_df.columns:
            corridor_ndmi = planning_df["sentinel2_ndmi_mean"].mean()

    metric_cols = st.columns(4)
    if processed_scenes is not None:
        metric_cols[0].metric("Scenes processed", processed_scenes)
    elif not s2_stats.empty and "scenes_used" in s2_stats.columns:
        metric_cols[0].metric("Scenes used (corridor)", int(s2_stats["scenes_used"].iloc[0]))
    else:
        metric_cols[0].metric("Scenes processed", "—")

    if date_min and date_max:
        metric_cols[1].metric("Sensing date range", f"{date_min} → {date_max}")
    else:
        metric_cols[1].metric("Sensing date range", "—")

    metric_cols[2].metric(
        "Mean corridor NDVI",
        f"{corridor_ndvi:.3f}" if corridor_ndvi is not None and pd.notna(corridor_ndvi) else "—",
    )
    metric_cols[3].metric(
        "Mean corridor NDMI",
        f"{corridor_ndmi:.3f}" if corridor_ndmi is not None and pd.notna(corridor_ndmi) else "—",
    )

    notes: list[str] = [
        "Open/free **Sentinel-2 L2A** products processed locally (NDVI / NDMI with SCL cloud mask)."
    ]
    if product_count:
        notes.append(f"Aggregated from **{product_count}** L2A products in `data/raw/okanagan/L2A`.")
    if total_qa_rows and processed_scenes is not None and total_qa_rows > processed_scenes:
        skipped = total_qa_rows - processed_scenes
        notes.append(f"{skipped} scene(s) skipped (no clear pixels after cloud mask).")
    st.caption(" ".join(notes))

    with st.expander("Top segments by satellite NDVI", expanded=False):
        ndvi_cols = [
            c
            for c in (
                "segment_id",
                "corridor_id",
                "sentinel2_ndvi_mean",
                "sentinel2_ndmi_mean",
                "cloud_filtered_pct",
                "worldcover_tree_pct",
                "vegetation_score",
                "planning_priority_level",
            )
            if c in planning_df.columns
        ]
        if "sentinel2_ndvi_mean" in planning_df.columns:
            top_ndvi = planning_df.sort_values("sentinel2_ndvi_mean", ascending=False).head(10)
            st.dataframe(top_ndvi[ndvi_cols], width="stretch", hide_index=True)
        else:
            st.caption("NDVI columns not present in planning dataset.")


def _okanagan_vegetation_drivers_section(planning_df: pd.DataFrame) -> None:
    """WorldCover composition, Sentinel-2 stress, and dryness derivation."""
    st.markdown("#### Vegetation drivers (public satellite proxies)")
    if planning_df.empty:
        st.info("Planning dataset empty — run the Okanagan pipeline.")
        return

    comp_cols = [
        c
        for c in (
            "worldcover_tree_pct",
            "worldcover_shrub_grass_pct",
            "worldcover_built_pct",
            "worldcover_bare_pct",
        )
        if c in planning_df.columns
    ]
    if comp_cols:
        means = planning_df[comp_cols].mean().round(1).reset_index()
        means.columns = ["land_cover_class", "mean_pct"]
        means["land_cover_class"] = means["land_cover_class"].str.replace("worldcover_", "").str.replace("_pct", "")
        fig_wc = px.bar(
            means,
            x="land_cover_class",
            y="mean_pct",
            title="Mean WorldCover composition across corridor segments (%)",
            labels={"land_cover_class": "Land cover class", "mean_pct": "Mean %"},
        )
        apply_plotly_chart_theme(fig_wc, dark=_chart_dark)
        st.plotly_chart(fig_wc, width="stretch")

    s2_cols = [c for c in ("sentinel2_ndvi_mean", "sentinel2_ndmi_mean") if c in planning_df.columns]
    if s2_cols:
        s2_means = planning_df[s2_cols].mean().round(3).reset_index()
        s2_means.columns = ["index", "mean_value"]
        s2_means["index"] = s2_means["index"].map(
            {
                "sentinel2_ndvi_mean": "NDVI (greenness)",
                "sentinel2_ndmi_mean": "NDMI (moisture)",
            }
        )
        fig_s2 = px.bar(
            s2_means,
            x="index",
            y="mean_value",
            title="Mean Sentinel-2 vegetation indices (corridor segments)",
            labels={"index": "Index", "mean_value": "Mean value"},
        )
        apply_plotly_chart_theme(fig_s2, dark=_chart_dark)
        st.plotly_chart(fig_s2, width="stretch")

    st.caption(
        "**Dryness score (proxy):** `dryness = clip((0.4 − NDMI) / 0.8 × 100, 0, 100)` — "
        "lower NDMI (drier canopy) raises the score. "
        "**Vegetation score** blends exposure (WorldCover tree %), dryness, and NDVI greenness."
    )
    if "vegetation_change_score" in planning_df.columns:
        change_mean = planning_df["vegetation_change_score"].mean()
        if pd.notna(change_mean):
            st.caption(
                f"**Change signal (proxy):** mean vegetation change score {change_mean:.1f}/100 "
                "from Sentinel-2 NDVI shift (latest vs earliest scene in period)."
            )


def _okanagan_outage_place_count() -> int | None:
    path = PROCESSED_DATA_DIR / "okanagan_outage_proxy_summary.csv"
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, usecols=["municipality"])
        return int(df["municipality"].nunique())
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def _load_okanagan_fwi_for_map(selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    """Return FWI sample table and status label for map coloring on selected date."""
    bundled = load_okanagan_fwi_sample()
    segments_path = PROCESSED_DATA_DIR / "okanagan_corridor_segments.geojson"
    if segments_path.is_file():
        try:
            import geopandas as gpd

            segments = gpd.read_file(segments_path).to_crs(4326)
            centroids_wgs84 = (
                segments.to_crs("EPSG:3005")
                .geometry.representative_point()
                .to_crs(4326)
            )
            values, status = fetch_fwi_samples(
                None,
                centroids_wgs84.x.tolist(),
                centroids_wgs84.y.tolist(),
                auto_bbox=True,
                fallback_bbox=OKANAGAN_AOI_BBOX,
                time=selected_date_iso,
            )
            if status == "cwfis_live" and any(v is not None for v in values):
                rows = []
                for (_, seg), fwi_val in zip(segments.iterrows(), values, strict=True):
                    rows.append(
                        {
                            "segment_id": seg.get("segment_id"),
                            "fwi_value": fwi_val,
                            "data_status": status,
                            "data_source": CWFIS_FWI_SOURCE_LABEL,
                        }
                    )
                return pd.DataFrame(rows), status
        except Exception:  # noqa: BLE001
            pass

    if not bundled.empty and bundled.get("fwi_value", pd.Series(dtype=float)).notna().any():
        status = "bundled_csv"
        if "data_status" in bundled.columns:
            status = str(bundled["data_status"].dropna().iloc[0]) if bundled["data_status"].notna().any() else status
        return bundled, status
    if not segments_path.is_file():
        return bundled, "segments_missing"
    return bundled, "fetch_failed"


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_fwi_raster(selected_date_iso: str) -> tuple[bytes | None, tuple[float, float, float, float], str]:
    return fetch_fwi_raster_for_date(selected_date_iso)


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_fires_for_date(selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    return load_fires_for_date(selected_date_iso)


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_outages_for_date(selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    return load_outages_for_date(selected_date_iso)


def _okanagan_tree_contact_priority_section(df: pd.DataFrame) -> None:
    """Top-priority corridor: tree-contact proxy, problem type, and scenario scores."""
    required = {
        "problem_type",
        "risk_pathway",
        "recommended_planning_action",
        "tree_contact_exposure_proxy",
        "current_priority_score",
    }
    if df.empty or not required.issubset(df.columns):
        return

    top_row = df.sort_values("planning_priority_score", ascending=False).iloc[0]
    segment_label = str(top_row.get("segment_id", ""))
    corridor_label = str(top_row.get("corridor_id", ""))

    st.markdown("#### Why this area is prioritized")
    st.caption(f"Top priority segment: **{segment_label}** (corridor {corridor_label})")

    def _fmt(val) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        if isinstance(val, (int, float)):
            return f"{val:.1f}"
        text = str(val).strip()
        return text if text else "—"

    info_cols = st.columns(2)
    info_cols[0].markdown(f"**Problem type:** {_fmt(top_row.get('problem_type'))}")
    info_cols[0].markdown(f"**Risk pathway:** {_fmt(top_row.get('risk_pathway'))}")
    info_cols[0].markdown(f"**Recommended action:** {_fmt(top_row.get('recommended_planning_action'))}")
    info_cols[1].markdown(f"**Tree-contact exposure proxy:** {_fmt(top_row.get('tree_contact_exposure_proxy'))}")
    info_cols[1].markdown(f"**Data quality:** {_fmt(top_row.get('tree_contact_score_data_quality'))}")
    missing = top_row.get("tree_contact_missing_components")
    if missing is not None and str(missing).strip():
        info_cols[1].markdown(f"**Missing components:** {missing}")

    metric_cols = st.columns(4)
    metric_cols[0].metric("Current priority", _fmt(top_row.get("current_priority_score")))
    metric_cols[1].metric("After inspection", _fmt(top_row.get("scenario_after_inspection_score")))
    metric_cols[2].metric("After trimming", _fmt(top_row.get("scenario_after_trimming_score")))
    metric_cols[3].metric(
        "After trimming + inspection",
        _fmt(top_row.get("scenario_after_trimming_and_inspection_score")),
    )

    explanation = top_row.get("explanation_short")
    if explanation is not None and str(explanation).strip():
        st.markdown(f"_{explanation}_")

    scenario_cols = [
        "current_priority_score",
        "scenario_after_inspection_score",
        "scenario_after_trimming_score",
        "scenario_after_trimming_and_inspection_score",
    ]
    if all(c in df.columns for c in scenario_cols):
        scenario_df = pd.DataFrame(
            {
                "scenario": [
                    "Current",
                    "After inspection",
                    "After trimming",
                    "After trimming + inspection",
                ],
                "priority_score": [float(top_row[c]) for c in scenario_cols],
            }
        )
        fig = px.bar(
            scenario_df,
            x="scenario",
            y="priority_score",
            title=f"Scenario comparison — {segment_label}",
            labels={"priority_score": "Priority score", "scenario": ""},
        )
        apply_plotly_chart_theme(fig, dark=_chart_dark)
        st.plotly_chart(fig, width="stretch")
        st.caption("Scenario only — uses synthetic treatment assumptions.")


def _okanagan_planning_tab() -> None:
    st.subheader("Kelowna / Okanagan Vegetation-Wildfire Planning")
    place_count = _okanagan_outage_place_count()
    place_suffix = f" ({place_count} in bundled summary)." if place_count is not None else "."
    st.caption(
        f"Historical outage and ECCC weather proxies start **{OKANAGAN_HISTORY_START_DATE}**. "
        f"Outage archive covers **{OKANAGAN_BC_HYDRO_REGION}** places{place_suffix}"
    )

    result = load_okanagan_planning_dataset()
    if result.status != "loaded":
        st.warning(result.detail)
        st.info("Run: `python TMP/scripts/build_okanagan_demo_pipeline.py`")
        return

    df = merge_sentinel2_into_planning(result.df.copy())

    cols = st.columns(5)
    cols[0].metric("Corridor segments", len(df))
    critical = int((df["planning_priority_level"] == "Critical").sum()) if "planning_priority_level" in df.columns else 0
    high = int((df["planning_priority_level"] == "High").sum()) if "planning_priority_level" in df.columns else 0
    cols[1].metric("Critical", critical)
    cols[2].metric("High", high)
    mean_score = df["planning_priority_score"].mean() if "planning_priority_score" in df.columns else 0
    cols[3].metric("Mean priority score", f"{mean_score:.1f}" if pd.notna(mean_score) else "—")
    cols[4].metric("Region", OKANAGAN_REGION_NAME)

    _okanagan_vegetation_executive_summary(df)

    st.markdown("#### Planning map")
    min_map_date, max_map_date, default_map_date = okanagan_map_date_bounds()
    selected_map_date = st.date_input(
        "Map date (2026 archive & CWFIS layers)",
        value=default_map_date,
        min_value=min_map_date,
        max_value=max_map_date,
        help=(
            "Refreshes FWI raster, CWFIF fires, and unofficial outage archive points for the selected day. "
            f"Outage archive snapshots run through {max_map_date.isoformat()}."
        ),
    )
    selected_date_iso = selected_map_date.isoformat()

    _MAP_TOGGLE_DEFAULTS = {
        "okanagan_show_fwi_raster": False,
        "okanagan_show_segments": True,
        "okanagan_show_fires": True,
        "okanagan_show_archive_outages": True,
        "okanagan_show_tx_lines": True,
        "okanagan_show_buffer": False,
        "okanagan_show_live_outages": False,
        "okanagan_segment_color_mode": "planning_priority_score",
    }
    for key, default in _MAP_TOGGLE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default

    segment_color_mode = st.selectbox(
        "Segment color by",
        options=["planning_priority_score", "fwi"],
        format_func=lambda v: (
            "Planning priority (composite score)"
            if v == "planning_priority_score"
            else "Fire Weather Index — selected date"
        ),
        key="okanagan_segment_color_mode",
        help=(
            "Planning priority uses the static composite score (vegetation, wildfire, weather, treatment, outage). "
            "FWI colors each segment by CWFIS Fire Weather Index sampled at its centroid for the map date."
        ),
    )
    if segment_color_mode == "planning_priority_score":
        st.caption(
            "Corridor lines use **planning priority level** buckets (Critical → Low). "
            "This score is static and does not change with the map date."
        )
    else:
        st.caption(
            "Corridor lines use **dated CWFIS FWI** at each segment centroid. "
            "This is separate from the optional FWI raster overlay checkbox below."
        )
    temporal_cols = st.columns(3)
    show_fwi_raster = temporal_cols[0].checkbox(
        "Show FWI raster overlay (CWFIS)",
        key="okanagan_show_fwi_raster",
        help=(
            "Optional regional FWI heatmap under the map for the selected date. "
            "Independent of segment line coloring — you can show the raster with either color mode."
        ),
    )
    show_fires = temporal_cols[1].checkbox(
        "Show fires (selected date)",
        key="okanagan_show_fires",
    )
    show_archive_outages = temporal_cols[2].checkbox(
        "Show outages (archive, selected date)",
        key="okanagan_show_archive_outages",
    )

    map_cols = st.columns(4)
    show_tx_lines = map_cols[0].checkbox(
        "Show BC transmission lines",
        key="okanagan_show_tx_lines",
    )
    show_buffer = map_cols[1].checkbox(
        "Show corridor buffer (200 m)",
        key="okanagan_show_buffer",
    )
    show_segments = map_cols[2].checkbox(
        "Show corridor segments",
        key="okanagan_show_segments",
    )
    live_outage_col = st.columns(1)[0]
    show_live_outages = live_outage_col.checkbox(
        "Show outages (live BC Hydro JSON)",
        key="okanagan_show_live_outages",
    )

    if segment_color_mode == "fwi" and not show_segments:
        st.info(
            "Segment FWI coloring needs **Show corridor segments** enabled. "
            "Turn it on to color corridor lines by Fire Weather Index."
        )

    fwi_raster_status = ""
    fires_status = ""
    archive_outage_status = ""
    fires_df = pd.DataFrame()
    archive_outage_points = pd.DataFrame()
    png_bytes: bytes | None = None
    raster_bbox: tuple[float, float, float, float] | None = None

    if show_fwi_raster:
        png_bytes, raster_bbox, fwi_raster_status = _cached_fwi_raster(selected_date_iso)

    fwi_df = pd.DataFrame()
    fwi_status = ""
    if show_segments and segment_color_mode == "fwi":
        fwi_df, fwi_status = _load_okanagan_fwi_for_map(selected_date_iso)

    if show_fires:
        fires_df, fires_status = _cached_fires_for_date(selected_date_iso)

    if show_archive_outages:
        archive_outage_points, archive_outage_status = _cached_outages_for_date(selected_date_iso)

    outage_points = pd.DataFrame()
    outage_total = 0
    outage_is_synthetic = False
    if show_live_outages:
        outages_raw = load_outages_json_cached(LIVE_PUBLIC_ONLY)
        outage_total = len(outages_raw)
        outage_is_synthetic = bool(
            outages_raw.get("is_synthetic", pd.Series(dtype=bool)).any()
        ) if not outages_raw.empty else False
        okanagan_outages = filter_outages_for_okanagan_map(outages_raw)
        outage_points = prepare_okanagan_outage_map_points(okanagan_outages)
        if show_live_outages and outage_total == 0:
            fetch_err = bchydro_fetch_error()
            if fetch_err:
                st.caption(f"Public outage feed unavailable: {fetch_err}")

    map_html = build_okanagan_leaflet_map_html(
        selected_date_iso=selected_date_iso,
        show_fwi_raster=show_fwi_raster,
        fwi_png_base64=base64.b64encode(png_bytes).decode("ascii") if png_bytes else None,
        fwi_bbox=raster_bbox,
        show_tx_lines=show_tx_lines,
        show_buffer=show_buffer,
        show_segments=show_segments,
        segment_color_mode=segment_color_mode,
        planning_df=df,
        fwi_df=fwi_df,
        fires_df=fires_df,
        archive_outages_df=archive_outage_points,
        live_outages_df=outage_points if show_live_outages else pd.DataFrame(),
        live_outages_synthetic=outage_is_synthetic,
    )
    st.iframe(map_html, height=MAP_HEIGHT_PX)

    st.caption(
        f"**Selected date:** {selected_date_iso} — "
        f"{fwi_source_caption(selected_date_iso)}; "
        f"fires from CWFIF WFS; outages from {OKANAGAN_OUTAGE_ARCHIVE_LABEL}."
    )
    fwi_active = show_fwi_raster or (segment_color_mode == "fwi" and show_segments)
    if segment_color_mode == "planning_priority_score" and show_segments:
        st.markdown(planning_priority_legend_html(), unsafe_allow_html=True)
    elif fwi_active:
        st.markdown(
            fwi_legend_html(continuous=segment_color_mode == "fwi" and show_segments),
            unsafe_allow_html=True,
        )
    if show_fwi_raster:
        if fwi_raster_status == "cwfis_live":
            st.success(f"FWI raster loaded for {selected_date_iso}.")
        elif fwi_raster_status == "fetch_failed":
            st.warning(
                f"CWFIS FWI raster unavailable for {selected_date_iso}. "
                "Try another date or check network access to cwfis.cfs.nrcan.gc.ca."
            )
    if show_fires and fires_df.empty:
        if fires_status == "fetch_failed":
            st.caption("CWFIF fire layer unavailable — check network access.")
        elif fires_status in {"no_fires", "no_fires_in_aoi"}:
            st.caption(f"No BC wildland fires in the Okanagan AOI on {selected_date_iso}.")
    elif show_fires and not fires_df.empty:
        st.caption(
            f"Showing **{len(fires_df)}** BC wildland fire(s) active on **{selected_date_iso}** "
            "(red circles — click for details)."
        )
    if show_archive_outages and archive_outage_points.empty:
        if archive_outage_status == "archive_missing":
            st.caption(
                "Outage archive parquet not found — copy bchydro_public_outages_history.parquet "
                "to data/processed/ or set EXTRACTOR_OUTPUT_DIR."
            )
        elif archive_outage_status.startswith("snapshot_nearest"):
            st.caption(
                f"No exact outage snapshot on {selected_date_iso} ({archive_outage_status.replace('_', ' ')})."
            )
        elif archive_outage_status not in {"", "snapshot_exact"}:
            st.caption(f"No outage archive points for {selected_date_iso} ({archive_outage_status}).")

    _okanagan_satellite_vegetation_section(df)

    if show_tx_lines:
        st.caption(
            "Transmission lines: province-wide BC Geographic Warehouse overlay. "
            "Corridor segments, buffers, and planning scores remain Okanagan-only."
        )

    fwi_valid = (
        int(fwi_df["fwi_value"].notna().sum())
        if not fwi_df.empty and "fwi_value" in fwi_df.columns
        else 0
    )
    if segment_color_mode == "fwi" and show_segments and fwi_valid == 0:
        if fwi_status == "fetch_failed":
            st.warning(
                "CWFIS FWI fetch failed — check network access to cwfis.cfs.nrcan.gc.ca. "
                "Bundled sample may be stale; run `python TMP/scripts/build_okanagan_fwi_sample.py`."
            )
        elif fwi_status == "no_valid_samples":
            st.warning(
                "CWFIS returned no valid FWI samples for corridor centroids. "
                "Run `python TMP/scripts/build_okanagan_fwi_sample.py` to refresh."
            )
        else:
            st.warning(
                "FWI layer missing or empty — run `python TMP/scripts/build_okanagan_fwi_sample.py` "
                "or the full Okanagan pipeline."
            )
    elif segment_color_mode == "fwi" and show_segments and fwi_valid > 0:
        fwi_date_note = ""
        if "as_of_date" in fwi_df.columns and fwi_df["as_of_date"].notna().any():
            as_of = str(fwi_df["as_of_date"].dropna().iloc[0])
            if as_of != selected_date_iso and fwi_status == "bundled_csv":
                fwi_date_note = (
                    f" Using bundled snapshot from **{as_of}** (live CWFIS fetch unavailable for {selected_date_iso})."
                )
        st.caption(
            f"CWFIS FWI colors **{fwi_valid}** corridor segment(s) for **{selected_date_iso}**.{fwi_date_note} "
            "Values vary along the corridor by local weather/fire danger — not the composite planning score."
        )

    st.markdown("#### Top corridor segments")
    display_cols = [
        c
        for c in (
            "segment_id",
            "corridor_id",
            "length_km",
            "planning_priority_score",
            "planning_priority_level",
            "problem_type",
            "tree_contact_exposure_proxy",
            "recommended_planning_action",
            "risk_pathway",
            "sentinel2_ndvi_mean",
            "sentinel2_ndmi_mean",
            "worldcover_tree_pct",
            "worldcover_built_pct",
            "vegetation_dryness_score",
            "vegetation_score",
            "wildfire_exposure_score",
            "eccc_weather_stress_score",
            "treatment_gap_score",
            "outage_history_proxy_score",
            "top_reason_1",
        )
        if c in df.columns
    ]
    top = df.sort_values("planning_priority_score", ascending=False).head(15)
    st.dataframe(top[display_cols], width="stretch", hide_index=True)

    _okanagan_tree_contact_priority_section(df)

    st.markdown("#### Score breakdown (component means)")
    comp_cols = [
        c
        for c in (
            "vegetation_score",
            "wildfire_exposure_score",
            "eccc_weather_stress_score",
            "treatment_gap_score",
            "outage_history_proxy_score",
            "terrain_score",
        )
        if c in df.columns
    ]
    if comp_cols:
        breakdown = df[comp_cols].mean().round(1).reset_index()
        breakdown.columns = ["component", "mean_score"]
        fig = px.bar(breakdown, x="component", y="mean_score", title="Mean component scores (0–100)")
        apply_plotly_chart_theme(fig, dark=_chart_dark)
        st.plotly_chart(fig, width="stretch")

    _okanagan_vegetation_drivers_section(df)


def _render_okanagan_overview() -> None:
    st.markdown("### What this demo shows")
    st.markdown(
        """
        - **Vegetation-wildfire planning workflow** — corridor segments ranked by composite exposure
        - **Public layer stack** — WorldCover land cover, Sentinel-2 NDVI/NDMI, CWFIS wildfire, ECCC weather stress, outage archive proxy
        - **Satellite vegetation context** — tree cover, moisture stress, and dryness proxies at corridor level (validated with BC Hydro LiDAR / Planet in production)
        - **Treatment gap placeholder** — synthetic scores show where BC Hydro work-management data would plug in
        - **Transparent proxy scoring** — component breakdown and top reasons per corridor segment
        """
    )
    st.markdown("### What this demo does not show")
    st.markdown(
        """
        - **Outage prediction** — planning prioritization only, not storm or outage forecasting
        - **Validated wildfire or vegetation treatment prioritization** — scores are illustrative composites
        - **BC Hydro internal GIS, SAIDI/SAIFI, or patrol records** — public/proxy layers only
        - **Real-time operational dispatch** — planning-oriented view, not control-room tooling
        """
    )
    st.info(
        "Open **Kelowna / Okanagan Planning** for corridor priority maps and component scores. "
        "See **Data Sources & Assumptions** for the BC Hydro internal data replacement table."
    )


def _okanagan_artifact_status(label: str, path: Path) -> str:
    if path.name == OKANAGAN_WORLDCOVER_STATS_CSV.name:
        if path.is_file():
            return "loaded"
        return f"missing — run: {WORLDCOVER_BUILD_CMD}"
    return "loaded" if path.is_file() else "missing — run pipeline"


def _okanagan_layer_inventory_df() -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for layer_key, path in OKANAGAN_LAYER_PATHS.items():
        rows.append(
            {
                "Layer": layer_key.replace("_", " ").title(),
                "Artifact": path.name,
                "Status": _okanagan_artifact_status(layer_key.replace("_", " ").title(), path),
            }
        )
    for label, path in (
        ("WorldCover stats", OKANAGAN_WORLDCOVER_STATS_CSV),
        ("Sentinel-2 stats", PROCESSED_DATA_DIR / "okanagan_sentinel2_corridor_stats.csv"),
        ("Corridor buffer 200 m", PROCESSED_DATA_DIR / "okanagan_corridor_buffer_200m.geojson"),
        ("CWFIS FWI sample", OKANAGAN_FWI_SAMPLE_CSV),
        ("Treatment gap", PROCESSED_DATA_DIR / "okanagan_synthetic_treatment_gap.csv"),
        ("Planning dataset", OKANAGAN_PLANNING_DATASET_CSV),
        ("Weather stress daily", PROCESSED_DATA_DIR / "okanagan_weather_stress_daily.csv"),
        ("Outage daily proxy", PROCESSED_DATA_DIR / "okanagan_outage_daily_proxy.csv"),
    ):
        if any(r["Artifact"] == path.name for r in rows):
            continue
        rows.append(
            {
                "Layer": label,
                "Artifact": path.name,
                "Status": _okanagan_artifact_status(label, path),
            }
        )
    return pd.DataFrame(rows)


def _render_okanagan_data_sources_tab() -> None:
    st.subheader("Data sources & assumptions")
    st.caption(OKANAGAN_PLANNING_DISCLAIMER)
    st.markdown("#### Okanagan layer inventory")
    st.dataframe(_okanagan_layer_inventory_df(), width="stretch", hide_index=True)
    st.markdown("#### BC Hydro internal data replacement")
    st.dataframe(okanagan_data_source_status(), width="stretch", hide_index=True)
    st.markdown("#### Assumptions and limitations")
    st.markdown(
        f"""
        - Outage history uses unofficial archive proxy for **{OKANAGAN_BC_HYDRO_REGION}** (from {OKANAGAN_HISTORY_START_DATE}).
        - Weather stress uses ECCC MSC GeoMet near Kelowna.
        - Wildfire exposure uses CWFIS WFS when available; synthetic fallback otherwise.
        - **Fire Weather Index (FWI)** from CWFIS WCS — segment coloring only, not operational.
        - Treatment gap scores are **synthetic** — placeholders for work-management records.
        - **Transmission lines** — province-wide BC Geographic Warehouse overlay; corridor segments and planning scores are Okanagan-only.
        """
    )


tab_overview, tab_planning, tab_sources = st.tabs(
    ["Overview", "Kelowna / Okanagan Planning", "Data Sources & Assumptions"]
)

with tab_overview:
    _render_okanagan_overview()

with tab_planning:
    _okanagan_planning_tab()

with tab_sources:
    _render_okanagan_data_sources_tab()
