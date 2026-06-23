"""Load Okanagan vegetation-wildfire planning dataset for Streamlit dashboard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.area_selection import lookup_municipality_coordinates
from src.config import (
    BC_TRANSMISSION_BC_GEOJSON,
    BC_TRANSMISSION_LINES_GEOJSON,
    OKANAGAN_CORRIDOR_BUFFER_CANDIDATES,
    OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES,
    OKANAGAN_FWI_CORRIDOR_CSV,
    OKANAGAN_FWI_SAMPLE_CSV,
    OKANAGAN_OUTAGE_DAILY_PROXY_CSV,
    OKANAGAN_PLANNING_DATASET_CSV,
    OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV,
    OKANAGAN_SENTINEL2_SCENE_QA_CSV,
    OKANAGAN_WORLDCOVER_STATS_CSV,
    OKANAGAN_TRANSMISSION_LINES_GEOJSON,
    PROCESSED_DATA_DIR,
)
from src.network_loader import _coords_to_path, _geometry_to_paths
from src.map_geojson import resolve_geojson_path
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_HISTORY_START_DATE, OKANAGAN_PILOT_LAT, OKANAGAN_PILOT_LON

WORLDCOVER_BUILD_CMD = "python TMP/scripts/build_okanagan_worldcover_stats.py"

OKANAGAN_LAYER_PATHS = {
    "planning": OKANAGAN_PLANNING_DATASET_CSV,
    "segments": OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES[0],
    "transmission_lines": OKANAGAN_TRANSMISSION_LINES_GEOJSON,
    "corridor_buffer": OKANAGAN_CORRIDOR_BUFFER_CANDIDATES[0],
    "fwi_sample": OKANAGAN_FWI_CORRIDOR_CSV,
    "wildfire_csv": PROCESSED_DATA_DIR / "okanagan_cwfis_wildfire_exposure.csv",
    "weather_csv": PROCESSED_DATA_DIR / "okanagan_weather_stress_stats.csv",
    "outage_summary": PROCESSED_DATA_DIR / "okanagan_outage_proxy_summary.csv",
    "outage_daily": OKANAGAN_OUTAGE_DAILY_PROXY_CSV,
    "transmission_qa": PROCESSED_DATA_DIR / "okanagan_transmission_qa_summary.csv",
    "sentinel2_corridor": OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV,
    "sentinel2_scene_qa": OKANAGAN_SENTINEL2_SCENE_QA_CSV,
    "worldcover_corridor": OKANAGAN_WORLDCOVER_STATS_CSV,
}

# Approximate centroids for Okanagan/Kootenay municipalities (archive proxy map markers).
OKANAGAN_PLACE_CENTROIDS: dict[str, tuple[float, float]] = {
    "Kelowna": (49.888, -119.496),
    "West Kelowna": (49.862, -119.583),
    "Westbank": (49.842, -119.623),
    "Lake Country": (50.017, -119.405),
    "Peachland": (49.774, -119.736),
    "Summerland": (49.600, -119.677),
    "Vernon": (50.267, -119.272),
    "Coldstream": (50.220, -119.260),
    "Armstrong": (50.448, -119.196),
    "Enderby": (50.553, -119.140),
    "Spallumcheen": (50.500, -119.200),
    "Lumby": (50.250, -118.970),
    "Nakusp": (50.243, -117.800),
    "Nelson": (49.495, -117.295),
    "Cranbrook": (49.512, -115.769),
    "Kimberley": (49.669, -115.978),
    "Fernie": (49.504, -115.063),
    "Golden": (51.296, -116.962),
    "Invermere": (50.508, -116.031),
    "Radium Hot Springs": (50.734, -116.074),
    "New Denver": (49.983, -117.378),
    "Silverton": (49.950, -117.350),
    "Sparwood": (49.733, -114.885),
    "Creston": (49.095, -116.513),
    "Castlegar": (49.324, -117.660),
    "Trail": (49.095, -117.705),
    "Salmon Arm": (50.700, -119.284),
    "Revelstoke": (50.998, -118.196),
}


@dataclass(frozen=True)
class OkanaganPlanningLoadResult:
    status: str  # not_loaded | loaded | empty
    detail: str
    df: pd.DataFrame


def load_okanagan_planning_dataset(csv_path: Path | None = None) -> OkanaganPlanningLoadResult:
    path = csv_path or OKANAGAN_PLANNING_DATASET_CSV
    if not path.is_file():
        return OkanaganPlanningLoadResult(
            status="not_loaded",
            detail=f"No planning dataset — run TMP/scripts/build_okanagan_demo_pipeline.py ({path.name})",
            df=pd.DataFrame(),
        )
    df = pd.read_csv(path)
    if df.empty:
        return OkanaganPlanningLoadResult(
            status="empty",
            detail=f"Planning dataset empty: {path.name}",
            df=df,
        )
    return OkanaganPlanningLoadResult(
        status="loaded",
        detail=f"{path.name} ({len(df)} corridor segments)",
        df=df,
    )


def load_okanagan_fwi_sample(csv_path: Path | None = None) -> pd.DataFrame:
    path = csv_path or OKANAGAN_FWI_CORRIDOR_CSV
    if not path.is_file():
        path = OKANAGAN_FWI_SAMPLE_CSV
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_okanagan_sentinel2_corridor_stats(csv_path: Path | None = None) -> pd.DataFrame:
    path = csv_path or OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_okanagan_sentinel2_scene_qa(csv_path: Path | None = None) -> pd.DataFrame:
    path = csv_path or OKANAGAN_SENTINEL2_SCENE_QA_CSV
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def merge_sentinel2_into_planning(planning_df: pd.DataFrame) -> pd.DataFrame:
    """Attach corridor-level Sentinel-2 QA fields (e.g. cloud_filtered_pct) when available."""
    if planning_df.empty or "segment_id" not in planning_df.columns:
        return planning_df
    s2 = load_okanagan_sentinel2_corridor_stats()
    if s2.empty or "segment_id" not in s2.columns:
        return planning_df
    extra_cols = [c for c in ("cloud_filtered_pct", "scenes_used", "period_start", "period_end") if c in s2.columns]
    if not extra_cols:
        return planning_df
    merged = planning_df.merge(s2[["segment_id", *extra_cols]].drop_duplicates("segment_id"), on="segment_id", how="left")
    return merged


def load_okanagan_transmission_paths(
    geojson_path: Path | None = None,
) -> pd.DataFrame:
    """HV transmission line paths from processed Okanagan GeoJSON."""
    path = geojson_path or OKANAGAN_TRANSMISSION_LINES_GEOJSON
    if not path.is_file():
        return pd.DataFrame()
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    rows: list[dict] = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        line_id = props.get("TRANSMISSION_LINE_ID", props.get("line_id"))
        for seg_path in _geometry_to_paths(geom):
            rows.append(
                {
                    "path": seg_path,
                    "line_id": line_id,
                    "dataset_note": (
                        "BC Geographic Warehouse transmission lines — Okanagan AOI "
                        f"({path.name})"
                    ),
                }
            )
    return pd.DataFrame(rows)


def load_okanagan_corridor_segment_paths(
    *,
    color_by: str = "planning_priority_score",
    planning_df: pd.DataFrame | None = None,
    fwi_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Corridor segment LineStrings as pydeck PathLayer rows with fill color."""
    path = resolve_geojson_path(OKANAGAN_CORRIDOR_SEGMENTS_CANDIDATES)
    if path is None:
        return pd.DataFrame()
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()

    planning = planning_df if planning_df is not None else pd.DataFrame()
    fwi = fwi_df if fwi_df is not None else load_okanagan_fwi_sample()
    fwi_lookup = (
        fwi.set_index("segment_id")["fwi_value"].to_dict()
        if not fwi.empty and "segment_id" in fwi.columns
        else {}
    )
    priority_lookup = (
        planning.set_index("segment_id")["planning_priority_score"].to_dict()
        if not planning.empty and "segment_id" in planning.columns
        else {}
    )
    level_lookup = (
        planning.set_index("segment_id")["planning_priority_level"].to_dict()
        if not planning.empty and "planning_priority_level" in planning.columns
        else {}
    )

    rows: list[dict] = []
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        segment_id = props.get("segment_id", "")
        for seg_path in _geometry_to_paths(geom):
            if color_by == "fwi":
                fwi_val = fwi_lookup.get(segment_id)
                color = fwi_value_color(fwi_val)
                color_label = f"FWI {fwi_val}" if fwi_val is not None else "FWI n/a"
            else:
                score = priority_lookup.get(segment_id)
                level = level_lookup.get(segment_id, "Medium")
                color = planning_priority_color(str(level), score)
                color_label = f"{level} ({score})" if score is not None else str(level)
            rows.append(
                {
                    "path": seg_path,
                    "segment_id": segment_id,
                    "corridor_id": props.get("corridor_id"),
                    "segment_color": color,
                    "tooltip_text": "\n".join(
                        [
                            f"Segment: {segment_id}",
                            f"Corridor: {props.get('corridor_id', '')}",
                            color_label,
                        ]
                    ),
                }
            )
    return pd.DataFrame(rows)


