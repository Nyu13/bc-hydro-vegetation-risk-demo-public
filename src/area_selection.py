from __future__ import annotations

import math

import pandas as pd
import pydeck as pdk

from src.config import (
    DEMO_DATA_DIR,
    DEMO_PILOT_BC_HYDRO_REGION,
    DEMO_PILOT_LAT,
    DEMO_PILOT_LON,
    DEMO_PILOT_MAP_ZOOM,
    DEMO_PILOT_MUNICIPALITY,
    DEMO_PILOT_REGION,
    DEMO_PILOT_TRANSMISSION_BBOX,
)
from src.network_loader import load_bc_transmission_paths
from src.population_loader import load_municipality_population, population_marker_radius

# Default BC-wide view when nothing is selected.
BC_DEFAULT_VIEW = {"latitude": 53.5, "longitude": -124.5, "zoom": 4.5}
REGION_SELECTION_ZOOM = 8.0
MUNICIPALITY_SELECTION_ZOOM = 10.5


def load_region_map_context() -> pd.DataFrame:
    """BC Hydro region centroids and approximate regional population for map context."""
    path = DEMO_DATA_DIR / "demo_region_map_context.csv"
    cols = ("region_name", "lat", "lon", "population_2021", "source_note")
    try:
        df = pd.read_csv(path)
        for col in cols:
            if col not in df.columns:
                raise ValueError(f"Missing {col!r}")
        df["population_2021"] = pd.to_numeric(df["population_2021"], errors="coerce")
        return df.dropna(subset=["region_name", "lat", "lon"])
    except Exception:
        return pd.DataFrame(columns=list(cols))


def lookup_region_coordinates(region_name: str) -> tuple[float, float] | None:
    """Centroid lat/lon for a BC Hydro region from demo_region_map_context.csv."""
    if not region_name:
        return None
    df = load_region_map_context()
    if df.empty:
        return None
    row = df.loc[df["region_name"] == region_name]
    if row.empty:
        return None
    lat = float(row.iloc[0]["lat"])
    lon = float(row.iloc[0]["lon"])
    return lat, lon


def lookup_municipality_coordinates(municipality: str) -> tuple[float, float] | None:
    """Centroid lat/lon for a municipality from demo_municipality_population.csv."""
    if not municipality:
        return None
    df = load_municipality_population()
    if df.empty or not {"lat", "lon"}.issubset(df.columns):
        return None
    row = df.dropna(subset=["lat", "lon"]).loc[df["municipality"] == municipality]
    if row.empty:
        return None
    lat = float(row.iloc[0]["lat"])
    lon = float(row.iloc[0]["lon"])
    return lat, lon


def default_area_map_view_state(*, pilot: bool = True) -> pdk.ViewState:
    if pilot:
        return pilot_area_map_view_state()
    return pdk.ViewState(**BC_DEFAULT_VIEW)


def pilot_area_map_view_state(*, municipality: bool = True) -> pdk.ViewState:
    """Default PoC map view — Surrey / Lower Mainland metro context."""
    zoom = DEMO_PILOT_MAP_ZOOM if municipality else REGION_SELECTION_ZOOM
    return pdk.ViewState(latitude=DEMO_PILOT_LAT, longitude=DEMO_PILOT_LON, zoom=zoom)


RISK_MAP_SINGLE_OUTAGE_ZOOM = 12.5
RISK_MAP_DEFAULT_ZOOM = 9.5


def jitter_duplicate_map_coordinates(
    df: pd.DataFrame,
    *,
    lat_col: str = "lat",
    lon_col: str = "lon",
    jitter_m: float = 40.0,
) -> pd.DataFrame:
    """Spread stacked markers that share the same coordinates (display-only)."""
    if df.empty or lat_col not in df.columns or lon_col not in df.columns:
        return df
    out = df.copy()
    out[lat_col] = pd.to_numeric(out[lat_col], errors="coerce")
    out[lon_col] = pd.to_numeric(out[lon_col], errors="coerce")
    for (_, _), group in out.groupby([lat_col, lon_col], dropna=False):
        if len(group) <= 1:
            continue
        center_lat = float(group.iloc[0][lat_col])
        center_lon = float(group.iloc[0][lon_col])
        cos_lat = max(0.15, abs(math.cos(math.radians(center_lat))))
        lat_deg = jitter_m / 111_320.0
        lon_deg = jitter_m / (111_320.0 * cos_lat)
        indices = list(group.index)
        for i, row_idx in enumerate(indices):
            if i == 0:
                continue
            angle = (2.0 * math.pi * i) / len(indices)
            out.at[row_idx, lat_col] = center_lat + lat_deg * math.sin(angle)
            out.at[row_idx, lon_col] = center_lon + lon_deg * math.cos(angle)
    return out


