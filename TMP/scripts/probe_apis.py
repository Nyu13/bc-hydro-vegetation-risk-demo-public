"""Probe live APIs (TMP helper)."""
from datetime import datetime, timedelta, timezone

import requests

from src.config import DEMO_PILOT_LAT, DEMO_PILOT_LON

end = datetime.now(timezone.utc)
start = end - timedelta(hours=48)
dt = (
    f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
    f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
)
bbox = (
    f"{DEMO_PILOT_LON - 0.3},{DEMO_PILOT_LAT - 0.3},"
    f"{DEMO_PILOT_LON + 0.3},{DEMO_PILOT_LAT + 0.3}"
)

for coll in ("swob-realtime", "climate-hourly"):
    url = f"https://api.weather.gc.ca/collections/{coll}/items"
    r = requests.get(
        url, params={"f": "json", "limit": 5, "bbox": bbox, "datetime": dt}, timeout=25
    )
    print(coll, r.status_code, len(r.json().get("features", [])))
    if r.ok and r.json().get("features"):
        p = r.json()["features"][0]["properties"]
        print("  sample keys:", sorted(p.keys())[:15])
        for k in sorted(p.keys()):
            if "date" in k.lower() or "time" in k.lower():
                print(f"  {k}={p[k]}")
        if coll == "swob-realtime":
            wind = [k for k in p if "wind" in k.lower() or "pcpn" in k.lower() or "gust" in k.lower()]
            print("  wind/pcpn keys:", wind[:20])

# BC Hydro JSON (verify=False for corp SSL probe only)
try:
    r = requests.get(
        "https://www.bchydro.com/power-outages/app/outages-map-data.json",
        timeout=20,
        verify=False,
    )
    d = r.json()
    print("bchydro status", r.status_code, type(d))
    if isinstance(d, dict):
        print("keys", d.keys())
        items = d.get("outages") or d.get("data") or []
    else:
        items = d
    print("n items", len(items))
    if items:
        print("first item keys", items[0].keys() if isinstance(items[0], dict) else items[0])
        import json

        print(json.dumps(items[0], indent=2)[:2500])
except Exception as exc:
    print("bchydro err", exc)

# RSS sample
try:
    r = requests.get(
        "https://www.bchydro.com/rss/outages/all.xml",
        timeout=20,
        verify=False,
    )
    print("rss status", r.status_code, len(r.text))
    print(r.text[:800])
except Exception as exc:
    print("rss err", exc)

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