def load_okanagan_corridor_buffer_geojson() -> dict | None:
    path = resolve_geojson_path(OKANAGAN_CORRIDOR_BUFFER_CANDIDATES)
    if path is None:
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def resolve_okanagan_place_coordinates(place_name: str) -> tuple[float, float] | None:
    """Best-effort lat/lon for an outage-archive municipality label."""
    if not place_name:
        return None
    label = str(place_name).strip()
    if not label:
        return None
    coords = lookup_municipality_coordinates(label)
    if coords is not None:
        return coords
    if label in OKANAGAN_PLACE_CENTROIDS:
        return OKANAGAN_PLACE_CENTROIDS[label]
    for key, value in OKANAGAN_PLACE_CENTROIDS.items():
        if key.casefold() == label.casefold():
            return value
    first_part = label.split(",")[0].strip()
    if first_part and first_part != label:
        return resolve_okanagan_place_coordinates(first_part)
    for key, value in OKANAGAN_PLACE_CENTROIDS.items():
        if key.casefold() in label.casefold() or label.casefold() in key.casefold():
            return value
    return None


def load_okanagan_outage_proxy_map_points(
    *,
    recent_days: int = 30,
    min_outage_count: int = 1,
) -> pd.DataFrame:
    """
    Municipality-level outage proxy markers from daily archive CSV.
    Coordinates are place centroids — not exact outage locations.
    """
    path = OKANAGAN_OUTAGE_DAILY_PROXY_CSV
    if not path.is_file():
        return pd.DataFrame()
    daily = pd.read_csv(path)
    if daily.empty or "date" not in daily.columns:
        return pd.DataFrame()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    cutoff = daily["date"].max()
    if pd.isna(cutoff):
        return pd.DataFrame()
    window = daily.loc[daily["date"] >= (cutoff - pd.Timedelta(days=recent_days))]
    agg = (
        window.groupby("municipality", as_index=False)
        .agg(
            public_outage_count=("public_outage_count", "sum"),
            public_customers_affected=("public_customers_affected", "sum"),
        )
        .loc[lambda df: df["public_outage_count"] >= min_outage_count]
    )
    rows: list[dict] = []
    for _, row in agg.iterrows():
        coords = resolve_okanagan_place_coordinates(str(row["municipality"]))
        if coords is None:
            continue
        lat, lon = coords
        count = int(row["public_outage_count"])
        rows.append(
            {
                "municipality": row["municipality"],
                "lat": lat,
                "lon": lon,
                "public_outage_count": count,
                "public_customers_affected": int(row["public_customers_affected"]),
                "marker_radius_m": outage_proxy_radius_m(count),
                "outage_color": [220, 53, 69, 190],
                "tooltip_text": "\n".join(
                    [
                        f"Place: {row['municipality']}",
                        f"Proxy outages ({recent_days}d): {count}",
                        f"Customers affected (proxy): {int(row['public_customers_affected'])}",
                        "Unofficial archive — municipality centroid, not exact coords",
                    ]
                ),
            }
        )
    return pd.DataFrame(rows)


