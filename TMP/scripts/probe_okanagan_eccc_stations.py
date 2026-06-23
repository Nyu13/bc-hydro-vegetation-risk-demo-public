#!/usr/bin/env python3
"""Probe MSC GeoMet stations near Okanagan AOI (one-off investigation)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.regions import OKANAGAN_AOI_BBOX, OKANAGAN_PILOT_LAT, OKANAGAN_PILOT_LON  # noqa: E402

W, S, E, N = OKANAGAN_AOI_BBOX
pad = 0.35
bbox = f"{OKANAGAN_PILOT_LON - pad},{OKANAGAN_PILOT_LAT - pad},{OKANAGAN_PILOT_LON + pad},{OKANAGAN_PILOT_LAT + pad}"

end = datetime.now(timezone.utc)
start = end - timedelta(hours=48)
dt = f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def in_aoi(lat, lon) -> bool:
    if lat is None or lon is None:
        return False
    return W <= float(lon) <= E and S <= float(lat) <= N


def probe_climate_hourly():
    url = "https://api.weather.gc.ca/collections/climate-hourly/items"
    r = requests.get(
        url,
        params={"f": "json", "limit": 5000, "bbox": bbox, "datetime": dt, "sortby": "-UTC_DATE"},
        timeout=30,
    )
    r.raise_for_status()
    stations: dict[str, dict] = {}
    for feature in r.json().get("features", []):
        p = feature.get("properties", {})
        name = str(p.get("STATION_NAME", "?"))
        lat = p.get("LATITUDE_DECIMAL_DEGREES") or p.get("LATITUDE")
        lon = p.get("LONGITUDE_DECIMAL_DEGREES") or p.get("LONGITUDE")
        sid = p.get("CLIMATE_IDENTIFIER") or p.get("STATION_ID") or p.get("STN_ID")
        if name not in stations:
            stations[name] = {
                "lat": lat,
                "lon": lon,
                "id": sid,
                "in_aoi": in_aoi(lat, lon),
                "count": 0,
            }
        stations[name]["count"] += 1
    print("=== climate-hourly (48h, pilot bbox pad=0.35) ===")
    for name, info in sorted(stations.items(), key=lambda x: -x[1]["count"]):
        print(
            f"  {name} | id={info['id']} | {info['lat']},{info['lon']} | "
            f"in_aoi={info['in_aoi']} | obs={info['count']}"
        )
    return stations


def probe_swob():
    url = "https://api.weather.gc.ca/collections/swob-realtime/items"
    r = requests.get(
        url,
        params={"f": "json", "limit": 250, "bbox": bbox, "datetime": dt, "sortby": "-obs_date_tm"},
        timeout=30,
    )
    r.raise_for_status()
    stations: dict[str, dict] = {}
    for feature in r.json().get("features", []):
        p = feature.get("properties", {})
        name = str(p.get("stn_nam-value") or p.get("stn_nam") or "?")
        lat = p.get("lat-value") or p.get("lat")
        lon = p.get("lon-value") or p.get("lon")
        sid = p.get("stn_id-value") or p.get("stn_id")
        if name not in stations:
            stations[name] = {
                "lat": lat,
                "lon": lon,
                "id": sid,
                "in_aoi": in_aoi(lat, lon),
                "count": 0,
            }
        stations[name]["count"] += 1
    print("\n=== swob-realtime (48h) ===")
    for name, info in sorted(stations.items(), key=lambda x: -x[1]["count"]):
        print(
            f"  {name} | id={info['id']} | {info['lat']},{info['lon']} | "
            f"in_aoi={info['in_aoi']} | obs={info['count']}"
        )
    return stations


def probe_citypage():
    for coll in ("citypage_weather", "citypage-weather"):
        url = f"https://api.weather.gc.ca/collections/{coll}/items"
        try:
            r = requests.get(url, params={"f": "json", "limit": 10, "bbox": bbox}, timeout=15)
            print(f"\n=== {coll} status={r.status_code} ===")
            if r.ok:
                features = r.json().get("features", [])
                print(f"  features: {len(features)}")
                for f in features[:3]:
                    p = f.get("properties", {})
                    print(f"  keys sample: {list(p.keys())[:12]}")
                    print(f"  name/city: {p.get('name') or p.get('city_name') or p.get('CITY')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  error: {exc}")


def probe_climate_stations_collection():
    url = "https://api.weather.gc.ca/collections/climate-stations/items"
    r = requests.get(url, params={"f": "json", "limit": 500, "bbox": f"{W},{S},{E},{N}"}, timeout=30)
    print(f"\n=== climate-stations (AOI bbox) status={r.status_code} ===")
    if not r.ok:
        print(r.text[:300])
        return
    features = r.json().get("features", [])
    print(f"  stations in AOI bbox: {len(features)}")
    for f in features[:20]:
        p = f.get("properties", {})
        name = p.get("STATION_NAME") or p.get("name")
        sid = p.get("CLIMATE_IDENTIFIER") or p.get("STATION_ID")
        lat = p.get("LATITUDE") or p.get("lat")
        lon = p.get("LONGITUDE") or p.get("lon")
        print(f"  {name} | id={sid} | {lat},{lon}")


if __name__ == "__main__":
    probe_climate_hourly()
    probe_swob()
    probe_citypage()
    probe_climate_stations_collection()
