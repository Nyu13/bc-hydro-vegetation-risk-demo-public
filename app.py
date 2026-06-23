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
    PROCESSED_DATA_DIR,
)
from src.cwfis_fwi import CWFIS_FWI_SOURCE_LABEL, fetch_fwi_samples
from src.okanagan_leaflet_map import MAP_HEIGHT_PX, build_okanagan_leaflet_map_html
from src.okanagan_map_layers import (
    filter_outages_for_region_map,
    fwi_legend_html,
    planning_priority_legend_html,
    tree_contact_legend_html,
    prepare_okanagan_outage_map_points,
)
from src.okanagan_temporal_map import (
    OKANAGAN_OUTAGE_ARCHIVE_LABEL,
    fetch_fwi_raster_for_date,
    fwi_source_caption,
    load_fires_for_date,
    load_outages_for_date,
    map_date_bounds,
)
from src.okanagan_planning_loader import (
    load_okanagan_planning_dataset,
    load_okanagan_sentinel2_corridor_stats,
    load_okanagan_sentinel2_scene_qa,
    merge_sentinel2_into_planning,
    okanagan_data_source_status,
)
from src.outage_loader import bchydro_fetch_error, load_bchydro_outage_json
from src.planning_regions import (
    PLANNING_REGION_OPTIONS,
    PLANNING_REGIONS,
    PlanningRegionConfig,
    OKANAGAN_REGION,
)
from src.surrey_planning_loader import (
    load_surrey_planning_dataset,
    load_surrey_sentinel2_corridor_stats,
    load_surrey_sentinel2_scene_qa,
    merge_sentinel2_into_surrey_planning,
    surrey_causal_ai_summary,
)
from src.theme_ui import apply_streamlit_theme
from src.visualization import apply_plotly_chart_theme

LIVE_PUBLIC_ONLY = True

st.set_page_config(
    page_title="BC Hydro Vegetation-Wildfire Planning Demo",
    layout="wide",
)

if "ui_theme_radio" not in st.session_state:
    st.session_state.ui_theme_radio = "Light"
if "demo_region_key" not in st.session_state:
    st.session_state.demo_region_key = OKANAGAN_REGION.key

with st.sidebar:
    region_labels = {key: label for key, label in PLANNING_REGION_OPTIONS}
    st.selectbox(
        "Demo region",
        options=list(region_labels.keys()),
        format_func=lambda key: region_labels[key],
        key="demo_region_key",
    )
    st.radio(
        "Display theme",
        ["Light", "Dark"],
        horizontal=True,
        key="ui_theme_radio",
    )

active_region = PLANNING_REGIONS[st.session_state.demo_region_key]

apply_streamlit_theme(st.session_state.ui_theme_radio)
_chart_dark = st.session_state.ui_theme_radio == "Dark"

st.title(f"BC Hydro {active_region.label} Vegetation-Wildfire Planning Demo")
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


def _outage_place_count(region: PlanningRegionConfig) -> int | None:
    path = region.outage_place_summary_csv
    if path is None or not path.is_file():
        return None
    try:
        df = pd.read_csv(path, usecols=["municipality"])
        return int(df["municipality"].nunique())
    except Exception:  # noqa: BLE001
        return None


def _load_planning_dataset(region: PlanningRegionConfig, planning_csv: Path):
    if region.key == "surrey":
        return load_surrey_planning_dataset(planning_csv)
    return load_okanagan_planning_dataset(planning_csv)


def _merge_sentinel2(region: PlanningRegionConfig, planning_df: pd.DataFrame) -> pd.DataFrame:
    if region.key == "surrey":
        return merge_sentinel2_into_surrey_planning(planning_df)
    return merge_sentinel2_into_planning(planning_df)


