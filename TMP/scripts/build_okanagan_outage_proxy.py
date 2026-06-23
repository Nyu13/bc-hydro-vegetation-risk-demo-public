#!/usr/bin/env python3
"""
Build Okanagan outage proxy from unofficial BC Hydro public outage archive.

Outputs daily and summary CSVs for all places in the Okanagan/Kootenay BC Hydro region.
Labelled as unofficial public archive proxy — not operational outage history.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.config import DEMO_DATA_DIR, PROCESSED_DATA_DIR  # noqa: E402
from src.region_history_loader import _history_candidate_paths, _load_history_parquet  # noqa: E402
from src.regions import (  # noqa: E402
    OKANAGAN_BC_HYDRO_REGION,
    OKANAGAN_HISTORY_START_DATE,
    OKANAGAN_REGION_NAME,
)
from src.risk_scoring import calculate_municipality_outage_history_score  # noqa: E402

from _okanagan_pipeline_common import ensure_dirs, today_iso, write_csv  # noqa: E402

SUMMARY_OUT = PROCESSED_DATA_DIR / "okanagan_outage_proxy_summary.csv"
DAILY_OUT = PROCESSED_DATA_DIR / "okanagan_outage_daily_proxy.csv"

OUTPUT_DAILY_COLS = [
    "date",
    "municipality",
    "public_outage_count",
    "public_customers_affected",
    "tree_related_outage_proxy",
    "weather_related_outage_proxy",
    "outage_history_proxy_score",
    "data_status",
    "data_source_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _normalize_municipality(name: str) -> str:
    return str(name or "").strip()


def _region_column(df: pd.DataFrame) -> str | None:
    if "region_name" in df.columns:
        return "region_name"
    if "region" in df.columns:
        return "region"
    return None


def _load_municipality_summary() -> pd.DataFrame:
    candidates = [
        PROCESSED_DATA_DIR / "municipality_summary.csv",
        DEMO_DATA_DIR / "demo_municipality_outage_summary.csv",
    ]
    for path in candidates:
        if path.is_file():
            df = pd.read_csv(path)
            if "region" in df.columns and "region_name" not in df.columns:
                df = df.rename(columns={"region": "region_name"})
            return df
    return pd.DataFrame()


def _filter_okanagan_summary(mun_df: pd.DataFrame) -> pd.DataFrame:
    """All municipalities/places in the Okanagan/Kootenay BC Hydro region."""
    if mun_df.empty:
        return mun_df
    region_col = _region_column(mun_df)
    if region_col is None:
        return pd.DataFrame()
    return mun_df.loc[mun_df[region_col].astype(str) == OKANAGAN_BC_HYDRO_REGION].copy()


def _filter_okanagan_history(history: pd.DataFrame) -> pd.DataFrame:
    """Parquet rows for Okanagan/Kootenay; municipality labels kept as archived (incl. compounds)."""
    region_col = _region_column(history)
    if region_col is None:
        return pd.DataFrame()
    work = history.loc[history[region_col].astype(str) == OKANAGAN_BC_HYDRO_REGION].copy()
    mun_col = "municipality" if "municipality" in work.columns else None
    if mun_col is None:
        return pd.DataFrame()
    work[mun_col] = work[mun_col].astype(str).str.strip()
    work = work.loc[work[mun_col].astype(str).str.len() > 0]
    return work


def _archive_date_bounds(history: pd.DataFrame, date_col: str) -> tuple[str | None, str | None]:
    parsed = pd.to_datetime(history[date_col], errors="coerce")
    valid = parsed.dropna()
    if valid.empty:
        return None, None
    return valid.min().strftime("%Y-%m-%d"), valid.max().strftime("%Y-%m-%d")


def _history_daily_from_parquet() -> pd.DataFrame | None:
    history = _load_history_parquet()
    if history is None or history.empty:
        return None

    work = _filter_okanagan_history(history)
    if work.empty:
        return None

    mun_col = "municipality"
    date_col = next((c for c in ("snapshot_date", "date_off", "date", "pub_date") if c in work.columns), None)
    if date_col is None:
        return None

    work["date"] = pd.to_datetime(work[date_col], errors="coerce").dt.date.astype(str)
    work = work.dropna(subset=["date"])
    archive_min, archive_max = _archive_date_bounds(work, "date")
    work = work.loc[work["date"] >= OKANAGAN_HISTORY_START_DATE]
    if work.empty:
        print(
            f"WARNING: No Okanagan/Kootenay outage rows on/after {OKANAGAN_HISTORY_START_DATE} "
            f"(archive range for region: {archive_min} .. {archive_max})."
        )
        return None

    cust_col = next((c for c in ("num_customers_out", "customers_affected") if c in work.columns), None)
    cause_col = "cause" if "cause" in work.columns else None

    rows: list[dict] = []
    for (dt, mun), grp in work.groupby(["date", mun_col]):
        customers = int(pd.to_numeric(grp[cust_col], errors="coerce").fillna(0).sum()) if cust_col else 0
        count = int(len(grp))
        tree_proxy = 0
        weather_proxy = 0
        if cause_col:
            causes = grp[cause_col].astype(str).str.lower()
            tree_proxy = int(causes.str.contains("tree|vegetation|branch|limb", regex=True, na=False).sum())
            weather_proxy = int(causes.str.contains("weather|wind|storm|lightning|ice|snow", regex=True, na=False).sum())
        rows.append(
            {
                "date": dt,
                "municipality": mun,
                "public_outage_count": count,
                "public_customers_affected": customers,
                "tree_related_outage_proxy": tree_proxy,
                "weather_related_outage_proxy": weather_proxy,
            }
        )
    return pd.DataFrame(rows)


def _synthetic_daily_from_summary(summary_rows: pd.DataFrame, *, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(
        start=OKANAGAN_HISTORY_START_DATE,
        end=pd.Timestamp.today(),
        freq="D",
    ).strftime("%Y-%m-%d")
    rows: list[dict] = []
    for _, row in summary_rows.iterrows():
        mun = str(row["municipality"])
        base_count = max(1, int(row.get("unique_outages", 10) / 30))
        tree_ratio = float(row.get("tree_related_outage_count", 0)) / max(float(row.get("unique_outages", 1)), 1)
        weather_ratio = float(row.get("weather_related_outage_count", 0)) / max(float(row.get("unique_outages", 1)), 1)
        priority = float(row.get("suggested_priority_score", 0.25))
        for dt in dates:
            noise = rng.uniform(0.6, 1.4)
            count = max(0, int(round(base_count * noise)))
            customers = int(count * float(row.get("avg_customers_per_unique_outage", 100) or 100))
            tree_proxy = int(round(count * tree_ratio))
            weather_proxy = int(round(count * weather_ratio))
            rows.append(
                {
                    "date": dt,
                    "municipality": mun,
                    "public_outage_count": count,
                    "public_customers_affected": customers,
                    "tree_related_outage_proxy": tree_proxy,
                    "weather_related_outage_proxy": weather_proxy,
                    "outage_history_proxy_score": calculate_municipality_outage_history_score(priority),
                    "data_status": "synthetic_daily_from_summary",
                    "data_source_notes": (
                        "Unofficial public archive proxy — synthetic daily spread from municipality "
                        "summary (deterministic seed). Not BC Hydro operational outage history."
                    ),
                }
            )
    return pd.DataFrame(rows)


def _build_summary_from_history(history: pd.DataFrame) -> pd.DataFrame:
    """Roll up archive rows into municipality summary when municipality_summary.csv is missing."""
    work = _filter_okanagan_history(history)
    if work.empty:
        return pd.DataFrame()

    mun_col = "municipality"
    cust_col = next((c for c in ("num_customers_out", "customers_affected") if c in work.columns), None)
    rows: list[dict] = []
    for mun, grp in work.groupby(mun_col):
        unique = int(grp["outage_id"].nunique()) if "outage_id" in grp.columns else int(len(grp))
        customers = pd.to_numeric(grp[cust_col], errors="coerce").fillna(0) if cust_col else pd.Series([0] * len(grp))
        tree = int(grp.get("is_tree_related", pd.Series(dtype=bool)).fillna(False).sum())
        weather = int(grp.get("is_weather_related", pd.Series(dtype=bool)).fillna(False).sum())
        priority = min(1.0, 0.15 + 0.0005 * unique + 0.001 * tree)
        rows.append(
            {
                "municipality": mun,
                "region_name": OKANAGAN_BC_HYDRO_REGION,
                "unique_outages": unique,
                "avg_customers_per_unique_outage": round(float(customers.mean()), 2) if len(customers) else 0.0,
                "tree_related_outage_count": tree,
                "weather_related_outage_count": weather,
                "suggested_priority_score": round(priority, 4),
                "data_status": "parquet_archive_rollup",
                "data_source_notes": (
                    f"Rolled up from bchydro_public_outages_history.parquet for {OKANAGAN_BC_HYDRO_REGION}."
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    args = parse_args()
    mun_df = _load_municipality_summary()
    okanagan_summary = _filter_okanagan_summary(mun_df)

    if okanagan_summary.empty:
        history = _load_history_parquet()
        if history is not None and not history.empty:
            okanagan_summary = _build_summary_from_history(history)
            print(
                f"WARNING: municipality_summary missing Okanagan/Kootenay rows — "
                f"rolled up {len(okanagan_summary)} places from parquet."
            )

    if okanagan_summary.empty:
        print(f"ERROR: No Okanagan/Kootenay municipality summary or parquet history available.")
        return 1

    summary_out = okanagan_summary.copy()
    if "outage_history_proxy_score" not in summary_out.columns:
        summary_out["outage_history_proxy_score"] = summary_out.get(
            "suggested_priority_score", 0.25
        ).apply(lambda v: calculate_municipality_outage_history_score(float(v)))
    summary_out["region"] = OKANAGAN_REGION_NAME
    summary_out["as_of_date"] = today_iso()
    summary_out["history_start_date"] = OKANAGAN_HISTORY_START_DATE
    if "data_status" not in summary_out.columns:
        summary_out["data_status"] = "unofficial_archive_proxy"
    if "data_source_notes" not in summary_out.columns:
        summary_out["data_source_notes"] = (
            f"Unofficial BC Hydro public outage archive proxy — all {OKANAGAN_BC_HYDRO_REGION} "
            "municipalities/places from municipality summary. Not validated for operational planning."
        )

    place_count = summary_out["municipality"].nunique()
    daily = _history_daily_from_parquet()
    if daily is not None and not daily.empty:
        daily_min = daily["date"].min()
        daily_max = daily["date"].max()
        daily["outage_history_proxy_score"] = 50.0
        daily["data_status"] = "parquet_archive_proxy"
        daily["data_source_notes"] = (
            f"Derived from bchydro_public_outages_history.parquet filtered to {OKANAGAN_BC_HYDRO_REGION} "
            f"({place_count} places, raw municipality labels incl. multi-place strings) "
            f"with date >= {OKANAGAN_HISTORY_START_DATE} (daily range {daily_min} .. {daily_max}). "
            "Unofficial public archive — not BC Hydro internal history."
        )
        pri_lookup = summary_out.set_index("municipality")["suggested_priority_score"].to_dict()
        for idx, row in daily.iterrows():
            pri = pri_lookup.get(row["municipality"])
            if pri is not None and not pd.isna(pri):
                daily.at[idx, "outage_history_proxy_score"] = calculate_municipality_outage_history_score(float(pri))
    else:
        hist_paths = [str(p) for p in _history_candidate_paths() if p.is_file()]
        note = (
            f"Parquet history not found or empty after {OKANAGAN_HISTORY_START_DATE} — "
            "synthetic daily from municipality summary. "
            f"Searched: {', '.join(hist_paths) or 'none'}"
        )
        print(f"WARNING: {note}")
        daily = _synthetic_daily_from_summary(summary_out, seed=args.seed)
        if "data_source_notes" in daily.columns:
            daily["data_source_notes"] = daily["data_source_notes"] + f" {note}"

    ensure_dirs(SUMMARY_OUT.parent)
    write_csv(summary_out, SUMMARY_OUT)
    write_csv(daily[OUTPUT_DAILY_COLS], DAILY_OUT)
    synthetic_summary = int((summary_out.get("data_status", "") == "synthetic_municipality_placeholder").sum())
    print(f"Wrote {len(summary_out)} places ({place_count} unique municipalities) to {SUMMARY_OUT}")
    if synthetic_summary:
        print(f"  ({synthetic_summary} synthetic municipality placeholders)")
    print(
        f"Wrote {len(daily)} daily rows to {DAILY_OUT} "
        f"(date range {daily['date'].min()} .. {daily['date'].max()}, start filter {OKANAGAN_HISTORY_START_DATE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
