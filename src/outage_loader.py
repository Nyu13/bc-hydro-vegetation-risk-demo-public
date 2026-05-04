from __future__ import annotations

import logging
from io import BytesIO
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from src.config import (
    BC_HYDRO_OUTAGE_JSON_URL,
    BC_HYDRO_OUTAGE_RSS_URL,
    DEMO_OFFLINE_MODE,
    DEMO_DATA_DIR,
    UNOFFICIAL_SNAPSHOT_URL,
)

LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 15


def load_bchydro_outage_json(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """Load current/recent outage JSON; fallback to demo CSV on failure."""
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_outages.csv for outage JSON.")
        return pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
    try:
        response = requests.get(BC_HYDRO_OUTAGE_JSON_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            for key in ("outages", "data", "features"):
                if key in payload and isinstance(payload[key], list):
                    return pd.json_normalize(payload[key])
            return pd.json_normalize(payload)
        if isinstance(payload, list):
            return pd.json_normalize(payload)
        raise ValueError("Unexpected outage JSON shape.")
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Outage JSON unavailable; using demo fallback. Details: %s", exc)
            return pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
        LOGGER.info("Outage JSON unavailable; synthetic fallback disabled. Details: %s", exc)
        return pd.DataFrame(
            columns=["outage_id", "timestamp", "region", "municipality", "customers_affected", "cause", "status"]
        )


def load_bchydro_rss(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """Load public outage RSS; fallback to demo outages on failure."""
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_outages.csv for outage RSS.")
        demo = pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
        return demo.rename(columns={"timestamp": "pub_date", "outage_id": "guid"})
    try:
        response = requests.get(BC_HYDRO_OUTAGE_RSS_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        root = ET.parse(BytesIO(response.content)).getroot()

        items: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            items.append(
                {
                    "title": _safe_xml_text(item, "title"),
                    "description": _safe_xml_text(item, "description"),
                    "pub_date": _safe_xml_text(item, "pubDate"),
                    "link": _safe_xml_text(item, "link"),
                    "guid": _safe_xml_text(item, "guid"),
                }
            )

        if not items:
            raise ValueError("RSS returned no items.")
        return pd.DataFrame(items)
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Outage RSS unavailable; using demo fallback. Details: %s", exc)
            demo = pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
            return demo.rename(columns={"timestamp": "pub_date", "outage_id": "guid"})
        LOGGER.info("Outage RSS unavailable; synthetic fallback disabled. Details: %s", exc)
        return pd.DataFrame(columns=["title", "description", "pub_date", "link", "guid"])


def load_unofficial_outage_snapshots_placeholder(allow_synthetic_fallback: bool = True) -> pd.DataFrame:
    """
    Load unofficial public outage snapshots placeholder.
    Falls back to demo outages if unavailable.
    """
    if DEMO_OFFLINE_MODE:
        LOGGER.info("DEMO_OFFLINE_MODE enabled. Using local demo_outages.csv for unofficial snapshots.")
        return pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
    try:
        response = requests.get(UNOFFICIAL_SNAPSHOT_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return pd.json_normalize(payload)
        if isinstance(payload, dict):
            for key in ("outages", "data"):
                if key in payload and isinstance(payload[key], list):
                    return pd.json_normalize(payload[key])
            return pd.json_normalize(payload)
        raise ValueError("Unexpected unofficial snapshot JSON shape.")
    except Exception as exc:  # noqa: BLE001
        if allow_synthetic_fallback:
            LOGGER.info("Unofficial snapshot unavailable; using demo fallback. Details: %s", exc)
            return pd.read_csv(DEMO_DATA_DIR / "demo_outages.csv")
        LOGGER.info("Unofficial snapshot unavailable; synthetic fallback disabled. Details: %s", exc)
        return pd.DataFrame(
            columns=["outage_id", "timestamp", "region", "municipality", "customers_affected", "cause", "status"]
        )


def _safe_xml_text(parent: ET.Element, tag: str) -> str:
    node = parent.find(tag)
    return node.text.strip() if node is not None and node.text else ""

