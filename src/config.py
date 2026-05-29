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
BC_TRANSMISSION_WFS_URL = "https://openmaps.gov.bc.ca/geo/pub/wfs"
BC_TRANSMISSION_WFS_LAYER = "pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP"
# WFS bbox filters must use EPSG:3005; this WGS84 box matches the demo / export scripts
BC_TRANSMISSION_LOWER_MAINLAND_BBOX_WGS84 = (-123.25, 49.05, -122.35, 49.45)
BC_TRANSMISSION_PROVINCE_BBOX_WGS84 = (-139.06, 48.30, -114.03, 60.00)

BC_HYDRO_OUTAGE_JSON_URL = "https://www.bchydro.com/power-outages/app/outages-map-data.json"
BC_HYDRO_OUTAGE_RSS_URL = "https://www.bchydro.com/rss/outages/all.xml"
# Corporate Python 3.14+ on Windows often fails BC Hydro TLS (Missing Authority Key Identifier).
# Unset on Windows: verify off by default (no failed verify attempt). Set BC_HYDRO_SSL_VERIFY=1 to force verify.
# Other platforms default to verify on; set BC_HYDRO_SSL_VERIFY=0 to skip verify entirely.


def _parse_bc_hydro_ssl_verify(raw: str | None) -> bool:
    if raw is None:
        return sys.platform != "win32"
    return raw.strip().lower() not in {"0", "false", "no"}


def bc_hydro_ssl_verify() -> bool:
    """Read BC_HYDRO_SSL_VERIFY from the environment (call per HTTP request)."""
    return _parse_bc_hydro_ssl_verify(os.getenv("BC_HYDRO_SSL_VERIFY"))


BC_HYDRO_SSL_VERIFY = bc_hydro_ssl_verify()

DEMO_PRIMARY_DISCLAIMER = (
    "This demo illustrates dashboard workflow and analytical logic only. "
    "It does not predict BC Hydro outages and should not be used for operational decisions."
)

DEMO_SECONDARY_DISCLAIMER = (
    "Demo only — uses public and proxy datasets. A formal PoC would require BC Hydro "
    "internal outage history, feeder/circuit topology, vegetation records, asset "
    "condition, and operational data."
)

# Backwards compatibility for imports
DEMO_DISCLAIMER = DEMO_SECONDARY_DISCLAIMER

DEMO_OFFLINE_MODE = os.getenv("DEMO_OFFLINE_MODE", "0").strip().lower() in {"1", "true", "yes"}

# PoC pilot geography (Surrey / Lower Mainland)
DEMO_PILOT_MUNICIPALITY = "Surrey"
DEMO_PILOT_REGION = "Lower Mainland"
# Alias used in UI copy and outage summaries (region_name column)
DEMO_PILOT_BC_HYDRO_REGION = DEMO_PILOT_REGION
DEMO_PILOT_LAT = 49.19
DEMO_PILOT_LON = -122.85
DEMO_PILOT_MAP_ZOOM = 10.5
# WGS84 bbox for optional transmission overlay clip (min_lon, min_lat, max_lon, max_lat)
DEMO_PILOT_TRANSMISSION_BBOX = (-123.05, 49.02, -122.65, 49.35)

DEMO_PILOT_DISCLAIMER = f"Defaults: {DEMO_PILOT_MUNICIPALITY} ({DEMO_PILOT_REGION})"

# Demo region selector (Surrey-only for PoC)
DEMO_REGION_OPTIONS = (f"{DEMO_PILOT_MUNICIPALITY}, BC",)

# Sidebar data mode — controls Planet sample vs public/proxy vs synthetic emphasis
DEMO_DATA_MODES = (
    "Public/proxy only",
    "Planet sample enabled",
    "Synthetic fallback",
)

PLANET_SURREY_SAMPLE_CSV = DEMO_DATA_DIR / "planet_surrey_sample_placeholder.csv"

# Optional processed open/free data outputs (see docs/free_data_integration_plan.md)
SURREY_WORLDCOVER_STATS_CSV = PROCESSED_DATA_DIR / "surrey_worldcover_corridor_stats.csv"
SURREY_FREE_DATA_SUMMARY_CSV = PROCESSED_DATA_DIR / "surrey_free_data_corridor_summary.csv"
SURREY_FREE_DATA_PLACEHOLDER_CSV = DEMO_DATA_DIR / "surrey_free_data_corridor_summary_placeholder.csv"
SURREY_SENTINEL2_STATS_CSV = PROCESSED_DATA_DIR / "surrey_sentinel2_corridor_stats.csv"
SURREY_SENTINEL2_SCENE_QA_CSV = PROCESSED_DATA_DIR / "surrey_sentinel2_scene_qa.csv"

PLANET_POC_DISCLAIMER = (
    "Planet layers are proposed remote-sensing inputs for the Surrey proof-of-process. "
    "They do not replace BC Hydro internal outage, feeder/circuit, vegetation treatment, "
    "asset, or work-management data."
)
