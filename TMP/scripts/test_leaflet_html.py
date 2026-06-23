"""Quick check of Leaflet HTML tile URL escaping."""
import re

import pandas as pd

from src.okanagan_leaflet_map import build_okanagan_leaflet_map_html

html = build_okanagan_leaflet_map_html(
    selected_date_iso="2026-01-15",
    show_fwi_raster=False,
    show_tx_lines=True,
    show_buffer=False,
    show_segments=True,
    segment_color_mode="planning_priority_score",
    planning_df=pd.DataFrame(),
    fwi_df=pd.DataFrame(),
    fires_df=pd.DataFrame(),
    archive_outages_df=pd.DataFrame(),
    live_outages_df=pd.DataFrame(),
    live_outages_synthetic=False,
)
m = re.search(r"L\.tileLayer\('([^']+)'", html)
print("Tile URL:", m.group(1) if m else "NOT FOUND")
print("Correct Leaflet placeholders:", "{s}" in (m.group(1) if m else ""))
print("Broken double braces:", "{{s}}" in html)
