"""Shared Sentinel-2 L2A NDVI/NDMI processing for regional corridor pipelines."""

from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def today_iso() -> str:
    return date.today().isoformat()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

LOG = logging.getLogger(__name__)

# SCL classes excluded from index stats: no data, saturated, cloud shadow, clouds, cirrus, snow
SCL_EXCLUDE_CLASSES = {0, 1, 3, 8, 9, 10, 11}

SAFE_NAME_RE = re.compile(
    r"^(S2[ABC]_MSIL2A_(\d{8})T\d{6}_.*?_(T\d{2}[A-Z]{3})_\d{8}T\d{6})(?:\.SAFE|\.zip)?$",
    re.IGNORECASE,
)

STUB_STATUS = "unavailable_credentials_or_missing_rasters"
PROCESSED_STATUS = "open_free_processed"


@dataclass(frozen=True)
class SafeProduct:
    path: Path
    scene_id: str
    sensing_date: str
    tile: str
    is_temp: bool = False


@dataclass
class SceneStats:
    scene_id: str
    tile: str
    sensing_date: str
    ndvi_mean: float | None
    ndmi_mean: float | None
    cloud_filtered_pct: float | None
    status: str
    notes: str = ""


def _parse_safe_name(name: str) -> tuple[str, str, str] | None:
    match = SAFE_NAME_RE.match(name)
    if not match:
        return None
    scene_id = match.group(1)
    sensing_raw = match.group(2)
    tile = match.group(3).upper()
    sensing_date = f"{sensing_raw[0:4]}-{sensing_raw[4:6]}-{sensing_raw[6:8]}"
    return scene_id, sensing_date, tile


def _safe_folder_name(product_name: str) -> str:
    stem = product_name
    if stem.upper().endswith(".SAFE"):
        stem = stem[: -len(".SAFE")]
    return f"{stem}.SAFE"


def _extract_zip_safe(zip_path: Path, temp_root: Path) -> Path | None:
    try:
        dest = temp_root / _safe_folder_name(zip_path.stem)
        if dest.is_dir():
            return dest
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_root)
        if dest.is_dir():
            return dest
        for child in sorted(temp_root.iterdir()):
            if child.is_dir() and child.name.upper().endswith(".SAFE") and child.stem == zip_path.stem:
                return child
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Failed to extract %s: %s", zip_path.name, exc)
    return None


def discover_safe_products(safe_dir: Path) -> tuple[list[SafeProduct], list[Path]]:
    """Find .SAFE directories and .zip products under safe_dir (including subfolders)."""
    if not safe_dir.is_dir():
        LOG.warning("SAFE directory not found: %s", safe_dir)
        return [], []

    products: list[SafeProduct] = []
    seen_ids: set[str] = set()
    temp_dirs: list[Path] = []
    temp_root = Path(tempfile.mkdtemp(prefix="s2_safe_"))
    temp_dirs.append(temp_root)

    candidates: list[Path] = []
    for path in safe_dir.rglob("*"):
        if path.is_dir() and path.name.upper().endswith(".SAFE"):
            candidates.append(path)
        elif path.is_file() and path.suffix.lower() == ".zip" and "MSIL2A" in path.name.upper():
            candidates.append(path)

    for path in sorted(candidates, key=lambda p: p.name):
        if path.is_dir():
            meta = _parse_safe_name(path.name)
            if meta is None:
                continue
            scene_id, sensing_date, tile = meta
            if scene_id in seen_ids:
                continue
            seen_ids.add(scene_id)
            products.append(SafeProduct(path=path, scene_id=scene_id, sensing_date=sensing_date, tile=tile))
            continue

        meta = _parse_safe_name(path.stem)
        if meta is None:
            continue
        scene_id, sensing_date, tile = meta
        if scene_id in seen_ids:
            continue
        extracted = _extract_zip_safe(path, temp_root)
        if extracted is None:
            LOG.warning("Skipping zip (extract failed): %s", path.name)
            continue
        seen_ids.add(scene_id)
        products.append(
            SafeProduct(
                path=extracted,
                scene_id=scene_id,
                sensing_date=sensing_date,
                tile=tile,
                is_temp=True,
            )
        )

    LOG.info("Discovered %d SAFE product(s) under %s", len(products), safe_dir)
    return products, temp_dirs


def _find_band(safe_root: Path, resolution: str, band: str) -> Path | None:
    patterns = [
        f"GRANULE/*/IMG_DATA/{resolution}/*_{band}_{resolution}.jp2",
        f"GRANULE/*/IMG_DATA/{resolution}/*_{band}_{resolution}.tif",
        f"GRANULE/*/IMG_DATA/{resolution}/*_{band}_*.jp2",
        f"GRANULE/*/IMG_DATA/{resolution}/*_{band}_*.tif",
    ]
    for pattern in patterns:
        hits = sorted(safe_root.glob(pattern))
        if hits:
            return hits[0]
    return None


def _to_reflectance(data: np.ndarray) -> np.ndarray:
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return data
    if float(np.nanmax(finite)) > 2.0:
        return data / 10000.0
    return data


