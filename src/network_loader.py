from __future__ import annotations

import logging

import pandas as pd

from src.config import DEMO_DATA_DIR

LOGGER = logging.getLogger(__name__)


def load_transmission_lines() -> pd.DataFrame:
    """
    Load demo corridor segments derived from public transmission-line proxy.
    """
    try:
        df = pd.read_csv(DEMO_DATA_DIR / "demo_corridors.csv")
        return df
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to load demo corridor data: %s", exc)
        return pd.DataFrame()

