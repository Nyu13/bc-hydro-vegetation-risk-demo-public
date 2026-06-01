"""Shared helpers for Surrey open/free data pipeline scripts."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEMO_DATA_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402

DEFAULT_AOI = DEMO_DATA_DIR / "surrey_transmission_buffer_200m.geojson"
DEFAULT_OUT_DIR = PROCESSED_DATA_DIR
DEFAULT_RAW_DIR = RAW_DATA_DIR / "surrey"

# ESA WorldCover 2021 v200 class values
WORLDCOVER_TREE = 10
WORLDCOVER_SHRUB = 20
WORLDCOVER_GRASS = 30
WORLDCOVER_BUILT = 50
WORLDCOVER_BARE = 60

# NALCMS 2020 forest-related classes (temperate / mixed forest)
NALCMS_FOREST_CLASSES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def load_aoi(aoi_path: Path) -> tuple[gpd.GeoDataFrame, str]:
    gdf = gpd.read_file(aoi_path)
    if gdf.empty:
        raise ValueError(f"AOI GeoJSON has no features: {aoi_path}")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    aoi_id = "surrey_buffer_200m"
    if "aoi_id" in gdf.columns and pd.notna(gdf["aoi_id"].iloc[0]):
        aoi_id = str(gdf["aoi_id"].iloc[0])
    return gdf, aoi_id


def today_iso() -> str:
    return date.today().isoformat()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dirs(path.parent)
    df.to_csv(path, index=False)


def worldcover_tile_name(lat: float, lon: float) -> str:
    """ESA WorldCover 3×3° tile id (e.g. N49W123 for Surrey / Lower Mainland)."""
    lat_i = int(lat // 3) * 3 if lat >= 0 else int((lat - 2.999) // 3) * 3
    if lon >= 0:
        lon_i = int(lon // 3) * 3
        return f"N{lat_i}E{lon_i}"
    west = int(-(-abs(lon) // 3) * 3)  # western edge of 3° cell, e.g. -122.85 → 123
    if west == 0:
        west = 3
    hemi = "N" if lat_i >= 0 else "S"
    return f"{hemi}{abs(lat_i)}W{west}"


WORLDCOVER_GRID_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/esa_worldcover_2020_grid.geojson"
)


def surrey_worldcover_tile_name() -> str:
    """Known-good WorldCover tile for Surrey PoC AOI (from esa_worldcover grid)."""
    return "N48W123"


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
    return surrey_worldcover_tile_name()


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


def stub_row(
    *,
    aoi_id: str,
    layer: str,
    data_status: str,
    instructions: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "aoi_id": aoi_id,
        "layer": layer,
        "data_status": data_status,
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
        "instructions": instructions,
    }
    if extra:
        row.update(extra)
    return row
