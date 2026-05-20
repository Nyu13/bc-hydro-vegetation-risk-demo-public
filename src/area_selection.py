from __future__ import annotations

import math

import pandas as pd
import pydeck as pdk

from src.config import DEMO_DATA_DIR
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


def default_area_map_view_state() -> pdk.ViewState:
    return pdk.ViewState(**BC_DEFAULT_VIEW)


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
    return merged, source


def prepare_municipality_hotspot_map_df(limit: int = 25) -> pd.DataFrame:
    """Top municipalities by priority score with population coordinates when available."""
    from src.region_history_loader import load_municipality_outage_summary

    mun_df, _ = load_municipality_outage_summary()
    if mun_df.empty:
        return mun_df

    ranked = mun_df.sort_values("suggested_priority_score", ascending=False).head(limit)
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
    return merged