def risk_map_pilot_view_state(
    *,
    lats: list[float] | None = None,
    lons: list[float] | None = None,
) -> pdk.ViewState:
    """Risk map view — tight zoom for a single outage point, else pilot default or bbox fit."""
    if not lats or not lons or len(lats) != len(lons):
        return pdk.ViewState(latitude=DEMO_PILOT_LAT, longitude=DEMO_PILOT_LON, zoom=RISK_MAP_DEFAULT_ZOOM)
    if len(lats) == 1:
        return pdk.ViewState(
            latitude=float(lats[0]),
            longitude=float(lons[0]),
            zoom=RISK_MAP_SINGLE_OUTAGE_ZOOM,
        )
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    latitude = (lat_min + lat_max) / 2
    longitude = (lon_min + lon_max) / 2
    span = max(lat_max - lat_min, abs(lon_max - lon_min), 0.01)
    if span < 0.015:
        zoom = 12.0
    elif span < 0.05:
        zoom = 11.0
    elif span < 0.15:
        zoom = 10.0
    else:
        zoom = RISK_MAP_DEFAULT_ZOOM
    return pdk.ViewState(latitude=latitude, longitude=longitude, zoom=zoom)


def promote_pilot_row(ranked: pd.DataFrame, *, municipality: bool) -> pd.DataFrame:
    """Move pilot municipality or BC Hydro region to the top without dropping other rows."""
    if ranked.empty:
        return ranked
    key = "municipality" if municipality else "region_name"
    if key not in ranked.columns:
        return ranked
    pilot_name = DEMO_PILOT_MUNICIPALITY if municipality else DEMO_PILOT_BC_HYDRO_REGION
    if pilot_name not in ranked[key].values:
        return ranked
    pilot_rows = ranked.loc[ranked[key] == pilot_name]
    other_rows = ranked.loc[ranked[key] != pilot_name]
    return pd.concat([pilot_rows, other_rows], ignore_index=True)


def pilot_row_index(ranked: pd.DataFrame, *, municipality: bool) -> int | None:
    """Zero-based row index of the pilot area in a ranked table, if present."""
    if ranked.empty:
        return None
    key = "municipality" if municipality else "region_name"
    pilot_name = DEMO_PILOT_MUNICIPALITY if municipality else DEMO_PILOT_BC_HYDRO_REGION
    if key not in ranked.columns:
        return None
    matches = ranked.index[ranked[key] == pilot_name]
    if matches.empty:
        return None
    return int(ranked.index.get_loc(matches[0]))


def fit_area_map_view_state(map_df: pd.DataFrame) -> pdk.ViewState:
    """Center and zoom to include all markers when nothing is selected."""
    if map_df.empty or not {"lat", "lon"}.issubset(map_df.columns):
        return default_area_map_view_state()
    lat_min = float(map_df["lat"].min())
    lat_max = float(map_df["lat"].max())
    lon_min = float(map_df["lon"].min())
    lon_max = float(map_df["lon"].max())
    latitude = (lat_min + lat_max) / 2
    longitude = (lon_min + lon_max) / 2
    span = max(lat_max - lat_min, abs(lon_max - lon_min), 0.25)
    if span < 0.6:
        zoom = 9.0
    elif span < 2.0:
        zoom = 7.0
    elif span < 6.0:
        zoom = 5.5
    else:
        zoom = float(BC_DEFAULT_VIEW["zoom"])
    return pdk.ViewState(latitude=latitude, longitude=longitude, zoom=zoom)


def selection_area_map_view_state(
    lat: float,
    lon: float,
    *,
    municipality: bool,
) -> pdk.ViewState:
    zoom = MUNICIPALITY_SELECTION_ZOOM if municipality else REGION_SELECTION_ZOOM
    return pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom)


# Tighter caps for municipality hotspot view — Metro Vancouver CSDs are close
# together; region-scale radii (10–22 km) collapse into one blob.
_MUNICIPALITY_OUTAGE_RADIUS = dict(base_m=2800, min_m=1200, max_m=5500, reference_outages=3500)
_MUNICIPALITY_POPULATION_RADIUS = dict(base_m=2200, min_m=1000, max_m=5000, reference_pop=400_000)


def outage_marker_radius(
    unique_outages: float | int | None,
    *,
    base_m: float = 12000,
    min_m: float = 7000,
    max_m: float = 32000,
    reference_outages: float = 5000,
) -> int:
    """Scale disk radius by √(outage count) for pydeck outage-intensity layer."""
    if unique_outages is None or pd.isna(unique_outages) or float(unique_outages) <= 0:
        return int(base_m)
    scale = math.sqrt(float(unique_outages) / reference_outages)
    radius = base_m * max(0.6, min(3.0, scale))
    return int(max(min_m, min(max_m, radius)))


def outage_intensity_color(unique_outages: float | int | None, max_outages: float) -> list[int]:
    """Orange → red fill by relative outage count (RGBA)."""
    if max_outages <= 0 or unique_outages is None or pd.isna(unique_outages):
        return [255, 140, 0, 200]
    t = min(1.0, max(0.0, float(unique_outages) / float(max_outages)))
    r = int(255)
    g = int(140 - 90 * t)
    b = int(0 + 40 * (1 - t))
    return [r, g, b, 210]


