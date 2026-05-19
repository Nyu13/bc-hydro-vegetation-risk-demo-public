from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from src.config import DEMO_DATA_DIR, PROCESSED_DATA_DIR

LOGGER = logging.getLogger(__name__)

REGION_SUMMARY_FILENAME = "region_summary.csv"
MUNICIPALITY_SUMMARY_FILENAME = "municipality_summary.csv"
DEMO_REGION_SUMMARY_FILENAME = "demo_region_outage_summary.csv"
DEMO_MUNICIPALITY_SUMMARY_FILENAME = "demo_municipality_outage_summary.csv"


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env_dir = os.getenv("EXTRACTOR_OUTPUT_DIR", "").strip()
    if env_dir:
        paths.append(Path(env_dir) / REGION_SUMMARY_FILENAME)
    paths.append(PROCESSED_DATA_DIR / REGION_SUMMARY_FILENAME)
    paths.append(DEMO_DATA_DIR / DEMO_REGION_SUMMARY_FILENAME)
    return paths


def load_region_outage_summary() -> tuple[pd.DataFrame, str]:
    """
    Load BC Hydro region outage summary from extractor output or bundled demo snapshot.

    Returns (dataframe, source_label).
    """
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            if "region_name" not in df.columns and "region" in df.columns:
                df = df.rename(columns={"region": "region_name"})
            if "region_name" not in df.columns:
                raise ValueError(f"Missing region_name in {path}")
            label = (
                "extractor processed output"
                if path.parent == PROCESSED_DATA_DIR or os.getenv("EXTRACTOR_OUTPUT_DIR")
                else "bundled demo snapshot (2025 unofficial archive)"
            )
            return df, f"{path.name} ({label})"
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read region summary at %s: %s", path, exc)
    return pd.DataFrame(), "not loaded"


def _municipality_candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env_dir = os.getenv("EXTRACTOR_OUTPUT_DIR", "").strip()
    if env_dir:
        paths.append(Path(env_dir) / MUNICIPALITY_SUMMARY_FILENAME)
    paths.append(PROCESSED_DATA_DIR / MUNICIPALITY_SUMMARY_FILENAME)
    paths.append(DEMO_DATA_DIR / DEMO_MUNICIPALITY_SUMMARY_FILENAME)
    return paths


def load_municipality_outage_summary() -> tuple[pd.DataFrame, str]:
    """Load municipality-level outage summary from extractor or bundled demo snapshot."""
    for path in _municipality_candidate_paths():
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            if "municipality" not in df.columns:
                raise ValueError(f"Missing municipality in {path}")
            if "region_name" not in df.columns and "region" in df.columns:
                df = df.rename(columns={"region": "region_name"})
            label = (
                "extractor processed output"
                if path.parent == PROCESSED_DATA_DIR or os.getenv("EXTRACTOR_OUTPUT_DIR")
                else "bundled demo snapshot (top municipalities)"
            )
            return df, f"{path.name} ({label})"
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read municipality summary at %s: %s", path, exc)
    return pd.DataFrame(), "not loaded"