def _read_aoi_clipped(path: Path, aoi_gdf, ref_profile: dict | None = None) -> tuple[np.ndarray, dict]:
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import Resampling, reproject

    with rasterio.open(path) as src:
        aoi_proj = aoi_gdf.to_crs(src.crs)
        shapes = [geom.__geo_interface__ for geom in aoi_proj.geometry if geom is not None]
        if ref_profile is None:
            out_image, out_transform = mask(src, shapes, crop=True, all_touched=True)
            data = out_image[0].astype(np.float64)
            profile = src.profile.copy()
            profile.update({"height": data.shape[0], "width": data.shape[1], "transform": out_transform})
            nodata = src.nodata
            if nodata is not None:
                data[data == nodata] = np.nan
            return _to_reflectance(data), profile

        dest = np.full((ref_profile["height"], ref_profile["width"]), np.nan, dtype=np.float64)
        clipped, clipped_transform = mask(src, shapes, crop=True, all_touched=True)
        src_data = clipped[0].astype(np.float64)
        src_nodata = src.nodata
        if src_nodata is not None:
            src_data[src_data == src_nodata] = np.nan
        reproject(
            source=src_data,
            destination=dest,
            src_transform=clipped_transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.bilinear if "B" in path.name else Resampling.nearest,
        )
        out = _to_reflectance(dest) if "B" in path.name else dest
        return out, ref_profile


def _compute_indices_masked(
    red: np.ndarray,
    nir: np.ndarray,
    swir: np.ndarray,
    scl: np.ndarray | None,
    *,
    exclude_scl: set[int],
) -> dict[str, float | None]:
    valid = np.isfinite(red) & np.isfinite(nir) & np.isfinite(swir)
    total_pixels = int(valid.sum())
    if total_pixels == 0:
        return {"ndvi_mean": None, "ndmi_mean": None, "cloud_filtered_pct": None}

    if scl is not None:
        scl_int = np.round(scl).astype(np.int32)
        clear = valid & ~np.isin(scl_int, list(exclude_scl))
    else:
        clear = valid

    clear_count = int(clear.sum())
    cloud_filtered_pct = round(100.0 * clear_count / total_pixels, 2) if total_pixels else None

    if clear_count == 0:
        return {"ndvi_mean": None, "ndmi_mean": None, "cloud_filtered_pct": cloud_filtered_pct}

    red_c = red[clear]
    nir_c = nir[clear]
    swir_c = swir[clear]

    ndvi_denom = nir_c + red_c
    ndmi_denom = nir_c + swir_c
    ndvi = np.full(ndvi_denom.shape, np.nan, dtype=np.float64)
    ndmi = np.full(ndmi_denom.shape, np.nan, dtype=np.float64)
    np.divide(nir_c - red_c, ndvi_denom, out=ndvi, where=ndvi_denom != 0)
    np.divide(nir_c - swir_c, ndmi_denom, out=ndmi, where=ndmi_denom != 0)

    ndvi_mean = float(np.nanmean(ndvi)) if np.any(np.isfinite(ndvi)) else None
    ndmi_mean = float(np.nanmean(ndmi)) if np.any(np.isfinite(ndmi)) else None

    return {
        "ndvi_mean": round(ndvi_mean, 4) if ndvi_mean is not None else None,
        "ndmi_mean": round(ndmi_mean, 4) if ndmi_mean is not None else None,
        "cloud_filtered_pct": cloud_filtered_pct,
    }


def _compute_period_stats(
    *,
    red_path: Path,
    nir_path: Path,
    swir_path: Path,
    scl_path: Path | None,
    aoi_gdf,
    mask_snow: bool,
) -> dict[str, float | None]:
    exclude = set(SCL_EXCLUDE_CLASSES)
    if not mask_snow:
        exclude.discard(11)

    red, profile = _read_aoi_clipped(red_path, aoi_gdf)
    nir, _ = _read_aoi_clipped(nir_path, aoi_gdf, ref_profile=profile)
    swir, _ = _read_aoi_clipped(swir_path, aoi_gdf, ref_profile=profile)
    scl = None
    if scl_path is not None and scl_path.is_file():
        scl, _ = _read_aoi_clipped(scl_path, aoi_gdf, ref_profile=profile)
    return _compute_indices_masked(red, nir, swir, scl, exclude_scl=exclude)


