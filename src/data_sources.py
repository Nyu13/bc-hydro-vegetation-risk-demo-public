DATA_SOURCES = [
    {
        "name": "BC Hydro Outage Map JSON",
        "url": "https://www.bchydro.com/power-outages/app/outages-map-data.json",
        "classification": "Public",
        "type": "Public outage status (current/recent)",
        "formal_poc_replacement": "BC Hydro internal outage history and event-level operational outage data",
        "notes": "Current/recent visibility, not a validated historical archive.",
    },
    {
        "name": "BC Hydro Outage RSS",
        "url": "https://www.bchydro.com/rss/outages/all.xml",
        "classification": "Public",
        "type": "Public outage feed (current/recent)",
        "formal_poc_replacement": "BC Hydro internal outage history and event-level operational outage data",
        "notes": "Useful for public status feed; not full historical record.",
    },
    {
        "name": "Unofficial Public Outage Snapshot Archive",
        "url": "https://github.com/outages/bchydro-outages",
        "classification": "Proxy / Unofficial",
        "type": "Public unofficial snapshots",
        "formal_poc_replacement": "BC Hydro validated internal historical outage archive",
        "notes": "Unofficial archive; not provided or validated by BC Hydro.",
    },
    {
        "name": "BC Geographic Warehouse — BC Transmission Lines",
        "url": "https://www.app.geo.ca/en-ca/map-browser/record/384d551b-dee1-4df8-8148-b3fcf865096a",
        "classification": "Public reference",
        "type": "Optional HV line overlay — British Columbia (WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP)",
        "formal_poc_replacement": "BC Hydro feeder/circuit topology and protected corridor models",
        "notes": (
            "WFS pub:WHSE_BASEMAPPING.GBA_TRANSMISSION_LINES_SP (openmaps.gov.bc.ca). "
            "Loader prefers data/processed/bc_transmission_lines_lower_mainland.geojson, "
            "else data/demo/demo_bc_transmission_lines_sample.geojson. "
            "Refresh: python TMP/scripts/fetch_bc_transmission_layer.py. "
            "Reference underlay only; demo_corridors.csv remains synthetic."
        ),
    },
    {
        "name": "ECCC weather stress proxy (Surrey corridor)",
        "url": "https://api.weather.gc.ca/",
        "classification": "Open/free processed",
        "type": "Atmospheric weather stress — wind, precipitation, air temperature, short-term dryness proxy",
        "formal_poc_replacement": "Planet LST 100 m, SWC 100 m, and BC Hydro-aligned environmental monitoring",
        "notes": (
            "Pipeline: TMP/scripts/build_surrey_environmental_stress.py → "
            "data/processed/surrey_eccc_weather_stress_stats.csv. "
            "Uses MSC GeoMet via src/weather_loader.py (live or demo_weather.csv fallback). "
            "Not true soil moisture, not land surface temperature, not canopy stress."
        ),
    },
    {
        "name": "Environment and Climate Change Canada",
        "url": "https://api.weather.gc.ca/",
        "classification": "Public",
        "type": "Public weather source",
        "formal_poc_replacement": "BC Hydro aligned weather observations/forecasts archive and storm operations context",
        "notes": "Used as weather severity proxy for storm windows.",
    },
    {
        "name": "Sentinel-2 L2A (Surrey corridor — local .SAFE / .zip)",
        "url": "https://browser.dataspace.copernicus.eu/",
        "classification": "Open/free processed",
        "type": "NDVI / NDMI from local L2A .SAFE folders or .zip products",
        "formal_poc_replacement": "Planet ARPS / Area Monitoring greenness and moisture time series",
        "notes": (
            "Process offline: TMP/scripts/build_surrey_sentinel2_indices.py --safe-dir "
            '"data/raw/surrey/Sentinel-2 L2A" (recursive scan of .SAFE and MSIL2A .zip). '
            "Legacy band GeoTIFF mode: --red/--nir/--swir. "
            "Raw products in data/raw/surrey/ (gitignored). "
            "See docs/sentinel2_manual_download_notes.md. No Streamlit runtime download."
        ),
    },
    {
        "name": "ESA WorldCover / Canada Land Cover (Surrey corridor)",
        "url": "https://esa-worldcover.org/en/data-access",
        "classification": "Open/free processed",
        "type": "Vegetation / land-cover proxy — zonal stats in 200 m buffer",
        "formal_poc_replacement": "BC Hydro vegetation patrol, treatment, ROW, and LiDAR-informed exposure datasets",
        "notes": (
            "Pipeline: TMP/scripts/run_surrey_free_data_pipeline.py → "
            "data/processed/surrey_free_data_corridor_summary.csv (🟦). "
            "Used in Public/proxy mode when Planet sample is off."
        ),
    },
    {
        "name": "ESA WorldCover / Canada Land Cover",
        "url": "https://esa-worldcover.org/en",
        "classification": "Public proxy",
        "type": "Vegetation / land-cover proxy",
        "formal_poc_replacement": "BC Hydro vegetation patrol, treatment, ROW, and LiDAR-informed exposure datasets",
        "notes": "Proxy for tree/forest exposure near demo corridors.",
    },
    {
        "name": "Planet (commercial — Surrey PoC request)",
        "url": "https://www.planet.com/",
        "classification": "Commercial (not purchased)",
        "type": "FCM canopy, SWC 100 m, LST 100 m, ARPS/PlanetScope vegetation analytics",
        "formal_poc_replacement": (
            "BC Hydro LiDAR-informed canopy, patrol/treatment records, and operational vegetation exposure"
        ),
        "notes": (
            "Not loaded until purchased; demo uses data/demo/planet_surrey_sample_placeholder.csv when "
            "sidebar mode is Planet sample enabled. Preferred AOI: Surrey transmission 200 m buffer "
            "(~3,580 ha). Full product list, AOI comparison, and quote questions: Data Sources & "
            "Assumptions tab → Planet section. See docs/planet_surrey_data_request.md."
        ),
    },
]

