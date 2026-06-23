"""Demo region constants — Surrey (legacy PoC) and Kelowna / Okanagan expansion."""

from __future__ import annotations

# --- Surrey / Lower Mainland (existing PoC) ---
SURREY_REGION_NAME = "Surrey"
SURREY_BC_HYDRO_REGION = "Lower Mainland"
SURREY_AOI_BBOX = (-123.05, 49.02, -122.65, 49.35)  # min_lon, min_lat, max_lon, max_lat
SURREY_AOI_WKT = (
    "POLYGON((-123.05 49.02, -122.65 49.02, -122.65 49.35, -123.05 49.35, -123.05 49.02))"
)
SURREY_PILOT_LAT = 49.19
SURREY_PILOT_LON = -122.85
SURREY_MAP_ZOOM = 10.5

# --- Kelowna / Okanagan (vegetation-heavy, wildfire-relevant demo) ---
OKANAGAN_REGION_NAME = "Kelowna / Okanagan"
OKANAGAN_AOI_BBOX = (-120.20, 49.50, -118.80, 50.50)  # min_lon, min_lat, max_lon, max_lat
OKANAGAN_AOI_WKT = (
    "POLYGON((-120.20 49.50, -118.80 49.50, -118.80 50.50, -120.20 50.50, -120.20 49.50))"
)
OKANAGAN_PILOT_LAT = 49.888
OKANAGAN_PILOT_LON = -119.496
OKANAGAN_MAP_ZOOM = 9.0

# Central Okanagan pilot labels for map focus and UI copy — not used to filter outage archive rows.
# Outage proxy scripts include every municipality/place in OKANAGAN_BC_HYDRO_REGION from the archive.
OKANAGAN_MUNICIPALITIES = (
    "Kelowna",
    "West Kelowna",
    "Lake Country",
    "Peachland",
    "Vernon",
    "Regional District of Central Okanagan",
)

# Primary filter for Okanagan outage proxy aggregation (matches BC Hydro public archive region_name).
OKANAGAN_BC_HYDRO_REGION = "Okanagan/Kootenay"

# Transmission corridor processing
OKANAGAN_CORRIDOR_BUFFER_M = 200
OKANAGAN_SEGMENT_LENGTH_KM = 5.0

# Historical time-series window for Okanagan pipeline outputs (outage proxy, ECCC weather)
OKANAGAN_HISTORY_START_DATE = "2026-01-01"
