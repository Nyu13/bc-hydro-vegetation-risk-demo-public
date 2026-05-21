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
            "Bundled WGS84 sample in data/demo/demo_bc_transmission_lines_sample.geojson. "
            "Reference underlay only; demo_corridors.csv remains synthetic risk points."
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
        "name": "ESA WorldCover / Canada Land Cover",
        "url": "https://esa-worldcover.org/en",
        "classification": "Public proxy",
        "type": "Vegetation / land-cover proxy",
        "formal_poc_replacement": "BC Hydro vegetation patrol, treatment, ROW, and LiDAR-informed exposure datasets",
        "notes": "Proxy for tree/forest exposure near demo corridors.",
    },
]

