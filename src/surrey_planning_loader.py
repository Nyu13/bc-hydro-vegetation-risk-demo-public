"""Load Surrey vegetation-wildfire planning dataset for Streamlit dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import (
    SURREY_PLANNING_DATASET_CSV,
    SURREY_SENTINEL2_CORRIDOR_STATS_CSV,
    SURREY_SENTINEL2_SCENE_QA_CSV,
)
from src.okanagan_planning_loader import OkanaganPlanningLoadResult, load_okanagan_planning_dataset


def load_surrey_planning_dataset(csv_path: Path | None = None) -> OkanaganPlanningLoadResult:
    """Surrey uses the same tabular schema as the Okanagan planning dataset."""
    return load_okanagan_planning_dataset(csv_path or SURREY_PLANNING_DATASET_CSV)


def load_surrey_sentinel2_corridor_stats(csv_path: Path | None = None) -> pd.DataFrame:
    path = csv_path or SURREY_SENTINEL2_CORRIDOR_STATS_CSV
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_surrey_sentinel2_scene_qa(csv_path: Path | None = None) -> pd.DataFrame:
    path = csv_path or SURREY_SENTINEL2_SCENE_QA_CSV
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def merge_sentinel2_into_surrey_planning(planning_df: pd.DataFrame) -> pd.DataFrame:
    if planning_df.empty or "segment_id" not in planning_df.columns:
        return planning_df
    s2 = load_surrey_sentinel2_corridor_stats()
    if s2.empty:
        return planning_df
    if "segment_id" in s2.columns:
        extra_cols = [c for c in ("cloud_filtered_pct", "scenes_used", "period_start", "period_end") if c in s2.columns]
        if extra_cols:
            return planning_df.merge(
                s2[["segment_id", *extra_cols]].drop_duplicates("segment_id"),
                on="segment_id",
                how="left",
            )
    if "aoi_id" in s2.columns:
        row = s2.iloc[0]
        for col in ("cloud_filtered_pct", "scenes_used", "period_start", "period_end"):
            if col in row.index and col not in planning_df.columns:
                planning_df[col] = row[col]
    return planning_df


@dataclass(frozen=True)
class SurreyCausalAiSummary:
    aoi_rows: int
    discovery_rows: int
    intervention_types: tuple[str, ...]
    scene_date_min: str | None
    scene_date_max: str | None


def surrey_causal_ai_summary(
    *,
    aoi_csv: Path | None = None,
    discovery_csv: Path | None = None,
) -> SurreyCausalAiSummary | None:
    from src.config import SURREY_CAUSAL_AI_AOI_SCENARIOS_CSV, SURREY_CAUSAL_AI_DISCOVERY_CSV

    aoi_path = aoi_csv or SURREY_CAUSAL_AI_AOI_SCENARIOS_CSV
    disc_path = discovery_csv or SURREY_CAUSAL_AI_DISCOVERY_CSV
    if not aoi_path.is_file() and not disc_path.is_file():
        return None
    aoi_rows = 0
    interventions: list[str] = []
    date_min = date_max = None
    if aoi_path.is_file():
        aoi = pd.read_csv(aoi_path)
        aoi_rows = len(aoi)
        if "intervention_type" in aoi.columns:
            interventions = sorted(aoi["intervention_type"].dropna().astype(str).unique().tolist())
        if "scene_date" in aoi.columns:
            dates = pd.to_datetime(aoi["scene_date"], errors="coerce").dropna()
            if not dates.empty:
                date_min = dates.min().date().isoformat()
                date_max = dates.max().date().isoformat()
    disc_rows = 0
    if disc_path.is_file():
        disc_rows = len(pd.read_csv(disc_path))
    return SurreyCausalAiSummary(
        aoi_rows=aoi_rows,
        discovery_rows=disc_rows,
        intervention_types=tuple(interventions),
        scene_date_min=date_min,
        scene_date_max=date_max,
    )