def _vegetation_executive_summary(region: PlanningRegionConfig, planning_df: pd.DataFrame) -> None:
    """Executive vegetation / satellite metrics for BC Hydro presentation."""
    st.markdown("#### Vegetation & satellite context")
    st.caption(BC_HYDRO_VEG_STORY_CAPTION)

    wc_path = region.worldcover_stats_csv
    s2_path = region.sentinel2_stats_csv
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
        wc_badge = f"{wc_badge} — run: `{region.worldcover_build_cmd}`"
    badge_cols[0].caption(f"**WorldCover:** {wc_badge}")
    badge_cols[1].caption(f"**Sentinel-2:** {_data_status_badge(s2_status, loaded=s2_loaded)}")
    badge_cols[2].caption(f"**Vegetation score:** {_data_status_badge(veg_status, loaded=not planning_df.empty)}")


def _satellite_vegetation_section(region: PlanningRegionConfig, planning_df: pd.DataFrame) -> None:
    """Compact Sentinel-2 L2A summary for the planning tab."""
    st.markdown("#### Satellite vegetation (Sentinel-2 L2A)")
    if region.key == "surrey":
        qa = load_surrey_sentinel2_scene_qa()
        s2_stats = load_surrey_sentinel2_corridor_stats()
    else:
        qa = load_okanagan_sentinel2_scene_qa()
        s2_stats = load_okanagan_sentinel2_corridor_stats()
    l2a_dir = PROCESSED_DATA_DIR.parent / "raw" / region.sentinel2_l2a_subdir
    product_count = len(list(l2a_dir.glob("*.zip"))) if l2a_dir.is_dir() else None

    if qa.empty and s2_stats.empty and not product_count:
        st.info(
            f"Sentinel-2 corridor stats not built yet. Run `{region.sentinel2_build_cmd}`."
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

    metric_cols = st.columns(3)
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
        "L2A products on disk",
        product_count if product_count else "—",
        help="Sentinel-2 L2A zip archives in data/raw/okanagan/L2A used for index extraction.",
    )

    notes: list[str] = [
        "Open/free **Sentinel-2 L2A** products processed locally (NDVI / NDMI with SCL cloud mask)."
    ]
    if product_count:
        notes.append(f"Indices aggregated from L2A archives in `data/raw/{region.sentinel2_l2a_subdir}`.")
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


def _vegetation_drivers_section(region: PlanningRegionConfig, planning_df: pd.DataFrame) -> None:
    """WorldCover composition, Sentinel-2 stress, and dryness derivation."""
    st.markdown("#### Vegetation drivers (public satellite proxies)")
    if planning_df.empty:
        st.info(f"Planning dataset empty — run `{region.pipeline_build_cmd}`.")
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


def _outage_place_count_okanagan() -> int | None:
    return _outage_place_count(OKANAGAN_REGION)


