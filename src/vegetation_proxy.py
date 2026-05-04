from __future__ import annotations

import logging

import pandas as pd

from src.config import DEMO_DATA_DIR

LOGGER = logging.getLogger(__name__)


def load_landcover_proxy_demo() -> pd.DataFrame:
    """
    Demo vegetation proxy loader.
    Uses precomputed corridor-level forest exposure scores from local demo file.
    """
    try:
        corridors = pd.read_csv(DEMO_DATA_DIR / "demo_corridors.csv")
        columns = ["demo_corridor_id", "region", "municipality", "forest_exposure_score"]
        return corridors[columns].copy()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed loading landcover proxy demo data: %s", exc)
        return pd.DataFrame()

