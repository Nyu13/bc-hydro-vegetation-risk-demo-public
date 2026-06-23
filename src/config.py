from __future__ import annotations

from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DEMO_DATA_DIR = DATA_DIR / "demo"
DOCS_DIR = PROJECT_ROOT / "docs"

# --- Demo region constants (also re-exported from src.regions for modular imports) ---
SURREY_REGION_NAME = "Surrey"
SURREY_BC_HYDRO_REGION = "Lower Mainland"
SURREY_AOI_BBOX = (-123.05, 49.02, -122.65, 49.35)  # min_lon, min_lat, max_lon, max_lat
SURREY_AOI_WKT = (
    "POLYGON((-123.05 49.02, -122.65 49.02, -122.65 49.35, -123.05 49.35, -123.05 49.02))"
)
SURREY_PILOT_LAT = 49.19
SURREY_PILOT_LON = -122.85
SURREY_MAP_ZOOM = 10.5

OKANAGAN_REGION_NAME = "Kelowna / Okanagan"
OKANAGAN_AOI_BBOX = (-120.20, 49.50, -118.80, 50.50)  # min_lon, min_lat, max_lon, max_lat
OKANAGAN_AOI_WKT = (
    "POLYGON((-120.20 49.50, -118.80 49.50, -118.80 50.50, -120.20 50.50, -120.20 49.50))"
)
OKANAGAN_PILOT_LAT = 49.888
OKANAGAN_PILOT_LON = -119.496
OKANAGAN_MAP_ZOOM = 9.0
OKANAGAN_MUNICIPALITIES = (
    "Kelowna",
    "West Kelowna",
    "Lake Country",
    "Peachland",
    "Vernon",
    "Regional District of Central Okanagan",
)
OKANAGAN_BC_HYDRO_REGION = "Okanagan/Kootenay"
OKANAGAN_CORRIDOR_BUFFER_M = 200
OKANAGAN_SEGMENT_LENGTH_KM = 5.0
OKANAGAN_HISTORY_START_DATE = "2026-01-01"

# BC Geographic Warehouse transmission lines (optional local KML/WFS; bundled sample for Cloud)
BC_TRANSMISSION_KML = DATA_DIR / "WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml"
BC_TRANSMISSION_GEOJSON = DEMO_DATA_DIR / "demo_bc_transmission_lines_sample.geojson"
BC_TRANSMISSION_LOWER_MAINLAND_BUNDLED_GEOJSON = (
    DEMO_DATA_DIR / "bc_transmission_lines_lower_mainland.geojson"
)
BC_TRANSMISSION_LOWER_MAINLAND_GEOJSON = (
    PROCESSED_DATA_DIR / "bc_transmission_lines_lower_mainland.geojson"
)
BC_TRANSMISSION_BC_GEOJSON = PROCESSED_DATA_DIR / "bc_transmission_lines_bc.geojson"
# Province-wide HV lines for Okanagan map context (no AOI clip)
BC_TRANSMISSION_LINES_GEOJSON = PROCESSED_DATA_DIR / "bc_transmission_lines.geojson"
BC_TRANSMISSION_WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
BC_TRANSMISSION_WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
# WFS bbox filters must use EPSG:3005; this WGS84 box matches the demo / export scripts
BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84 = (-123.25, 49.05, -122.35, 49.45)
BC_TRANSMISSION_PROVINCE_BBOX_WGS84 = (-139.06, 48.30, -114.03, 60.00)

BC_HYDRO_OUTAGE_JSON_URL = "https://www.bchydro.com/power-outages/app/outages-map-data.json"
BC_HYDRO_OUTAGE_RSS_URL = "https://www.bchydro.com/rss/outages/all.xml"
# Corporate Python 3.14+ on Windows often fails BC Hydro TLS (Missing Authority Key Identifier).
# Unset on Windows or Streamlit Cloud: verify off by default (no failed verify attempt).
# Set BC_HYDRO_SSL_VERIFY=1 to force verify. On other local platforms, unset defaults to verify on.
# Streamlit Cloud: set BC_HYDRO_SSL_VERIFY=0 in app Secrets if live outages fail (see README).


def _running_on_streamlit_cloud() -> bool:
    if os.getenv("STREAMLIT_RUNTIME_ENVIRONMENT", "").strip().lower() == "cloud":
        return True
    return os.getenv("USER", "").strip().lower() == "appuser"


def _default_bc_hydro_ssl_verify() -> bool:
    if sys.platform == "win32":
        return False
    if _running_on_streamlit_cloud():
        return False
    return True


def _parse_bc_hydro_ssl_verify(raw: str | None) -> bool:
    if raw is None:
        return _default_bc_hydro_ssl_verify()
    return raw.strip().lower() not in {"0", "false", "no"}


def bc_hydro_ssl_verify() -> bool:
    """Read BC_HYDRO_SSL_VERIFY from the environment (call per HTTP request)."""
    return _parse_bc_hydro_ssl_verify(os.getenv("BC_HYDRO_SSL_VERIFY"))


BC_HYDRO_SSL_VERIFY = bc_hydro_ssl_verify()

DEMO_PRIMARY_DISCLAIMER = (
    "Proof-of-process demo using public and proxy data only. "
    "Not outage prediction or operational decision support."
)

DEMO_SECONDARY_DISCLAIMER = (
    "A formal PoC would require BC Hydro internal outage history, feeder/circuit topology, "
    "vegetation records, asset condition, and operational data."
)

DEMO_DISCLAIMER = DEMO_SECONDARY_DISCLAIMER