@st.cache_data(show_spinner=False, ttl=3600)
def _load_region_fwi_for_map(region_key: str, selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    """Return FWI sample table and status label for map coloring on selected date."""
    region = PLANNING_REGIONS[region_key]
    bundled_path = region.fwi_corridor_csv if region.fwi_corridor_csv.is_file() else region.fwi_sample_csv
    bundled = pd.read_csv(bundled_path) if bundled_path.is_file() else pd.DataFrame()
    segments_path = region.segments_geojson
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
                fallback_bbox=region.aoi_bbox,
                time=selected_date_iso,
            )
            if status == "cwfis_live" and any(v is not None for v in values):
                rows = []
                for (_, seg), fwi_val in zip(segments.iterrows(), values, strict=True):
                    rows.append(
                        {
                            "segment_id": seg.get("segment_id"),
                            "fwi_value": fwi_val,
                            "as_of_date": selected_date_iso,
                            "data_status": status,
                            "data_source": CWFIS_FWI_SOURCE_LABEL,
                        }
                    )
                return pd.DataFrame(rows), status
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "Live CWFIS FWI sampling failed for %s (%s): %s",
                selected_date_iso,
                region.key,
                exc,
            )

    if not bundled.empty and bundled.get("fwi_value", pd.Series(dtype=float)).notna().any():
        return bundled, "bundled_csv"
    if not segments_path.is_file():
        return bundled, "segments_missing"
    return bundled, "fetch_failed"


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_fwi_raster(region_key: str, selected_date_iso: str) -> tuple[bytes | None, tuple[float, float, float, float], str]:
    region = PLANNING_REGIONS[region_key]
    return fetch_fwi_raster_for_date(selected_date_iso, bbox=region.aoi_bbox)


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_fires_for_date(region_key: str, selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    region = PLANNING_REGIONS[region_key]
    return load_fires_for_date(
        selected_date_iso,
        aoi_bbox=region.aoi_bbox,
        pilot_lat=region.pilot_lat,
        pilot_lon=region.pilot_lon,
        pilot_label=region.pilot_place_label,
    )


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_outages_for_date(region_key: str, selected_date_iso: str) -> tuple[pd.DataFrame, str]:
    region = PLANNING_REGIONS[region_key]
    return load_outages_for_date(
        selected_date_iso,
        aoi_bbox=region.aoi_bbox,
        bc_hydro_region=region.bc_hydro_region,
        municipalities=region.municipalities,
    )


def _fmt_planning_value(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if isinstance(val, (int, float)):
        return f"{val:.1f}"
    text = str(val).strip()
    return text if text else "—"


def _example_problem_areas_section(
    region: PlanningRegionConfig,
    df: pd.DataFrame,
    *,
    stress_mode: bool = False,
) -> str | None:
    """Top tree-contact example segments with detail card; returns map focus segment_id."""
    focus_key = f"{region.key}_map_focus_segment_id"
    pick_key = f"{region.key}_example_segment_pick"
    required = {
        "segment_id",
        "corridor_id",
        "planning_priority_score",
        "planning_priority_level",
        "tree_contact_exposure_proxy",
        "problem_type",
        "recommended_planning_action",
        "risk_pathway",
        "scenario_after_trimming_and_inspection_score",
        "scenario_priority_reduction",
        "current_priority_score",
        "scenario_after_inspection_score",
        "scenario_after_trimming_score",
    }
    if df.empty or not required.issubset(df.columns):
        return st.session_state.get(focus_key)

    st.markdown("#### Example problem areas")
    if stress_mode:
        st.caption("Synthetic stress scenario — illustrative only.")
    st.caption(
        "Top five segments by tree contact / fall-in review proxy, then planning priority score."
    )

    examples = df.sort_values(
        ["tree_contact_exposure_proxy", "planning_priority_score"],
        ascending=[False, False],
    ).head(5)
    if examples.empty:
        return st.session_state.get(focus_key)

    table_cols = [
        "corridor_id",
        "planning_priority_score",
        "planning_priority_level",
        "tree_contact_exposure_proxy",
        "problem_type",
        "recommended_planning_action",
        "risk_pathway",
        "scenario_after_trimming_and_inspection_score",
        "scenario_priority_reduction",
    ]
    st.dataframe(examples[table_cols], width="stretch", hide_index=True)

    option_labels = {
        str(row["segment_id"]): (
            f"{row['segment_id']} — {row.get('corridor_id', '')} "
            f"(tree contact {_fmt_planning_value(row.get('tree_contact_exposure_proxy'))})"
        )
        for _, row in examples.iterrows()
    }
    segment_ids = list(option_labels.keys())
    if pick_key not in st.session_state:
        st.session_state[pick_key] = segment_ids[0]
    if st.session_state[pick_key] not in segment_ids:
        st.session_state[pick_key] = segment_ids[0]

    selected_segment_id = st.selectbox(
        "Example segment",
        options=segment_ids,
        format_func=lambda seg_id: option_labels[seg_id],
        key=pick_key,
    )
    focus_btn_cols = st.columns(2)
    with focus_btn_cols[0]:
        if st.button("Focus map on selected example segment", key=f"{region.key}_focus_map_btn"):
            st.session_state[focus_key] = selected_segment_id
    with focus_btn_cols[1]:
        if st.button(
            "Clear map selection",
            key=f"{region.key}_clear_map_btn",
            disabled=not st.session_state.get(focus_key),
        ):
            st.session_state[focus_key] = None

    lookup = examples.set_index("segment_id", drop=False)
    row = lookup.loc[selected_segment_id]

    st.markdown("#### Why this area is prioritized")
    st.caption(
        f"Segment **{selected_segment_id}** · corridor **{_fmt_planning_value(row.get('corridor_id'))}**"
    )

    info_cols = st.columns(2)
    info_cols[0].markdown(f"**Problem type:** {_fmt_planning_value(row.get('problem_type'))}")
    info_cols[0].markdown(
        f"**Suggested planning action:** {_fmt_planning_value(row.get('recommended_planning_action'))}"
    )
    why_bits: list[str] = []
    risk_pathway = row.get("risk_pathway")
    if risk_pathway is not None and str(risk_pathway).strip():
        why_bits.append(str(risk_pathway).strip())
    explanation = row.get("explanation_short")
    if explanation is not None and str(explanation).strip():
        why_bits.append(str(explanation).strip())
    why_text = " ".join(why_bits) if why_bits else "—"
    info_cols[0].markdown(f"**Why:** {why_text}")
    info_cols[1].markdown(
        "**Tree contact / fall-in review proxy:** "
        f"{_fmt_planning_value(row.get('tree_contact_exposure_proxy'))}"
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Current priority", _fmt_planning_value(row.get("current_priority_score")))
    metric_cols[1].metric(
        "After inspection", _fmt_planning_value(row.get("scenario_after_inspection_score"))
    )
    metric_cols[2].metric("After trimming", _fmt_planning_value(row.get("scenario_after_trimming_score")))
    metric_cols[3].metric(
        "After trimming + inspection",
        _fmt_planning_value(row.get("scenario_after_trimming_and_inspection_score")),
    )
    st.caption("Scenario values use synthetic treatment assumptions.")

    return st.session_state.get(focus_key)


def _causal_ai_section(region: PlanningRegionConfig) -> None:
    if region.key != "surrey":
        return
    summary = surrey_causal_ai_summary()
    if summary is None:
        return
    st.markdown("#### Causal AI exploration (Fujitsu Research)")
    st.caption(
        "Research-only datasets for causal discovery and intervention scenario exploration — "
        "not operational planning scores."
    )
    cols = st.columns(3)
    cols[0].metric("AOI scenario rows", summary.aoi_rows)
    cols[1].metric("Discovery rows (targets)", summary.discovery_rows)
    if summary.scene_date_min and summary.scene_date_max:
        cols[2].metric("Scene dates", f"{summary.scene_date_min} → {summary.scene_date_max}")
    else:
        cols[2].metric("Scene dates", "—")
    if summary.intervention_types:
        st.caption(
            "Intervention types in AOI scenarios: "
            + ", ".join(summary.intervention_types)
        )
    links: list[str] = []
    if region.causal_ai_aoi_csv and region.causal_ai_aoi_csv.is_file():
        links.append(f"`{region.causal_ai_aoi_csv.relative_to(PROCESSED_DATA_DIR.parent)}`")
    if region.causal_ai_discovery_csv and region.causal_ai_discovery_csv.is_file():
        links.append(f"`{region.causal_ai_discovery_csv.relative_to(PROCESSED_DATA_DIR.parent)}`")
    if links:
        st.caption("Processed files: " + ", ".join(links))
    if region.causal_ai_dict_md and region.causal_ai_dict_md.is_file():
        st.caption(f"Data dictionary: `{region.causal_ai_dict_md.relative_to(PROCESSED_DATA_DIR.parent.parent)}`")


def _planning_tab(region: PlanningRegionConfig) -> None:
    st.subheader(f"{region.label} Vegetation-Wildfire Planning")
    place_count = _outage_place_count(region)
    place_suffix = f" ({place_count} in bundled summary)." if place_count is not None else "."
    st.caption(
        f"Historical outage and ECCC weather proxies start **{region.history_start_date}**. "
        f"Outage archive covers **{region.bc_hydro_region}** places{place_suffix}"
    )

    scenario = st.selectbox(
        "Scenario",
        options=["baseline", "stress"],
        format_func=lambda value: (
            "Baseline public/proxy"
            if value == "baseline"
            else "Synthetic stress scenario"
        ),
        key=f"{region.key}_scenario",
        help=(
            "Baseline uses the public/proxy planning dataset. "
            "Synthetic stress applies illustrative score boosts on selected segments."
        ),
    )
    stress_mode = scenario == "stress"
    planning_csv = region.planning_stress_csv if stress_mode else region.planning_csv

    result = _load_planning_dataset(region, planning_csv)
    if result.status != "loaded":
        st.warning(result.detail)
        st.info(f"Run: `{region.stress_build_cmd if stress_mode else region.pipeline_build_cmd}`")
        return

    df = _merge_sentinel2(region, result.df.copy())
    if stress_mode:
        st.warning(
            "Synthetic stress scenario — illustrative only. Not observed BC Hydro data."
        )

    cols = st.columns(5)
    cols[0].metric("Corridor segments", len(df))
    critical = int((df["planning_priority_level"] == "Critical").sum()) if "planning_priority_level" in df.columns else 0
    high = int((df["planning_priority_level"] == "High").sum()) if "planning_priority_level" in df.columns else 0
    cols[1].metric("Critical", critical)
    cols[2].metric("High", high)
    mean_score = df["planning_priority_score"].mean() if "planning_priority_score" in df.columns else 0
    cols[3].metric("Mean priority score", f"{mean_score:.1f}" if pd.notna(mean_score) else "—")
    cols[4].metric("Region", region.region_name)

    _vegetation_executive_summary(region, df)
    _causal_ai_section(region)
    focus_segment_id = _example_problem_areas_section(region, df, stress_mode=stress_mode)

    st.markdown("#### Planning map")
    if stress_mode:
        st.caption(
            "Synthetic stress scenario — illustrative only. Not observed BC Hydro data."
        )
    min_map_date, max_map_date, default_map_date = map_date_bounds(
        history_start_date=region.history_start_date,
        bc_hydro_region=region.bc_hydro_region,
        municipalities=region.municipalities,
    )
    selected_map_date = st.date_input(
        "Map date (2026 archive & CWFIS layers)",
        value=default_map_date,
        min_value=min_map_date,
        max_value=max_map_date,
        key=f"{region.key}_map_date",
        help=(
            "Refreshes FWI raster, CWFIF fires, and unofficial outage archive points for the selected day. "
            f"Outage archive snapshots run through {max_map_date.isoformat()}."
        ),
    )
    selected_date_iso = selected_map_date.isoformat()

    _MAP_TOGGLE_DEFAULTS = {
        f"{region.key}_show_fwi_raster": False,
        f"{region.key}_show_segments": True,
        f"{region.key}_show_fires": True,
        f"{region.key}_show_archive_outages": True,
        f"{region.key}_show_tx_lines": True,
        f"{region.key}_show_buffer": False,
        f"{region.key}_show_live_outages": False,
        f"{region.key}_segment_color_mode": "planning_priority_score",
    }
    for key, default in _MAP_TOGGLE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default

    segment_color_mode = st.selectbox(
        "Segment color by",
        options=["planning_priority_score", "tree_contact_exposure_proxy", "fwi"],
        format_func=lambda v: (
            "Planning priority (composite score)"
            if v == "planning_priority_score"
            else (
                "Tree contact / fall-in review proxy"
                if v == "tree_contact_exposure_proxy"
                else "Fire Weather Index — selected date"
            )
        ),
        key=f"{region.key}_segment_color_mode",
        help=(
            "Planning priority uses the static composite score (vegetation, wildfire, weather, treatment, outage). "
            "Tree contact colors segments by the tree contact / fall-in review proxy (0–100). "
            "FWI colors each segment by CWFIS Fire Weather Index sampled at its centroid for the map date."
        ),
    )
    if segment_color_mode == "planning_priority_score":
        st.caption(
            "Corridor lines use **planning priority level** buckets (Critical → Low). "
            "This score is static and does not change with the map date."
        )
    elif segment_color_mode == "tree_contact_exposure_proxy":
        st.caption(
            "Corridor lines use a continuous **tree contact / fall-in review proxy** ramp (green = low, red = high). "
            "Static composite — does not change with the map date."
        )
    else:
        st.caption(
            "Corridor lines use **dated CWFIS FWI** at each segment centroid. "
            "This is separate from the optional FWI raster overlay checkbox below."
        )
    temporal_cols = st.columns(3)
    temporal_cols[0].checkbox(
        "Show FWI raster overlay (CWFIS)",
        key=f"{region.key}_show_fwi_raster",
        help=(
            "Optional regional FWI heatmap under the map for the selected date. "
            "Independent of segment line coloring — you can show the raster with either color mode."
        ),
    )
    temporal_cols[1].checkbox(
        "Show fires (selected date)",
        key=f"{region.key}_show_fires",
    )
    temporal_cols[2].checkbox(
        "Show outages (archive, selected date)",
        key=f"{region.key}_show_archive_outages",
    )

    map_cols = st.columns(4)
    map_cols[0].checkbox(
        "Show BC transmission lines",
        key=f"{region.key}_show_tx_lines",
    )
    map_cols[1].checkbox(
        "Show corridor buffer (200 m)",
        key=f"{region.key}_show_buffer",
    )
    map_cols[2].checkbox(
        "Show corridor segments",
        key=f"{region.key}_show_segments",
    )
    live_outage_col = st.columns(1)[0]
    live_outage_col.checkbox(
        "Show outages (live BC Hydro JSON)",
        key=f"{region.key}_show_live_outages",
    )

    show_fwi_raster = st.session_state[f"{region.key}_show_fwi_raster"]
    show_fires = st.session_state[f"{region.key}_show_fires"]
    show_archive_outages = st.session_state[f"{region.key}_show_archive_outages"]
    show_tx_lines = st.session_state[f"{region.key}_show_tx_lines"]
    show_buffer = st.session_state[f"{region.key}_show_buffer"]
    show_segments = st.session_state[f"{region.key}_show_segments"]
    show_live_outages = st.session_state[f"{region.key}_show_live_outages"]

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
        png_bytes, raster_bbox, fwi_raster_status = _cached_fwi_raster(region.key, selected_date_iso)

    fwi_df = pd.DataFrame()
    fwi_status = ""
    if show_segments and segment_color_mode == "fwi":
        fwi_df, fwi_status = _load_region_fwi_for_map(region.key, selected_date_iso)

    if show_fires:
        fires_df, fires_status = _cached_fires_for_date(region.key, selected_date_iso)

    if show_archive_outages:
        archive_outage_points, archive_outage_status = _cached_outages_for_date(
            region.key, selected_date_iso
        )

    outage_points = pd.DataFrame()
    outage_total = 0
    outage_is_synthetic = False
    if show_live_outages:
        outages_raw = load_outages_json_cached(LIVE_PUBLIC_ONLY)
        outage_total = len(outages_raw)
        outage_is_synthetic = bool(
            outages_raw.get("is_synthetic", pd.Series(dtype=bool)).any()
        ) if not outages_raw.empty else False
        region_outages = filter_outages_for_region_map(
            outages_raw,
            aoi_bbox=region.aoi_bbox,
            bc_hydro_region=region.bc_hydro_region,
            municipalities=region.municipalities,
        )
        outage_points = prepare_okanagan_outage_map_points(region_outages)
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
        focus_segment_id=focus_segment_id if show_segments else None,
        center_lat=region.pilot_lat,
        center_lon=region.pilot_lon,
        zoom=region.map_zoom,
        aoi_bbox=region.aoi_bbox,
        segments_geojson_path=region.segments_geojson,
        buffer_geojson_path=region.buffer_geojson,
        transmission_geojson_candidates=region.transmission_geojson_candidates,
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
    elif segment_color_mode == "tree_contact_exposure_proxy" and show_segments:
        st.markdown(tree_contact_legend_html(), unsafe_allow_html=True)
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
            st.caption(f"No BC wildland fires in the {region.label} AOI on {selected_date_iso}.")
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

    _satellite_vegetation_section(region, df)

    if show_tx_lines:
        st.caption(
            "Transmission lines: province-wide BC Geographic Warehouse reference overlay. "
            f"Corridor segments, buffers, and planning scores are {region.label}-scoped."
        )

    fwi_valid = (
        int(fwi_df["fwi_value"].notna().sum())
        if not fwi_df.empty and "fwi_value" in fwi_df.columns
        else 0
    )
    if segment_color_mode == "fwi" and show_segments and fwi_valid == 0:
        if fwi_status == "fetch_failed":
            st.warning(
                "CWFIS FWI fetch failed — check network access to cwfis.cfs.nrcan.gc.ca."
            )
        elif fwi_status == "no_valid_samples":
            st.warning("CWFIS returned no valid FWI samples for corridor centroids.")
        else:
            st.warning("FWI layer missing or empty for corridor segment centroids.")
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

    _vegetation_drivers_section(region, df)


def _render_overview(region: PlanningRegionConfig) -> None:
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
    if region.key == "surrey":
        st.markdown(
            "- **Causal AI exploration** — Fujitsu Research Surrey AOI scenario exports linked on the Planning tab "
            "(research context only, not operational scores)"
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
        f"Open **{region.label} Planning** (or switch region in the sidebar) for corridor priority maps and component scores. "
        "See **Data Sources & Assumptions** for the BC Hydro internal data replacement table."
    )


def _render_okanagan_overview() -> None:
    _render_overview(OKANAGAN_REGION)


def _region_layer_inventory_df(region: PlanningRegionConfig) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    artifacts = (
        ("Planning dataset", region.planning_csv),
        ("Stress scenario", region.planning_stress_csv),
        ("Corridor segments", region.segments_geojson),
        ("Corridor buffer 200 m", region.buffer_geojson),
        ("WorldCover stats", region.worldcover_stats_csv),
        ("Sentinel-2 stats", region.sentinel2_stats_csv),
        ("Sentinel-2 scene QA", region.sentinel2_scene_qa_csv),
        ("FWI sample", region.fwi_sample_csv),
    )
    if region.causal_ai_aoi_csv:
        artifacts = (*artifacts, ("Causal AI AOI scenarios", region.causal_ai_aoi_csv))
    if region.causal_ai_discovery_csv:
        artifacts = (*artifacts, ("Causal AI discovery (targets)", region.causal_ai_discovery_csv))
    for label, path in artifacts:
        status = "loaded" if path.is_file() else f"missing — run `{region.pipeline_build_cmd}`"
        rows.append({"Layer": label, "Artifact": path.name, "Status": status})
    return pd.DataFrame(rows)


def _render_data_sources_tab(region: PlanningRegionConfig) -> None:
    st.subheader("Data sources & assumptions")
    st.caption(region.planning_disclaimer)
    st.markdown(f"#### {region.label} layer inventory")
    st.dataframe(_region_layer_inventory_df(region), width="stretch", hide_index=True)
    if region.key == "okanagan":
        st.markdown("#### BC Hydro internal data replacement")
        st.dataframe(okanagan_data_source_status(), width="stretch", hide_index=True)
    st.markdown("#### Assumptions and limitations")
    st.markdown(
        f"""
        - Outage history uses unofficial archive proxy for **{region.bc_hydro_region}** (from {region.history_start_date}).
        - Weather stress uses ECCC MSC GeoMet / climate-hourly proxies for the demo AOI.
        - Wildfire exposure uses CWFIS WFS when available; synthetic fallback otherwise.
        - **Fire Weather Index (FWI)** from CWFIS WCS — segment coloring only, not operational.
        - **CWFIF fires** — BC active fires filtered to the selected map date and region AOI.
        - Treatment gap scores are **synthetic** — placeholders for work-management records.
        - **Transmission lines** — BC Geographic Warehouse overlay; corridor segments and planning scores are region-scoped.
        """
    )
    if region.key == "surrey" and region.causal_ai_dict_md and region.causal_ai_dict_md.is_file():
        st.caption(
            f"Causal AI column definitions: `{region.causal_ai_dict_md.relative_to(PROCESSED_DATA_DIR.parent.parent)}`"
        )


def _render_okanagan_data_sources_tab() -> None:
    _render_data_sources_tab(OKANAGAN_REGION)


tab_overview, tab_planning, tab_sources = st.tabs(
    ["Overview", "Planning", "Data Sources & Assumptions"]
)

with tab_overview:
    _render_overview(active_region)

with tab_planning:
    _planning_tab(active_region)

with tab_sources:
    _render_data_sources_tab(active_region)
