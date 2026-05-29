"""Compare BC Hydro live JSON vs GitHub archive (TMP)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.config import BC_HYDRO_OUTAGE_JSON_URL, GITHUB_BCHYDRO_OUTAGES_URL
from src.outage_loader import load_bchydro_outage_json, load_github_bchydro_outages

urllib3.disable_warnings()


def fetch(url: str) -> object:
    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    return r.json()


def norm(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("outages", "data", "features"):
            if key in payload and isinstance(payload[key], list):
                return [x for x in payload[key] if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def main() -> None:
    live = fetch(BC_HYDRO_OUTAGE_JSON_URL)
    gh = fetch(GITHUB_BCHYDRO_OUTAGES_URL)

    live_items = norm(live)
    gh_items = norm(gh)

    print("=== LIVE ===")
    print("top type:", type(live).__name__, "count:", len(live_items))
    if live_items:
        print("keys:", sorted(live_items[0].keys()))

    print("=== GITHUB ===")
    print("top type:", type(gh).__name__, "count:", len(gh_items))
    if gh_items:
        print("keys:", sorted(gh_items[0].keys()))

    live_ids = {str(x.get("id", "")) for x in live_items}
    gh_ids = {str(x.get("id", "")) for x in gh_items}
    print("=== IDS ===")
    print("only live:", len(live_ids - gh_ids))
    print("only github:", len(gh_ids - live_ids))
    print("overlap:", len(live_ids & gh_ids))

    def canonical(items: list[dict]) -> str:
        return json.dumps(sorted(items, key=lambda x: str(x.get("id", ""))), sort_keys=True, default=str)

    hl = hashlib.sha256(canonical(live_items).encode()).hexdigest()[:16]
    hg = hashlib.sha256(canonical(gh_items).encode()).hexdigest()[:16]
    print("canonical sha256 prefix live:", hl, "github:", hg, "match:", hl == hg)

    for label, items in [("LIVE", live_items), ("GITHUB", gh_items)]:
        for row in items:
            muni = str(row.get("municipality", "")).lower()
            area = str(row.get("area", "")).lower()
            region = str(row.get("regionName", row.get("region", ""))).lower()
            if "surrey" in muni or "surrey" in area:
                print(f"--- {label} Surrey sample id={row.get('id')} ---")
                for k in (
                    "id",
                    "municipality",
                    "area",
                    "latitude",
                    "longitude",
                    "numCustomersOut",
                    "cause",
                    "polygon",
                ):
                    v = row.get(k)
                    if k == "polygon" and isinstance(v, list):
                        print(f"  polygon len={len(v)} first8={v[:8]}")
                    else:
                        print(f"  {k}={v!r}")
                break

    ldf = load_bchydro_outage_json(allow_synthetic_fallback=False)
    gdf = load_github_bchydro_outages(allow_synthetic_fallback=False)
    print("=== LOADER ===")
    print("live rows:", len(ldf), "polygons:", int(ldf["outage_has_polygon"].sum()) if len(ldf) else 0)
    print("github rows:", len(gdf), "polygons:", int(gdf["outage_has_polygon"].sum()) if len(gdf) else 0)


if __name__ == "__main__":
    main()