def filter_outages_to_okanagan_bbox(outage_df: pd.DataFrame) -> pd.DataFrame:
    """Filter live/public outage JSON rows to the Okanagan AOI bbox."""
    if outage_df.empty:
        return outage_df
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    frame = outage_df.copy()
    if "out_lat" not in frame.columns and "latitude" in frame.columns:
        frame["out_lat"] = pd.to_numeric(frame["latitude"], errors="coerce")
        frame["out_lon"] = pd.to_numeric(frame["longitude"], errors="coerce")
    if "out_lat" not in frame.columns:
        return pd.DataFrame()
    mask = (
        frame["out_lat"].between(min_lat, max_lat)
        & frame["out_lon"].between(min_lon, max_lon)
    )
    return frame.loc[mask].copy()


def fwi_value_color(value: float | None) -> list[int]:
    """RGBA color for Canadian FWI value (open CWFIS scale bands)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return [150, 150, 150, 160]
    if value < 5:
        return [46, 204, 113, 200]
    if value < 10:
        return [241, 196, 15, 200]
    if value < 20:
        return [230, 126, 34, 210]
    return [192, 57, 43, 220]


def planning_priority_color(level: str, score: float | None = None) -> list[int]:
    del score
    level_colors = {
        "Critical": [192, 57, 43, 210],
        "High": [230, 126, 34, 200],
        "Medium": [241, 196, 15, 190],
        "Low": [46, 204, 113, 180],
    }
    return level_colors.get(str(level), [150, 150, 150, 180])


def outage_proxy_radius_m(outage_count: int) -> int:
    return int(min(12000, max(2500, outage_count * 400)))


def okanagan_data_source_status() -> pd.DataFrame:
    """Summary table for BC Hydro data replacement slide."""
    rows = [
        {
            "layer": "Transmission corridor geometry",
            "current_source": "BC Geographic Warehouse WFS (public)",
            "bc_hydro_replacement": "Internal GIS / asset transmission network",
            "demo_status": _file_status(OKANAGAN_LAYER_PATHS["segments"]),
        },
        {
            "layer": "Transmission lines (HV)",
            "current_source": "BC Geographic Warehouse WFS — province-wide map overlay",
            "bc_hydro_replacement": "Internal GIS / asset transmission network",
            "demo_status": _transmission_layer_status(),
        },
        {
            "layer": "Fire Weather Index (FWI)",
            "current_source": "CWFIS GeoServer WCS (public:fwi)",
            "bc_hydro_replacement": "BC Wildfire Service / internal fire-weather integration",
            "demo_status": _fwi_layer_status(),
        },
        {
            "layer": "Vegetation cover (WorldCover)",
            "current_source": "ESA WorldCover 2021 (open)",
            "bc_hydro_replacement": "Planet / internal vegetation inventory",
            "demo_status": _worldcover_layer_status(),
        },
        {
            "layer": "Vegetation moisture (Sentinel-2 NDMI)",
            "current_source": "Sentinel-2 L2A local SAFE (optional)",
            "bc_hydro_replacement": "Planet SWC / patrol observations",
            "demo_status": _file_status(PROCESSED_DATA_DIR / "okanagan_sentinel2_corridor_stats.csv"),
        },
        {
            "layer": "Wildfire exposure",
            "current_source": "CWFIS WFS (CWFIF active fires + 24h hotspots)",
            "bc_hydro_replacement": "BC Wildfire Service + internal risk zones",
            "demo_status": _wildfire_layer_status(),
        },
        {
            "layer": "Weather stress",
            "current_source": f"ECCC MSC GeoMet (Kelowna station, from {OKANAGAN_HISTORY_START_DATE})",
            "bc_hydro_replacement": "Internal weather / forecast integration",
            "demo_status": _file_status(OKANAGAN_LAYER_PATHS["weather_csv"]),
        },
        {
            "layer": "Outage history",
            "current_source": "Unofficial public archive proxy (Okanagan/Kootenay region-wide)",
            "bc_hydro_replacement": "BC Hydro internal outage + SAIDI/SAIFI",
            "demo_status": _file_status(OKANAGAN_LAYER_PATHS["outage_summary"]),
        },
        {
            "layer": "Vegetation treatment gap",
            "current_source": "Synthetic (seed=42)",
            "bc_hydro_replacement": "Work management / treatment records",
            "demo_status": _file_status(PROCESSED_DATA_DIR / "okanagan_synthetic_treatment_gap.csv"),
        },
    ]
    return pd.DataFrame(rows)


def _transmission_layer_status() -> str:
    for path in (
        BC_TRANSMISSION_LINES_GEOJSON,
        BC_TRANSMISSION_BC_GEOJSON,
        OKANAGAN_LAYER_PATHS["transmission_lines"],
    ):
        if path.is_file():
            return f"loaded ({path.name})"
    return "missing — run TMP/scripts/build_bc_transmission_lines.py"


def _fwi_layer_status() -> str:
    path = OKANAGAN_LAYER_PATHS["fwi_sample"]
    if not path.is_file():
        return "missing — run pipeline"
    try:
        df = pd.read_csv(path, usecols=["data_status", "fwi_value"], nrows=500)
        if df.empty:
            return "empty"
        if df["fwi_value"].notna().any():
            status = df["data_status"].iloc[0] if "data_status" in df.columns else "loaded"
            return f"loaded ({status})"
        return "loaded (no valid FWI samples)"
    except Exception:  # noqa: BLE001
        return _file_status(path)


def _worldcover_layer_status() -> str:
    path = OKANAGAN_WORLDCOVER_STATS_CSV
    if not path.is_file():
        return f"missing — run: {WORLDCOVER_BUILD_CMD}"
    try:
        df = pd.read_csv(path, usecols=["data_status", "worldcover_tree_pct"], nrows=5)
        if df.empty:
            return "empty"
        status = str(df["data_status"].iloc[0]) if "data_status" in df.columns else "loaded"
        if status == "open_free_processed" and df["worldcover_tree_pct"].notna().any():
            return "loaded (ESA WorldCover 2021)"
        if status.startswith("stub"):
            return f"missing raster — run: {WORLDCOVER_BUILD_CMD} ({status})"
        return f"loaded ({status})"
    except Exception:  # noqa: BLE001
        return _file_status(path)


def _wildfire_layer_status() -> str:
    path = OKANAGAN_LAYER_PATHS["wildfire_csv"]
    if not path.is_file():
        return "missing — run pipeline"
    try:
        df = pd.read_csv(path, usecols=["data_status"], nrows=5)
        if df.empty:
            return "empty"
        status = df["data_status"].iloc[0]
        if status == "cwfis_live":
            return "loaded (CWFIS live)"
        if status == "synthetic_placeholder":
            return "loaded (synthetic fallback)"
        return f"loaded ({status})"
    except Exception:  # noqa: BLE001
        return _file_status(path)


def _file_status(path: Path) -> str:
    if not path.is_file():
        return "missing — run pipeline"
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, nrows=1)
            return "loaded" if not df.empty else "empty"
        return "loaded"
    except Exception:  # noqa: BLE001
        return "error reading"


def okanagan_map_default_view() -> dict[str, float]:
    return {
        "latitude": OKANAGAN_PILOT_LAT,
        "longitude": OKANAGAN_PILOT_LON,
        "zoom": 8.5,
    }
