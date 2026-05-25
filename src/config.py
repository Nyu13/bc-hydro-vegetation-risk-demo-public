from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DEMO_DATA_DIR = DATA_DIR / "demo"
DOCS_DIR = PROJECT_ROOT / "docs"

# BC Geographic Warehouse transmission lines (optional local KML/WFS; bundled sample for Cloud)
BC_TRANSMISSION_KML = DATA_DIR / "WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP_loader.kml"
BC_TRANSMISSION_GEOJSON = DEMO_DATA_DIR / "demo_bc_transmission_lines_sample.geojson"

BC_HYDRO_OUTAGE_JSON_URL = "https://www.bchydro.com/power-outages/app/outages-map-data.json"
BC_HYDRO_OUTAGE_RSS_URL = "https://www.bchydro.com/rss/outages/all.xml"
UNOFFICIAL_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/outages/bchydro-outages/main/bchydro-outages.json"
)

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

DEMO_PILOT_DISCLAIMER = f"PoC pilot area: {DEMO_PILOT_MUNICIPALITY} ({DEMO_PILOT_REGION})"
