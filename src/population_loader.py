from __future__ import annotations

import logging

import pandas as pd

from src.config import DEMO_DATA_DIR

LOGGER = logging.getLogger(__name__)

POPULATION_COLUMNS = (
    "municipality",
    "region",
    "population_2021",
    "lat",
    "lon",
    "source_note",
)


def load_municipality_population() -> pd.DataFrame:
    """Bundled 2021 Census population by municipality (demo subset)."""
    path = DEMO_DATA_DIR / "demo_municipality_population.csv"
    try:
        df = pd.read_csv(path)
        for col in POPULATION_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Missing column {col!r} in {path.name}")
        df["population_2021"] = pd.to_numeric(df["population_2021"], errors="coerce")
        return df.dropna(subset=["municipality", "population_2021"])
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to load municipality population: %s", exc)
        return pd.DataFrame(columns=list(POPULATION_COLUMNS))


def attach_population(df: pd.DataFrame, population: pd.DataFrame | None = None) -> pd.DataFrame:
    """Left-merge population onto rows with a municipality column."""
    if df.empty or "municipality" not in df.columns:
        return df
    pop = population if population is not None else load_municipality_population()
    if pop.empty:
        return df
    merge_cols = ["municipality", "population_2021", "source_note"]
    if "region" in df.columns and "region" in pop.columns:
        merged = df.merge(
            pop[merge_cols + ["region"]],
            on=["municipality", "region"],
            how="left",
        )
        missing = merged["population_2021"].isna()
        if missing.any():
            fallback = df.loc[missing, ["municipality"]].merge(
                pop.drop_duplicates("municipality")[merge_cols],
                on="municipality",
                how="left",
            )
            merged.loc[missing, "population_2021"] = fallback["population_2021"].values
            merged.loc[missing, "source_note"] = fallback["source_note"].values
        return merged
    return df.merge(pop.drop_duplicates("municipality")[merge_cols], on="municipality", how="left")


def population_marker_radius(
    population: float | int | None,
    *,
    base_m: float = 8000,
    min_m: float = 4500,
    max_m: float = 22000,
    reference_pop: float = 100_000,
) -> int:
    """Scale disk radius (meters) sub-linearly by population for pydeck."""
    if population is None or pd.isna(population) or float(population) <= 0:
        return int(base_m)
    import math

    scale = math.sqrt(float(population) / reference_pop)
    radius = base_m * max(0.55, min(2.75, scale))
    return int(max(min_m, min(max_m, radius)))
