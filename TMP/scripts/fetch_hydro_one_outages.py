#!/usr/bin/env python3
"""
Fetch live Hydro One (Ontario) outages from the public Kubra Storm Centre API.

Unofficial public map feed — not an operational archive. Suitable as a live
Ontario outage snapshot for demo / outreach AOIs (e.g. Muskoka / Ottawa Valley).

Discovers INSTANCE_ID / VIEW_ID from https://stormcentre.hydroone.com/ when
possible; falls back to known Hydro One GUIDs.

Outputs under TMP/temp/hydro_one_outages/:
  - latest/   (always overwritten)
  - snapshots/YYYYMMDD_HHMMSSZ/  (when --archive is set)
  - archive_index.csv            (one row per archived run)

Usage:
  python TMP/scripts/fetch_hydro_one_outages.py
  python TMP/scripts/fetch_hydro_one_outages.py --archive
  python TMP/scripts/fetch_hydro_one_outages.py --bbox -80.0 44.5 -78.5 45.5
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import mercantile
import polyline
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
OUT_DIR = PROJECT_ROOT / "TMP" / "temp" / "hydro_one_outages"

STORMCENTRE_HOME = "https://stormcentre.hydroone.com/"
KUBRA_BASE = "https://kubra.io"

# Discovered 2026-10-07 from stormcentre.hydroone.com HTML bootstrap
DEFAULT_INSTANCE_ID = "b8d8094c-3809-49e5-bf8b-1ddd27f6e12d"
DEFAULT_VIEW_ID = "5c2283d7-eff9-4f7e-966b-3afd90d8a6b9"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; VegetationRiskDemo/1.0; "
        "+https://github.com/bc-hydro-vegetation-risk-demo)"
    ),
    "Accept": "application/json, text/html, */*",
}

INSTANCE_RE = re.compile(
    r"instanceId[\"']?\s*[:=]\s*[\"']([0-9a-f-]{36})",
    re.I,
)
VIEW_RE = re.compile(
    r"viewId[\"']?\s*[:=]\s*[\"']([0-9a-f-]{36})",
    re.I,
)

MIN_ZOOM = 7
MAX_ZOOM = 14
REQUEST_TIMEOUT = 30


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instance-id", default=None, help="Kubra stormcenter instance GUID")
    p.add_argument("--view-id", default=None, help="Kubra view GUID")
    p.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Optional WGS84 bbox filter after fetch (e.g. Muskoka)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Output directory (default: {OUT_DIR})",
    )
    p.add_argument(
        "--archive",
        action="store_true",
        help="Also write a timestamped snapshot under out-dir/snapshots/ and append archive_index.csv",
    )
    p.add_argument(
        "--append-history",
        action="store_true",
        help="Append normalized rows to out-dir/outages_history.csv (with fetched_at_utc)",
    )
    p.add_argument("--min-zoom", type=int, default=MIN_ZOOM)
    p.add_argument("--max-zoom", type=int, default=MAX_ZOOM)
    return p.parse_args()


def http_get(url: str) -> requests.Response:
    return requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        verify=False,
        allow_redirects=True,
    )


def discover_ids() -> tuple[str, str]:
    try:
        r = http_get(STORMCENTRE_HOME)
        r.raise_for_status()
        inst = INSTANCE_RE.search(r.text)
        view = VIEW_RE.search(r.text)
        if inst and view:
            return inst.group(1), view.group(1)
    except Exception as exc:
        print(f"WARN: discover from stormcentre failed ({exc}); using defaults")
    return DEFAULT_INSTANCE_ID, DEFAULT_VIEW_ID


def fetch_state(instance_id: str, view_id: str) -> dict[str, Any]:
    url = (
        f"{KUBRA_BASE}/stormcenter/api/v1/stormcenters/{instance_id}"
        f"/views/{view_id}/currentState?preview=false"
    )
    r = http_get(url)
    r.raise_for_status()
    return r.json()


def fetch_cluster_layer_id(instance_id: str, view_id: str, state: dict[str, Any]) -> str:
    deployment_id = state["stormcenterDeploymentId"]
    url = (
        f"{KUBRA_BASE}/stormcenter/api/v1/stormcenters/{instance_id}"
        f"/views/{view_id}/configuration/{deployment_id}?preview=false"
    )
    r = http_get(url)
    r.raise_for_status()
    config = r.json()
    interval_data = config["config"]["layers"]["data"]["interval_generation_data"]
    for layer in interval_data:
        if str(layer.get("type", "")).startswith("CLUSTER_LAYER"):
            return str(layer["id"])
    raise RuntimeError("No CLUSTER_LAYER found in Kubra configuration")


def fetch_summary(state: dict[str, Any]) -> dict[str, Any]:
    data_path = state["data"]["interval_generation_data"]
    url = f"{KUBRA_BASE}/{data_path}/public/summary-1/data.json"
    r = http_get(url)
    r.raise_for_status()
    return r.json()


def service_area_bbox(state: dict[str, Any]) -> list[float]:
    ((regions_key, regions),) = state["datastatic"].items()
    url = f"{KUBRA_BASE}/{regions}/{regions_key}/serviceareas.json"
    r = http_get(url)
    r.raise_for_status()
    areas = r.json()["file_data"][0]["geom"]["a"]
    points: list[tuple[float, float]] = []
    for geom in areas:
        points.extend(polyline.decode(geom))
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    # mercantile.tiles expects west, south, east, north
    return [min(lons), min(lats), max(lons), max(lats)]


def cluster_url(state: dict[str, Any], layer_id: str, quadkey: str) -> str:
    template = state["data"]["cluster_interval_generation_data"]
    # template: cluster-data/{qkh}/.../...  where {qkh} is last 3 of quadkey reversed
    path = template.replace("{qkh}", quadkey[-3:][::-1])
    return f"{KUBRA_BASE}/{path}/public/{layer_id}/{quadkey}.json"


def descend_outages(
    state: dict[str, Any],
    layer_id: str,
    quadkeys: list[str],
    max_zoom: int,
) -> Iterator[dict[str, Any]]:
    for quadkey in quadkeys:
        url = cluster_url(state, layer_id, quadkey)
        r = http_get(url)
        if r.status_code == 404:
            continue
        if not r.ok:
            print(f"WARN: {r.status_code} {url}")
            continue
        payload = r.json()
        file_data = payload.get("file_data") or []
        any_clusters = any(item.get("desc", {}).get("cluster") for item in file_data)
        if not any_clusters or len(quadkey) >= max_zoom:
            for item in file_data:
                if item.get("desc", {}).get("cluster"):
                    continue
                item = dict(item)
                item["_source_url"] = url
                item["_quadkey"] = quadkey
                yield item
        else:
            yield from descend_outages(
                state,
                layer_id,
                [quadkey + str(i) for i in (0, 1, 2, 3)],
                max_zoom,
            )


def outage_point(geom: dict[str, Any]) -> tuple[float | None, float | None]:
    if not geom:
        return None, None
    if geom.get("p"):
        lat, lon = polyline.decode(geom["p"][0])[0]
        return float(lon), float(lat)
    if geom.get("a"):
        ring = polyline.decode(geom["a"][0])
        if not ring:
            return None, None
        lats = [p[0] for p in ring]
        lons = [p[1] for p in ring]
        return sum(lons) / len(lons), sum(lats) / len(lats)
    return None, None


def outage_geometry(geom: dict[str, Any]) -> dict[str, Any] | None:
    if not geom:
        return None
    if geom.get("a"):
        rings = []
        for encoded in geom["a"]:
            rings.append([[lon, lat] for lat, lon in polyline.decode(encoded)])
        return {"type": "Polygon", "coordinates": rings}
    if geom.get("p"):
        lat, lon = polyline.decode(geom["p"][0])[0]
        return {"type": "Point", "coordinates": [lon, lat]}
    return None


def _scalar(value: Any) -> Any:
    """Flatten Kubra multilingual / masked value objects for CSV."""
    if isinstance(value, dict):
        if "val" in value:
            return value.get("val")
        for key in ("EN-US", "en-US", "en", "fr-CA", "fr"):
            if key in value:
                return value[key]
        return json.dumps(value, ensure_ascii=False)
    return value


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    desc = raw.get("desc") or {}
    geom = raw.get("geom") or {}
    lon, lat = outage_point(geom)
    customers = desc.get("cust_a") if "cust_a" in desc else desc.get("n_cust")
    return {
        "outage_id": raw.get("id") or desc.get("outage_id") or "",
        "title": raw.get("title") or "",
        "customers_affected": _scalar(customers),
        "n_outages_in_cluster_record": _scalar(desc.get("n_out")),
        "cause": _scalar(desc.get("cause") or desc.get("comments") or ""),
        "status": _scalar(desc.get("status") or ""),
        "etr": _scalar(desc.get("etr") or desc.get("etr_iso") or ""),
        "start_time": _scalar(desc.get("start_time") or desc.get("startTime") or ""),
        "region": _scalar(desc.get("region") or desc.get("area") or ""),
        "municipality": _scalar(desc.get("municipality") or desc.get("city") or ""),
        "latitude": lat,
        "longitude": lon,
        "cluster": bool(desc.get("cluster")),
        "source_url": raw.get("_source_url") or "",
        "quadkey": raw.get("_quadkey") or "",
        "utility": "Hydro One",
        "province": "Ontario",
        "feed": "kubra_stormcentre_live",
        "data_source_notes": (
            "Unofficial public Hydro One Storm Centre (Kubra) live snapshot; "
            "not operational outage history."
        ),
    }


def in_bbox(lon: float | None, lat: float | None, bbox: list[float]) -> bool:
    if lon is None or lat is None:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def write_outputs(
    out_dir: Path,
    meta: dict[str, Any],
    raw_outages: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "snapshot_meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    (out_dir / "raw_outages.json").write_text(
        json.dumps(raw_outages, indent=2),
        encoding="utf-8",
    )

    fieldnames = list(rows[0].keys()) if rows else [
        "outage_id",
        "title",
        "customers_affected",
        "latitude",
        "longitude",
        "utility",
        "province",
        "feed",
    ]
    with (out_dir / "outages.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    features = []
    for raw, row in zip(raw_outages, rows):
        geometry = outage_geometry(raw.get("geom") or {})
        if geometry is None and row.get("longitude") is not None:
            geometry = {
                "type": "Point",
                "coordinates": [row["longitude"], row["latitude"]],
            }
        if geometry is None:
            continue
        props = {k: v for k, v in row.items() if k not in ("latitude", "longitude")}
        features.append({"type": "Feature", "properties": props, "geometry": geometry})

    fc = {"type": "FeatureCollection", "features": features}
    (out_dir / "outages.geojson").write_text(
        json.dumps(fc),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    instance_id = args.instance_id
    view_id = args.view_id
    if not instance_id or not view_id:
        discovered_i, discovered_v = discover_ids()
        instance_id = instance_id or discovered_i
        view_id = view_id or discovered_v

    print(f"Hydro One Kubra instance={instance_id} view={view_id}")
    state = fetch_state(instance_id, view_id)
    summary = fetch_summary(state)
    totals = (summary.get("summaryFileData") or {}).get("totals") or [{}]
    expected = int(totals[0].get("total_outages") or 0)
    customers = totals[0].get("total_cust_a", {}).get("val")
    print(
        f"Summary: {expected} outages, "
        f"customers_affected={customers}, "
        f"generated={summary.get('summaryFileData', {}).get('date_generated')}"
    )

    layer_id = fetch_cluster_layer_id(instance_id, view_id, state)
    bbox = service_area_bbox(state)
    print(f"Service-area bbox (west,south,east,north)={bbox}")
    print(f"Cluster layer id={layer_id}")

    root_quadkeys = [
        mercantile.quadkey(t) for t in mercantile.tiles(*bbox, zooms=[args.min_zoom])
    ]
    print(f"Root tiles at z{args.min_zoom}: {len(root_quadkeys)}")

    raw_outages = list(
        descend_outages(state, layer_id, root_quadkeys, max_zoom=args.max_zoom)
    )
    print(f"Fetched {len(raw_outages)} leaf outage records (expected ~{expected})")

    rows = [normalize_row(raw) for raw in raw_outages]
    if args.bbox:
        filtered_raw = []
        filtered_rows = []
        for raw, row in zip(raw_outages, rows):
            if in_bbox(row.get("longitude"), row.get("latitude"), list(args.bbox)):
                filtered_raw.append(raw)
                filtered_rows.append(row)
        print(f"Bbox filter kept {len(filtered_rows)} / {len(rows)}")
        raw_outages, rows = filtered_raw, filtered_rows

    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    stamp = now.strftime("%Y%m%d_%H%M%SZ")
    meta = {
        "utility": "Hydro One",
        "province": "Ontario",
        "fetched_at_utc": fetched_at,
        "snapshot_id": stamp,
        "instance_id": instance_id,
        "view_id": view_id,
        "stormcentre_url": STORMCENTRE_HOME,
        "expected_outages": expected,
        "customers_affected_total": customers,
        "fetched_outages": len(rows),
        "summary_date_generated": (summary.get("summaryFileData") or {}).get(
            "date_generated"
        ),
        "bbox_filter": list(args.bbox) if args.bbox else None,
        "disclaimer": (
            "Unofficial public Kubra Storm Centre snapshot for demo use only. "
            "Not Hydro One operational data."
        ),
    }

    latest_dir = args.out_dir / "latest"
    write_outputs(latest_dir, meta, raw_outages, rows)
    # Keep flat copies at out-dir root for backward compatibility
    write_outputs(args.out_dir, meta, raw_outages, rows)
    print(f"Wrote latest -> {latest_dir}")
    print(f"  outages.csv ({len(rows)} rows)")

    if args.archive:
        snap_dir = args.out_dir / "snapshots" / stamp
        write_outputs(snap_dir, meta, raw_outages, rows)
        index_path = args.out_dir / "archive_index.csv"
        index_row = {
            "snapshot_id": stamp,
            "fetched_at_utc": fetched_at,
            "expected_outages": expected,
            "fetched_outages": len(rows),
            "customers_affected_total": customers,
            "snapshot_dir": str(snap_dir.relative_to(args.out_dir)).replace("\\", "/"),
        }
        write_header = not index_path.is_file()
        with index_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(index_row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(index_row)
        print(f"Archived snapshot -> {snap_dir}")
        print(f"Appended {index_path.name}")

    if args.append_history:
        history_path = args.out_dir / "outages_history.csv"
        history_rows = [{**row, "fetched_at_utc": fetched_at, "snapshot_id": stamp} for row in rows]
        write_header = not history_path.is_file()
        fieldnames = list(history_rows[0].keys()) if history_rows else [
            "outage_id",
            "fetched_at_utc",
            "snapshot_id",
            "customers_affected",
            "latitude",
            "longitude",
        ]
        with history_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(history_rows)
        # Always refresh a tiny run index even without --archive folders
        index_path = args.out_dir / "archive_index.csv"
        index_row = {
            "snapshot_id": stamp,
            "fetched_at_utc": fetched_at,
            "expected_outages": expected,
            "fetched_outages": len(rows),
            "customers_affected_total": customers,
            "snapshot_dir": "latest",
        }
        write_header = not index_path.is_file()
        with index_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(index_row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(index_row)
        print(f"Appended {len(history_rows)} rows -> {history_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
