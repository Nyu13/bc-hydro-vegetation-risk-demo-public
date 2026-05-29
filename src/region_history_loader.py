from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from src.config import DEMO_DATA_DIR, PROCESSED_DATA_DIR
from src.data_provenance import tag_dataframe

LOGGER = logging.getLogger(__name__)

REGION_SUMMARY_FILENAME = "region_summary.csv"
MUNICIPALITY_SUMMARY_FILENAME = "municipality_summary.csv"
HISTORY_FILENAME = "bchydro_public_outages_history.parquet"
DEMO_REGION_SUMMARY_FILENAME = "demo_region_outage_summary.csv"
DEMO_MUNICIPALITY_SUMMARY_FILENAME = "demo_municipality_outage_summary.csv"

CUSTOMER_METRIC_COLS = ("avg_customers_per_unique_outage",)

REGION_SUMMARY_DISPLAY_COLS = (
    "region_name",
    "unique_outages",
    "avg_customers_per_unique_outage",
    "tree_related_outage_count",
    "weather_related_outage_count",
    "suggested_priority_score",
    "first_snapshot_date",
    "last_snapshot_date",
)

MUNICIPALITY_SUMMARY_DISPLAY_COLS = (
    "municipality",
    "region_name",
    "unique_outages",
    "avg_customers_per_unique_outage",
    "tree_related_outage_count",
    "weather_related_outage_count",
    "suggested_priority_score",
)

# Snapshot-row sums/means — never shown in Area selection UI
_SNAPSHOT_CUSTOMER_COLS = frozenset(
    {
        "total_customers_affected",
        "average_customers_affected",
        "median_customers_per_outage",
        "max_customers_affected",
    }
)


def _candidate_paths(filename: str, demo_filename: str) -> list[Path]:
    paths: list[Path] = []
    env_dir = os.getenv("EXTRACTOR_OUTPUT_DIR", "").strip()
    if env_dir:
        paths.append(Path(env_dir) / filename)
    paths.append(PROCESSED_DATA_DIR / filename)
    paths.append(DEMO_DATA_DIR / demo_filename)
    return paths


def _history_candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env_dir = os.getenv("EXTRACTOR_OUTPUT_DIR", "").strip()
    if env_dir:
        paths.append(Path(env_dir) / HISTORY_FILENAME)
    paths.append(PROCESSED_DATA_DIR / HISTORY_FILENAME)
    default_extractor = Path(r"C:\workspace\bchydro-outage-history-extractor\data\processed")
    paths.append(default_extractor / HISTORY_FILENAME)
    return paths


def _load_history_parquet() -> pd.DataFrame | None:
    for path in _history_candidate_paths():
        if not path.is_file():
            continue
        try:
            return pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read history at %s: %s", path, exc)
    return None


def _max_customers_per_outage(grp: pd.DataFrame) -> pd.Series:
    if "outage_id" in grp.columns and grp["outage_id"].notna().any():
        return grp.groupby("outage_id", dropna=True)["num_customers_out"].max().fillna(0)
    deduped = grp.drop_duplicates(subset=["gis_id", "date_off", "area", "cause"])
    return deduped["num_customers_out"].fillna(0)