DEMO_OFFLINE_MODE = os.getenv("DEMO_OFFLINE_MODE", "0").strip().lower() in {"1", "true", "yes"}

# Live Streamlit demo defaults to Okanagan / Kootenay planning workflow.
DEMO_DEFAULT_REGION = OKANAGAN_REGION_NAME

# Legacy Surrey pilot constants — used by TMP/scripts and Surrey pipeline outputs, not the live demo UI.
DEMO_PILOT_MUNICIPALITY = SURREY_REGION_NAME
DEMO_PILOT_REGION = SURREY_BC_HYDRO_REGION
DEMO_PILOT_BC_HYDRO_REGION = SURREY_BC_HYDRO_REGION
DEMO_PILOT_LAT = SURREY_PILOT_LAT
DEMO_PILOT_LON = SURREY_PILOT_LON
DEMO_PILOT_MAP_ZOOM = SURREY_MAP_ZOOM
DEMO_PILOT_TRANSMISSION_BBOX = SURREY_AOI_BBOX
DEMO_PILOT_DISCLAIMER = f"Legacy pilot: {DEMO_PILOT_MUNICIPALITY} ({DEMO_PILOT_REGION})"

# Legacy region-mode selector (removed from Streamlit UI; kept for script compatibility).
DEMO_REGION_MODE_SURREY = "Surrey baseline"
DEMO_REGION_MODE_OKANAGAN = OKANAGAN_REGION_NAME
DEMO_REGION_MODE_OPTIONS = (DEMO_REGION_MODE_SURREY, DEMO_REGION_MODE_OKANAGAN)
DEMO_REGION_OPTIONS = (f"{SURREY_REGION_NAME}, BC",)

DEMO_DATA_MODES = (
    "Public/proxy only",
    "Planet sample enabled",
    "Synthetic fallback",
)

PLANET_SURREY_SAMPLE_CSV = DEMO_DATA_DIR / "planet_surrey_sample_placeholder.csv"

# Optional processed open/free data outputs (see docs/free_data_pipeline_runbook.md)
SURREY_WORLDCOVER_STATS_CSV = PROCESSED_DATA_DIR / "surrey_worldcover_corridor_stats.csv"
SURREY_FREE_DATA_SUMMARY_CSV = PROCESSED_DATA_DIR / "surrey_free_data_corridor_summary.csv"
SURREY_FREE_DATA_PLACEHOLDER_CSV = DEMO_DATA_DIR / "surrey_free_data_corridor_summary_placeholder.csv"
SURREY_SENTINEL2_STATS_CSV = PROCESSED_DATA_DIR / "surrey_sentinel2_corridor_stats.csv"
SURREY_SENTINEL2_SCENE_QA_CSV = PROCESSED_DATA_DIR / "surrey_sentinel2_scene_qa.csv"
SURREY_ECCC_WEATHER_STRESS_CSV = PROCESSED_DATA_DIR / "surrey_eccc_weather_stress_stats.csv"

# Kelowna / Okanagan planning demo outputs (see TMP/scripts/build_okanagan_demo_pipeline.py)
OKANAGAN_PLANNING_DATASET_CSV = PROCESSED_DATA_DIR / "okanagan_vegetation_wildfire_planning_dataset.csv"
OKANAGAN_CORRIDOR_SEGMENTS_GEOJSON = PROCESSED_DATA_DIR / "okanagan_corridor_segments.geojson"
OKANAGAN_TRANSMISSION_LINES_GEOJSON = PROCESSED_DATA_DIR / "okanagan_transmission_lines.geojson"
OKANAGAN_CORRIDOR_BUFFER_GEOJSON = PROCESSED_DATA_DIR / "okanagan_corridor_buffer_200m.geojson"
OKANAGAN_FWI_SAMPLE_CSV = PROCESSED_DATA_DIR / "okanagan_fwi_sample.csv"
OKANAGAN_FWI_CORRIDOR_CSV = PROCESSED_DATA_DIR / "okanagan_fwi_corridor_sample.csv"
OKANAGAN_WILDFIRE_EXPOSURE_CSV = PROCESSED_DATA_DIR / "okanagan_cwfis_wildfire_exposure.csv"
OKANAGAN_WEATHER_STRESS_CSV = PROCESSED_DATA_DIR / "okanagan_weather_stress_stats.csv"
OKANAGAN_WEATHER_STRESS_DAILY_CSV = PROCESSED_DATA_DIR / "okanagan_weather_stress_daily.csv"
OKANAGAN_OUTAGE_DAILY_PROXY_CSV = PROCESSED_DATA_DIR / "okanagan_outage_daily_proxy.csv"
OKANAGAN_TRANSMISSION_QA_CSV = PROCESSED_DATA_DIR / "okanagan_transmission_qa_summary.csv"
OKANAGAN_SENTINEL2_CORRIDOR_STATS_CSV = PROCESSED_DATA_DIR / "okanagan_sentinel2_corridor_stats.csv"
OKANAGAN_SENTINEL2_SCENE_QA_CSV = PROCESSED_DATA_DIR / "okanagan_sentinel2_scene_qa.csv"

OKANAGAN_PLANNING_DISCLAIMER = (
    "Kelowna / Okanagan proof-of-process: public and proxy layers show where vegetation, wildfire, "
    "weather stress, outage history, and treatment gaps overlap."
)

PLANET_POC_DISCLAIMER = (
    "Planet layers are proposed remote-sensing inputs for legacy Surrey pipeline scripts. "
    "Not used in the Okanagan live demo."
)