def _process_safe_scene(product: SafeProduct, aoi_gdf) -> SceneStats:
    safe_root = product.path
    b04 = _find_band(safe_root, "R10m", "B04")
    b08 = _find_band(safe_root, "R10m", "B08")
    b11 = _find_band(safe_root, "R20m", "B11")
    scl = _find_band(safe_root, "R20m", "SCL")

    missing = [
        label
        for label, band in (("B04", b04), ("B08", b08), ("B11", b11))
        if band is None
    ]
    if missing:
        return SceneStats(
            scene_id=product.scene_id,
            tile=product.tile,
            sensing_date=product.sensing_date,
            ndvi_mean=None,
            ndmi_mean=None,
            cloud_filtered_pct=None,
            status="skipped_missing_bands",
            notes=f"Missing bands: {', '.join(missing)}",
        )

    try:
        red, profile = _read_aoi_clipped(b04, aoi_gdf)
        nir, _ = _read_aoi_clipped(b08, aoi_gdf, ref_profile=profile)
        swir, _ = _read_aoi_clipped(b11, aoi_gdf, ref_profile=profile)
        scl_arr = None
        if scl is not None:
            scl_arr, _ = _read_aoi_clipped(scl, aoi_gdf, ref_profile=profile)

        stats = _compute_indices_masked(
            red, nir, swir, scl_arr, exclude_scl=SCL_EXCLUDE_CLASSES
        )
        if stats["ndvi_mean"] is None and stats["ndmi_mean"] is None:
            return SceneStats(
                scene_id=product.scene_id,
                tile=product.tile,
                sensing_date=product.sensing_date,
                ndvi_mean=None,
                ndmi_mean=None,
                cloud_filtered_pct=stats.get("cloud_filtered_pct"),
                status="skipped_no_clear_pixels",
                notes="No clear AOI pixels after SCL mask",
            )
        return SceneStats(
            scene_id=product.scene_id,
            tile=product.tile,
            sensing_date=product.sensing_date,
            ndvi_mean=stats.get("ndvi_mean"),
            ndmi_mean=stats.get("ndmi_mean"),
            cloud_filtered_pct=stats.get("cloud_filtered_pct"),
            status="processed",
            notes="",
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Scene failed %s: %s", product.scene_id, exc)
        return SceneStats(
            scene_id=product.scene_id,
            tile=product.tile,
            sensing_date=product.sensing_date,
            ndvi_mean=None,
            ndmi_mean=None,
            cloud_filtered_pct=None,
            status="skipped_error",
            notes=str(exc),
        )


def _aggregate_scene_stats(
    scenes: list[SceneStats],
    *,
    period_start: str | None,
    period_end: str | None,
) -> dict[str, Any]:
    ok = [s for s in scenes if s.status == "processed"]
    ndvi_vals = [float(s.ndvi_mean) for s in ok if s.ndvi_mean is not None]
    ndmi_vals = [float(s.ndmi_mean) for s in ok if s.ndmi_mean is not None]
    cloud_vals = [float(s.cloud_filtered_pct) for s in ok if s.cloud_filtered_pct is not None]

    dates = sorted({s.sensing_date for s in ok})
    tiles = sorted({s.tile for s in ok})

    ps = period_start or (dates[0] if dates else None)
    pe = period_end or (dates[-1] if dates else None)

    ndvi_change = None
    ndmi_change = None
    change_notes = ""
    if len(dates) >= 2:
        by_date: dict[str, list[SceneStats]] = {}
        for scene in ok:
            by_date.setdefault(scene.sensing_date, []).append(scene)
        earliest = dates[0]
        latest = dates[-1]
        early_ndvi = [float(s.ndvi_mean) for s in by_date[earliest] if s.ndvi_mean is not None]
        late_ndvi = [float(s.ndvi_mean) for s in by_date[latest] if s.ndvi_mean is not None]
        early_ndmi = [float(s.ndmi_mean) for s in by_date[earliest] if s.ndmi_mean is not None]
        late_ndmi = [float(s.ndmi_mean) for s in by_date[latest] if s.ndmi_mean is not None]
        if early_ndvi and late_ndvi:
            ndvi_change = round(float(np.mean(late_ndvi)) - float(np.mean(early_ndvi)), 4)
        if early_ndmi and late_ndmi:
            ndmi_change = round(float(np.mean(late_ndmi)) - float(np.mean(early_ndmi)), 4)
        change_notes = f"NDVI/NDMI change: latest ({latest}) minus earliest ({earliest}) scene means."

    return {
        "sentinel2_ndvi_mean": round(float(np.mean(ndvi_vals)), 4) if ndvi_vals else None,
        "sentinel2_ndmi_mean": round(float(np.mean(ndmi_vals)), 4) if ndmi_vals else None,
        "cloud_filtered_pct": round(float(np.mean(cloud_vals)), 2) if cloud_vals else None,
        "sentinel2_ndvi_change": ndvi_change,
        "sentinel2_ndmi_change": ndmi_change,
        "change_notes": change_notes,
        "period_start": ps,
        "period_end": pe,
        "scenes_used": len(ok),
        "tiles_used": ",".join(tiles) if tiles else "",
    }


def _scene_qa_rows(scenes: list[SceneStats], aoi_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scene in scenes:
        rows.append(
            {
                "aoi_id": aoi_id,
                "scene_id": scene.scene_id,
                "tile": scene.tile,
                "sensing_date": scene.sensing_date,
                "ndvi_mean": scene.ndvi_mean,
                "ndmi_mean": scene.ndmi_mean,
                "cloud_filtered_pct": scene.cloud_filtered_pct,
                "status": scene.status,
                "notes": scene.notes,
            }
        )
    return rows