def _customer_metrics_from_history(
    history_df: pd.DataFrame,
    group_cols: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, grp in history_df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        per_outage = _max_customers_per_outage(grp)
        customers = grp["num_customers_out"].fillna(0)
        row = dict(zip(group_cols, keys))
        row["avg_customers_per_unique_outage"] = (
            float(per_outage.mean()) if len(per_outage) else 0.0
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _normalize_cause_count_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Canonicalize deduped unique-outage cause counts (extractor column names)."""
    out = df.copy()
    legacy_map = (
        ("tree_related_unique_outages", "tree_related_outage_count"),
        ("weather_related_unique_outages", "weather_related_outage_count"),
    )
    for legacy, canonical in legacy_map:
        if canonical not in out.columns and legacy in out.columns:
            out[canonical] = out[legacy]
        if legacy in out.columns and canonical in out.columns:
            out[canonical] = out[canonical].fillna(out[legacy])
        if legacy in out.columns:
            out = out.drop(columns=[legacy])
    for col in ("tree_related_outage_count", "weather_related_outage_count"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def select_display_columns(df: pd.DataFrame, *, municipality: bool) -> list[str]:
    """Columns safe for Area selection tables (unique-outage metrics only)."""
    preferred = (
        MUNICIPALITY_SUMMARY_DISPLAY_COLS if municipality else REGION_SUMMARY_DISPLAY_COLS
    )
    return [c for c in preferred if c in df.columns]


def _enrich_customer_metrics(df: pd.DataFrame, *, municipality: bool) -> pd.DataFrame:
    if df.empty or all(col in df.columns for col in CUSTOMER_METRIC_COLS):
        return df

    history_df = _load_history_parquet()
    if history_df is None or "num_customers_out" not in history_df.columns:
        return df

    group_cols = ["region_name", "municipality"] if municipality else ["region_name"]
    if municipality and "municipality" not in history_df.columns:
        return df
    if "region_name" not in history_df.columns and "region" in history_df.columns:
        history_df = history_df.rename(columns={"region": "region_name"})

    metrics = _customer_metrics_from_history(history_df, group_cols)
    merge_cols = [c for c in group_cols if c in df.columns]
    if not merge_cols:
        return df

    enriched = df.merge(metrics, on=merge_cols, how="left", suffixes=("", "_computed"))
    for col in CUSTOMER_METRIC_COLS:
        computed = f"{col}_computed"
        if col not in enriched.columns and computed in enriched.columns:
            enriched[col] = enriched[computed]
        elif col in enriched.columns and computed in enriched.columns:
            enriched[col] = enriched[col].fillna(enriched[computed])
        if computed in enriched.columns:
            enriched = enriched.drop(columns=[computed])
    return enriched


def _source_label(path: Path, *, bundled_demo: bool) -> str:
    if path.parent == PROCESSED_DATA_DIR or os.getenv("EXTRACTOR_OUTPUT_DIR"):
        return "extractor processed output"
    if bundled_demo:
        return "bundled demo snapshot (unofficial archive)"
    return "bundled demo snapshot (top municipalities)"


def load_region_outage_summary() -> tuple[pd.DataFrame, str]:
    """
    Load BC Hydro region outage summary from extractor output or bundled demo snapshot.

    Returns (dataframe, source_label).
    """
    for path in _candidate_paths(REGION_SUMMARY_FILENAME, DEMO_REGION_SUMMARY_FILENAME):
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            if "region_name" not in df.columns and "region" in df.columns:
                df = df.rename(columns={"region": "region_name"})
            if "region_name" not in df.columns:
                raise ValueError(f"Missing region_name in {path}")
            df = _normalize_cause_count_columns(_enrich_customer_metrics(df, municipality=False))
            drop_cols = [c for c in _SNAPSHOT_CUSTOMER_COLS if c in df.columns]
            if drop_cols:
                df = df.drop(columns=drop_cols)
            bundled_demo = path.name.startswith("demo_")
            label = _source_label(path, bundled_demo=bundled_demo)
            source_label = f"{path.name} ({label})"
            df = tag_dataframe(
                df,
                is_synthetic=bundled_demo,
                source=source_label,
            )
            return df, source_label
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read region summary at %s: %s", path, exc)
    return pd.DataFrame(), "not loaded"


def load_municipality_outage_summary() -> tuple[pd.DataFrame, str]:
    """Load municipality-level outage summary from extractor or bundled demo snapshot."""
    for path in _candidate_paths(MUNICIPALITY_SUMMARY_FILENAME, DEMO_MUNICIPALITY_SUMMARY_FILENAME):
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            if "municipality" not in df.columns:
                raise ValueError(f"Missing municipality in {path}")
            if "region_name" not in df.columns and "region" in df.columns:
                df = df.rename(columns={"region": "region_name"})
            df = _normalize_cause_count_columns(_enrich_customer_metrics(df, municipality=True))
            drop_cols = [c for c in _SNAPSHOT_CUSTOMER_COLS if c in df.columns]
            if drop_cols:
                df = df.drop(columns=drop_cols)
            bundled_demo = path.name.startswith("demo_")
            label = _source_label(path, bundled_demo=bundled_demo)
            source_label = f"{path.name} ({label})"
            df = tag_dataframe(
                df,
                is_synthetic=bundled_demo,
                source=source_label,
            )
            return df, source_label
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not read municipality summary at %s: %s", path, exc)
    return pd.DataFrame(), "not loaded"