def _area_region_tooltip_text(row: pd.Series) -> str:
    lines = [
        f"Region: {row.get('region_name', '')}",
        f"Unique outages (proxy): {row.get('unique_outages', '')}",
        f"Avg customers per outage (max): {row.get('avg_customers_per_unique_outage', '')}",
        f"Population (approx): {row.get('population_2021', '')}",
        f"Tree-related outages: {row.get('tree_related_outage_count', '')}",
        f"Weather-related outages: {row.get('weather_related_outage_count', '')}",
    ]
    return "\n".join(line for line in lines if str(line.split(": ", 1)[-1]).strip())


def _area_municipality_tooltip_text(row: pd.Series) -> str:
    lines = [
        f"Municipality: {row.get('municipality', '')}",
        f"Region: {row.get('region_name', '')}",
        f"Unique outages (proxy): {row.get('unique_outages', '')}",
        f"Avg customers per outage (max): {row.get('avg_customers_per_unique_outage', '')}",
        f"Population (2021): {row.get('population_2021', '')}",
    ]
    return "\n".join(line for line in lines if str(line.split(": ", 1)[-1]).strip())


def prepare_region_hotspot_map_df() -> tuple[pd.DataFrame, str]:
    """Merge unofficial region outage summary with centroids and regional population."""
    from src.region_history_loader import load_region_outage_summary

    summary_df, source = load_region_outage_summary()
    context_df = load_region_map_context()
    if summary_df.empty or context_df.empty:
        return pd.DataFrame(), source

    merged = summary_df.merge(context_df, on="region_name", how="left")
    merged = merged.dropna(subset=["lat", "lon"])
    if merged.empty:
        return merged, source

    max_out = float(merged["unique_outages"].max()) if "unique_outages" in merged.columns else 1.0
    merged["outage_radius_m"] = merged["unique_outages"].apply(outage_marker_radius)
    merged["outage_color"] = merged["unique_outages"].apply(
        lambda v: outage_intensity_color(v, max_out)
    )
    merged["population_radius_m"] = merged["population_2021"].apply(population_marker_radius)
    if "avg_customers_per_unique_outage" in merged.columns:
        merged["avg_customers_per_unique_outage"] = pd.to_numeric(
            merged["avg_customers_per_unique_outage"], errors="coerce"
        ).fillna(0).round(1)
    merged["tooltip_text"] = merged.apply(_area_region_tooltip_text, axis=1)
    return merged, source


def prepare_municipality_hotspot_map_df(
    limit: int = 25,
    *,
    region_filter: str | None = DEMO_PILOT_REGION,
) -> pd.DataFrame:
    """Top municipalities by priority score with population coordinates when available."""
    from src.region_history_loader import load_municipality_outage_summary

    mun_df, _ = load_municipality_outage_summary()
    if mun_df.empty:
        return mun_df

    if region_filter and "region_name" in mun_df.columns:
        mun_df = mun_df.loc[mun_df["region_name"] == region_filter]
    ranked = promote_pilot_row(
        mun_df.sort_values("suggested_priority_score", ascending=False),
        municipality=True,
    ).head(limit)
    pop_df = load_municipality_population()
    if pop_df.empty:
        return ranked

    pop_lookup = pop_df.drop_duplicates("municipality")
    merged = ranked.merge(
        pop_lookup[["municipality", "population_2021", "lat", "lon", "source_note"]],
        on="municipality",
        how="left",
    )
    merged = merged.dropna(subset=["lat", "lon"])
    if merged.empty:
        return merged

    max_out = float(merged["unique_outages"].max())
    merged["outage_radius_m"] = merged["unique_outages"].apply(
        lambda v: outage_marker_radius(v, **_MUNICIPALITY_OUTAGE_RADIUS)
    )
    merged["outage_color"] = merged["unique_outages"].apply(
        lambda v: outage_intensity_color(v, max_out)
    )
    merged["population_radius_m"] = merged["population_2021"].apply(
        lambda p: population_marker_radius(p, **_MUNICIPALITY_POPULATION_RADIUS)
    )
    if "avg_customers_per_unique_outage" in merged.columns:
        merged["avg_customers_per_unique_outage"] = pd.to_numeric(
            merged["avg_customers_per_unique_outage"], errors="coerce"
        ).fillna(0).round(1)
    merged["tooltip_text"] = merged.apply(_area_municipality_tooltip_text, axis=1)
    return merged


def bc_transmission_path_layer(*, clip_to_pilot_bbox: bool = True) -> pdk.Layer | None:
    """
    Optional map underlay: BC Geographic Warehouse HV transmission lines (BC-wide reference).
    """
    bbox = DEMO_PILOT_TRANSMISSION_BBOX if clip_to_pilot_bbox else None
    paths_df = load_bc_transmission_paths(bbox=bbox)
    if paths_df.empty:
        return None
    return pdk.Layer(
        "PathLayer",
        data=paths_df,
        get_path="path",
        get_color=[41, 128, 185, 190],
        get_width=3,
        width_min_pixels=2,
        pickable=True,
    )

