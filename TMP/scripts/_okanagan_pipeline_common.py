"""Shared helpers for Kelowna / Okanagan planning pipeline scripts."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_REGION_NAME  # noqa: E402

# ESA WorldCover 2021 v200 class values
WORLDCOVER_TREE = 10
WORLDCOVER_SHRUB = 20
WORLDCOVER_GRASS = 30
WORLDCOVER_BUILT = 50
WORLDCOVER_BARE = 60

WORLDCOVER_GRID_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/esa_worldcover_2020_grid.geojson"
)

OKANAGAN_RAW_DIR = RAW_DATA_DIR / "okanagan"
OKANAGAN_PROCESSED_DIR = PROCESSED_DATA_DIR
DEFAULT_SEGMENTS_GEOJSON = OKANAGAN_PROCESSED_DIR / "okanagan_corridor_segments.geojson"
DEFAULT_BUFFER_GEOJSON = OKANAGAN_PROCESSED_DIR / "okanagan_corridor_buffer_200m.geojson"
NEUTRAL_DEFAULT_SCORE = 50.0
NEUTRAL_DEFAULT_LABEL = "neutral_default_50"


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def today_iso() -> str:
    return date.today().isoformat()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dirs(path.parent)
    df.to_csv(path, index=False)


def worldcover_tile_name(lat: float, lon: float) -> str:
    """ESA WorldCover 3×3° tile id (e.g. N48W120 for Okanagan)."""
    lat_i = int(lat // 3) * 3 if lat >= 0 else int((lat - 2.999) // 3) * 3
    if lon >= 0:
        lon_i = int(lon // 3) * 3
        return f"N{lat_i}E{lon_i}"
    west = int(-(-abs(lon) // 3) * 3)
    if west == 0:
        west = 3
    hemi = "N" if lat_i >= 0 else "S"
    return f"{hemi}{abs(lat_i)}W{west}"


def okanagan_worldcover_tile_name() -> str:
    """Known WorldCover tile for Okanagan centroid (~N49W120)."""
    return "N48W120"


def worldcover_tile_for_aoi(aoi: gpd.GeoDataFrame) -> str:
    """Resolve 3×3° ll_tile id intersecting AOI centroid."""
    try:
        grid = gpd.read_file(WORLDCOVER_GRID_URL)
        centroid = aoi.to_crs("EPSG:4326").union_all().centroid
        pt = gpd.GeoDataFrame(geometry=[centroid], crs="EPSG:4326")
        if grid.crs is not None:
            pt = pt.to_crs(grid.crs)
        hits = grid[grid.intersects(pt.geometry.iloc[0])]
        if not hits.empty and "ll_tile" in hits.columns:
            return str(hits.iloc[0]["ll_tile"])
    except Exception:
        pass
    min_lon, min_lat, max_lon, max_lat = OKANAGAN_AOI_BBOX
    return worldcover_tile_name((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)


def worldcover_download_url_for_tile(tile: str, *, vintage: str = "2021") -> str:
    if vintage == "2020":
        return (
            "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/map/"
            f"ESA_WorldCover_10m_2020_v100_{tile}_Map.tif"
        )
    return (
        "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    )


def try_download_file(url: str, dest: Path, *, timeout: int = 600) -> tuple[bool, str]:
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return True, f"Using cached raster: {dest}"
    ensure_dirs(dest.parent)
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code} for {url}"
            with dest.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        if dest.stat().st_size < 1_000_000:
            dest.unlink(missing_ok=True)
            return False, f"Download too small — likely invalid: {url}"
        return True, f"Downloaded {dest.name}"
    except Exception as exc:  # noqa: BLE001 — pipeline must not crash
        return False, f"Download failed: {exc}"


def zonal_class_percentages(
    raster_path: Path,
    aoi: gpd.GeoDataFrame,
    *,
    class_map: dict[str, set[int]],
) -> tuple[dict[str, float | None], str, str]:
    """Return percentage per class group, data_status, and detail message."""
    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask
        from rasterstats import zonal_stats
    except ImportError as exc:
        return (
            {key: None for key in class_map},
            "stub_missing_deps",
            f"Install geopandas, rasterio, rasterstats: {exc}",
        )

    if not raster_path.is_file():
        return (
            {key: None for key in class_map},
            "stub_missing_raster",
            f"Raster not found: {raster_path}",
        )

    try:
        aoi_reproj = aoi.to_crs("EPSG:4326")
        shapes = [geom.__geo_interface__ for geom in aoi_reproj.geometry if geom is not None]
        if not shapes:
            return (
                {key: None for key in class_map},
                "stub_empty_aoi",
                "AOI geometry empty after reprojection",
            )

        with rasterio.open(raster_path) as src:
            aoi_stats = aoi_reproj.to_crs(src.crs)
            shapes_proj = [geom.__geo_interface__ for geom in aoi_stats.geometry if geom is not None]
            try:
                stats = zonal_stats(
                    shapes_proj,
                    str(raster_path),
                    categorical=True,
                    nodata=src.nodata,
                    all_touched=True,
                )
            except Exception:
                out_image, out_transform = mask(src, shapes_proj, crop=True, all_touched=True)
                data = out_image[0]
                valid = data[data != src.nodata] if src.nodata is not None else data.flatten()
                valid = valid[np.isfinite(valid)]
                if valid.size == 0:
                    return (
                        {key: None for key in class_map},
                        "stub_no_valid_pixels",
                        "No valid raster pixels under AOI",
                    )
                total = float(valid.size)
                counts = {int(v): int((valid == v).sum()) for v in np.unique(valid)}
                stats = [counts]

        if not stats:
            return (
                {key: None for key in class_map},
                "stub_no_stats",
                "Zonal stats returned no rows",
            )

        merged: dict[int, float] = {}
        for row in stats:
            if not row:
                continue
            for key, value in row.items():
                if key == "null":
                    continue
                try:
                    code = int(float(key))
                except (TypeError, ValueError):
                    continue
                merged[code] = merged.get(code, 0.0) + float(value)

        total_pixels = sum(merged.values())
        if total_pixels <= 0:
            return (
                {key: None for key in class_map},
                "stub_zero_pixels",
                "Zero classified pixels under AOI",
            )

        out: dict[str, float | None] = {}
        for label, codes in class_map.items():
            count = sum(merged.get(code, 0.0) for code in codes)
            out[label] = round(100.0 * count / total_pixels, 2)
        return out, "open_free_processed", f"Zonal stats from {raster_path.name}"

    except Exception as exc:  # noqa: BLE001
        return (
            {key: None for key in class_map},
            "stub_processing_error",
            f"Zonal stats failed: {exc}",
        )


def load_okanagan_segments(segments_path: Path | None = None) -> gpd.GeoDataFrame:
    path = segments_path or DEFAULT_SEGMENTS_GEOJSON
    if not path.is_file():
        raise FileNotFoundError(
            f"Corridor segments not found: {path}. "
            "Run TMP/scripts/build_okanagan_transmission_corridors.py first."
        )
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def load_okanagan_buffer(buffer_path: Path | None = None) -> gpd.GeoDataFrame:
    path = buffer_path or DEFAULT_BUFFER_GEOJSON
    if not path.is_file():
        raise FileNotFoundError(f"Corridor buffer not found: {path}")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def segment_id_column(gdf: gpd.GeoDataFrame) -> str:
    if "segment_id" in gdf.columns:
        return "segment_id"
    if "corridor_id" in gdf.columns:
        return "corridor_id"
    gdf = gdf.copy()
    gdf["segment_id"] = [f"SEG-{i:04d}" for i in range(len(gdf))]
    return "segment_id"


def resolve_worldcover_raster(aoi_gdf: gpd.GeoDataFrame, *, raw_dir: Path | None = None) -> tuple[Path | None, str]:
    raw = raw_dir or OKANAGAN_RAW_DIR
    tile = okanagan_worldcover_tile_name()
    cached = raw / "worldcover" / f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    if cached.is_file():
        return cached, f"Using cached WorldCover raster: {cached}"
    tile = worldcover_tile_for_aoi(aoi_gdf)
    cached = raw / "worldcover" / f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
    if cached.is_file():
        return cached, f"Using cached WorldCover raster: {cached}"
    url = worldcover_download_url_for_tile(tile)
    ok, detail = try_download_file(url, cached, timeout=900)
    if ok:
        return cached, detail
    return None, (
        f"{detail}. Manual: download {url} to {cached} "
        "(or pass --worldcover-raster). See docs/free_data_pipeline_runbook.md."
    )


def discover_sentinel2_dirs() -> list[Path]:
    candidates = [
        OKANAGAN_RAW_DIR / "L2A",
        OKANAGAN_RAW_DIR / "sentinel2",
        RAW_DATA_DIR / "sentinel2" / "okanagan",
        RAW_DATA_DIR / "sentinel2",
    ]
    return [p for p in candidates if p.is_dir()]


def score_or_neutral(value: float | None, *, label: str = NEUTRAL_DEFAULT_LABEL) -> tuple[float, str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return NEUTRAL_DEFAULT_SCORE, label
    return float(value), "computed"


def assign_planning_priority_level(score: float) -> str:
    if score >= 80:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def top_contributing_reasons(
    components: dict[str, float],
    *,
    weight_map: dict[str, float],
    labels: dict[str, str],
    n: int = 3,
) -> tuple[str, str, str]:
    weighted = [
        (labels.get(key, key), float(components.get(key, NEUTRAL_DEFAULT_SCORE)) * weight_map.get(key, 0))
        for key in weight_map
    ]
    ranked = sorted(weighted, key=lambda item: item[1], reverse=True)
    reasons = [name for name, _ in ranked[:n]]
    while len(reasons) < n:
        reasons.append("")
    return reasons[0], reasons[1], reasons[2]
