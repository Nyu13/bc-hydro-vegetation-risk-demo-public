#!/usr/bin/env python3
"""Sentinel-2 NDVI/NDMI corridor stats from local L2A .SAFE products, band GeoTIFFs, or stub row."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _surrey_pipeline_common import DEFAULT_AOI, DEFAULT_OUT_DIR, load_aoi, today_iso, write_csv  # noqa: E402
from _sentinel2_pipeline_common import (  # noqa: E402
    PROCESSED_STATUS,
    STUB_STATUS,
    SceneStats,
    _aggregate_scene_stats,
    _compute_period_stats,
    _process_safe_scene,
    _scene_qa_rows,
    discover_safe_products,
)

LOG = logging.getLogger(__name__)

MANUAL_NOTES = (
    "No local Sentinel-2 inputs found. Download S2 L2A .SAFE or .zip products to "
    "data/raw/surrey/Sentinel-2 L2A/ or data/raw/surrey/sentinel2/ (gitignored). "
    "See docs/sentinel2_manual_download_notes.md. Example: "
    "python TMP/scripts/build_surrey_sentinel2_indices.py "
    '--safe-dir "data/raw/surrey/Sentinel-2 L2A"'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Surrey Sentinel-2 NDVI/NDMI corridor stats from .SAFE products or band GeoTIFFs."
    )
    parser.add_argument("--aoi", type=Path, default=DEFAULT_AOI, help="Corridor buffer GeoJSON")
    parser.add_argument(
        "--safe-dir",
        type=Path,
        default=None,
        help="Directory to scan recursively for .SAFE folders and .zip L2A products",
    )
    parser.add_argument("--red", type=Path, default=None, help="B04 (red) single-band GeoTIFF (legacy mode)")
    parser.add_argument("--nir", type=Path, default=None, help="B08 (NIR) single-band GeoTIFF")
    parser.add_argument("--swir", type=Path, default=None, help="B11 (SWIR) single-band GeoTIFF")
    parser.add_argument("--scl", type=Path, default=None, help="SCL scene classification band (optional)")
    parser.add_argument(
        "--mask-snow",
        action="store_true",
        help="Legacy raster mode: also mask SCL class 11 (SAFE mode always masks snow)",
    )
    parser.add_argument("--period-start", type=str, default=None, help="ISO date override for period start")
    parser.add_argument("--period-end", type=str, default=None, help="ISO date override for period end")
    parser.add_argument("--red-prior", type=Path, default=None, help="Prior-period B04 GeoTIFF for change")
    parser.add_argument("--nir-prior", type=Path, default=None, help="Prior-period B08 GeoTIFF for change")
    parser.add_argument("--swir-prior", type=Path, default=None, help="Prior-period B11 GeoTIFF for change")
    parser.add_argument("--scl-prior", type=Path, default=None, help="Prior-period SCL GeoTIFF")
    parser.add_argument("--period-start-prior", type=str, default=None)
    parser.add_argument("--period-end-prior", type=str, default=None)
    parser.add_argument(
        "--prior-csv",
        type=Path,
        default=None,
        help="Prior stats CSV with sentinel2_ndvi_mean for change when prior bands absent",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: data/processed/surrey_sentinel2_corridor_stats.csv)",
    )
    parser.add_argument(
        "--qa-out",
        type=Path,
        default=None,
        help="Per-scene QA CSV (default: data/processed/surrey_sentinel2_scene_qa.csv)",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory when --out not set")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def _resolve_out_path(args: argparse.Namespace) -> Path:
    if args.out is not None:
        return args.out
    return args.out_dir / "surrey_sentinel2_corridor_stats.csv"


def _resolve_qa_out_path(args: argparse.Namespace) -> Path:
    if args.qa_out is not None:
        return args.qa_out
    return args.out_dir / "surrey_sentinel2_scene_qa.csv"


def _local_raster_mode(args: argparse.Namespace) -> bool:
    paths = (args.red, args.nir, args.swir)
    if all(p is None for p in paths):
        return False
    missing = [name for name, p in (("red", args.red), ("nir", args.nir), ("swir", args.swir)) if p is None]
    if missing:
        raise ValueError(
            f"Local raster mode requires --red, --nir, and --swir. Missing: {', '.join(missing)}"
        )
    for label, path in (("red", args.red), ("nir", args.nir), ("swir", args.swir)):
        if path is not None and not path.is_file():
            raise FileNotFoundError(f"Band raster not found ({label}): {path}")
    return True


def _safe_mode(args: argparse.Namespace) -> bool:
    return args.safe_dir is not None


def _prior_ndvi_from_csv(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path)
        if df.empty or "sentinel2_ndvi_mean" not in df.columns:
            return None
        val = df.iloc[0]["sentinel2_ndvi_mean"]
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def _compute_ndvi_change(
    current_ndvi: float | None,
    args: argparse.Namespace,
    aoi_gdf,
    out_path: Path,
) -> tuple[float | None, str]:
    if current_ndvi is None:
        return None, "NDVI change not computed — current NDVI unavailable."

    prior_stats: dict[str, float | None] | None = None
    if args.red_prior and args.nir_prior and args.swir_prior:
        if not all(p.is_file() for p in (args.red_prior, args.nir_prior, args.swir_prior)):
            return None, "Prior band rasters specified but not all files exist."
        prior_stats = _compute_period_stats(
            red_path=args.red_prior,
            nir_path=args.nir_prior,
            swir_path=args.swir_prior,
            scl_path=args.scl_prior,
            aoi_gdf=aoi_gdf,
            mask_snow=args.mask_snow,
        )
        prior_ndvi = prior_stats.get("ndvi_mean")
        if prior_ndvi is not None:
            change = round(current_ndvi - float(prior_ndvi), 4)
            return change, f"NDVI change vs prior band rasters ({args.period_start_prior}–{args.period_end_prior})."

    prior_csv = args.prior_csv or out_path
    prior_ndvi = _prior_ndvi_from_csv(prior_csv)
    if prior_ndvi is not None:
        change = round(current_ndvi - prior_ndvi, 4)
        return change, f"NDVI change vs prior CSV {prior_csv.name}."

    return None, "NDVI change not computed — provide prior band rasters or existing stats CSV."


def _stub_row(aoi_id: str, notes: str) -> dict[str, Any]:
    return {
        "aoi_id": aoi_id,
        "layer": "sentinel2_l2a",
        "data_status": STUB_STATUS,
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
        "period_start": None,
        "period_end": None,
        "scenes_used": 0,
        "tiles_used": "",
        "instructions": notes,
        "sentinel2_ndvi_mean": None,
        "sentinel2_ndmi_mean": None,
        "cloud_filtered_pct": None,
        "sentinel2_ndvi_change": None,
        "sentinel2_ndmi_change": None,
        "change_notes": None,
    }


def _processed_row(aoi_id: str, stats: dict[str, Any], *, change_notes: str) -> dict[str, Any]:
    ndvi_change = stats.get("sentinel2_ndvi_change")
    notes = change_notes
    if ndvi_change is None and stats.get("change_notes"):
        notes = str(stats.get("change_notes"))
    elif stats.get("change_notes") and ndvi_change is not None:
        notes = str(stats.get("change_notes"))

    return {
        "aoi_id": aoi_id,
        "layer": "sentinel2_l2a",
        "data_status": PROCESSED_STATUS,
        "data_source": "open_free_v1",
        "as_of_date": today_iso(),
        "period_start": stats.get("period_start"),
        "period_end": stats.get("period_end"),
        "scenes_used": stats.get("scenes_used", 0),
        "tiles_used": stats.get("tiles_used", ""),
        "instructions": "",
        "sentinel2_ndvi_mean": stats.get("sentinel2_ndvi_mean"),
        "sentinel2_ndmi_mean": stats.get("sentinel2_ndmi_mean"),
        "cloud_filtered_pct": stats.get("cloud_filtered_pct"),
        "sentinel2_ndvi_change": ndvi_change,
        "sentinel2_ndmi_change": stats.get("sentinel2_ndmi_change"),
        "change_notes": notes if ndvi_change is None else "",
    }


def _run_safe_mode(args: argparse.Namespace, aoi_gdf, aoi_id: str, out_path: Path, qa_path: Path) -> int:
    safe_dir = args.safe_dir
    if safe_dir is None:
        return 1

    products, temp_dirs = discover_safe_products(safe_dir)
    try:
        if not products:
            row = _stub_row(aoi_id, f"No .SAFE or L2A .zip products found under {safe_dir}. {MANUAL_NOTES}")
            write_csv(pd.DataFrame([row]), out_path)
            write_csv(
                pd.DataFrame(
                    columns=[
                        "aoi_id",
                        "scene_id",
                        "tile",
                        "sensing_date",
                        "ndvi_mean",
                        "ndmi_mean",
                        "cloud_filtered_pct",
                        "status",
                        "notes",
                    ]
                ),
                qa_path,
            )
            print(f"Wrote {out_path} (status={STUB_STATUS}, no products)")
            return 0

        scenes: list[SceneStats] = []
        for product in products:
            LOG.info("Processing %s (%s)", product.scene_id, product.sensing_date)
            scenes.append(_process_safe_scene(product, aoi_gdf))

        qa_rows = _scene_qa_rows(scenes, aoi_id)
        write_csv(pd.DataFrame(qa_rows), qa_path)

        ok_count = sum(1 for s in scenes if s.status == "processed")
        if ok_count == 0:
            row = _stub_row(
                aoi_id,
                f"Found {len(products)} SAFE product(s) but none produced clear AOI stats. See {qa_path.name}.",
            )
            write_csv(pd.DataFrame([row]), out_path)
            print(f"Wrote {out_path} (status={STUB_STATUS}, scenes=0/{len(products)})")
            return 0

        agg = _aggregate_scene_stats(
            scenes,
            period_start=args.period_start,
            period_end=args.period_end,
        )
        row = _processed_row(aoi_id, agg, change_notes=str(agg.get("change_notes", "")))
        write_csv(pd.DataFrame([row]), out_path)
        print(
            f"Wrote {out_path} (status={PROCESSED_STATUS}, scenes={agg['scenes_used']}/{len(products)}, "
            f"ndvi={agg.get('sentinel2_ndvi_mean')}, ndmi={agg.get('sentinel2_ndmi_mean')})"
        )
        print(f"Wrote {qa_path} ({len(qa_rows)} scene rows)")
        return 0
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    _configure_logging(args.verbose)
    out_path = _resolve_out_path(args)
    qa_path = _resolve_qa_out_path(args)
    aoi_gdf, aoi_id = load_aoi(args.aoi)

    try:
        if _safe_mode(args):
            return _run_safe_mode(args, aoi_gdf, aoi_id, out_path, qa_path)

        if not _local_raster_mode(args):
            row = _stub_row(aoi_id, MANUAL_NOTES)
            write_csv(pd.DataFrame([row]), out_path)
            print(f"Wrote {out_path} (status={STUB_STATUS})")
            return 0

        stats = _compute_period_stats(
            red_path=args.red,
            nir_path=args.nir,
            swir_path=args.swir,
            scl_path=args.scl,
            aoi_gdf=aoi_gdf,
            mask_snow=args.mask_snow,
        )
        ndvi_change, change_notes = _compute_ndvi_change(
            stats.get("ndvi_mean"),
            args,
            aoi_gdf,
            out_path,
        )
        row = _processed_row(
            aoi_id,
            {
                "sentinel2_ndvi_mean": stats.get("ndvi_mean"),
                "sentinel2_ndmi_mean": stats.get("ndmi_mean"),
                "cloud_filtered_pct": stats.get("cloud_filtered_pct"),
                "sentinel2_ndvi_change": ndvi_change,
                "sentinel2_ndmi_change": None,
                "period_start": args.period_start,
                "period_end": args.period_end,
                "scenes_used": 1,
                "tiles_used": "",
                "change_notes": change_notes,
            },
            change_notes=change_notes,
        )
        if ndvi_change is None and change_notes:
            row["change_notes"] = change_notes
        write_csv(pd.DataFrame([row]), out_path)
        print(
            f"Wrote {out_path} (status={PROCESSED_STATUS}, "
            f"ndvi={stats.get('ndvi_mean')}, ndmi={stats.get('ndmi_mean')})"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 — pipeline must not crash
        row = _stub_row(aoi_id, f"{MANUAL_NOTES} Error: {exc}")
        write_csv(pd.DataFrame([row]), out_path)
        print(f"Wrote {out_path} (status={STUB_STATUS}, error={exc})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
