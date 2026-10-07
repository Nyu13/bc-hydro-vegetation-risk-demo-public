#!/usr/bin/env python3
"""
Backfill Ontario transmission outage history from IESO public reports.

Source: https://reports-public.ieso.ca/public/TxOutagesTodayAll/
Each retained daily XML lists outages active that calendar day (often including
long-running requests with PlannedStart years earlier). Retention on the
public index is typically ~30 days — this script downloads every available
day and builds a deduped historical-ish table.

This is IESO transmission outage requests (equipment/station names), NOT
Hydro One distribution Storm Centre polygons. Still the best free Ontario
outage history stack for demo / corridor framing.

Outputs under TMP/temp/ieso_tx_outages/:
  - raw/<date>.xml
  - outage_requests.csv          (deduped by OutageID, latest snapshot wins)
  - daily_active_counts.csv
  - fetch_meta.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
OUT_DIR = PROJECT_ROOT / "TMP" / "temp" / "ieso_tx_outages"
INDEX_URL = "https://reports-public.ieso.ca/public/TxOutagesTodayAll/"
NS = {"ieso": "http://www.ieso.ca/schema"}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; VegetationRiskDemo/1.0; "
        "+https://github.com/bc-hydro-vegetation-risk-demo)"
    ),
    "Accept": "text/html,application/xml,*/*",
}
DATE_FILE_RE = re.compile(
    r"PUB_TxOutagesTodayAll_(\d{8})(?:_v(\d+))?\.xml",
    re.I,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument(
        "--max-days",
        type=int,
        default=0,
        help="Optional cap on number of days to download (0 = all listed)",
    )
    return p.parse_args()


def http_get(url: str) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=60, verify=False)


def list_best_files_per_day() -> dict[str, str]:
    """Return {YYYYMMDD: filename} preferring unversioned, else highest _vN."""
    r = http_get(INDEX_URL)
    r.raise_for_status()
    best: dict[str, tuple[int, str]] = {}
    for date_s, ver_s in DATE_FILE_RE.findall(r.text):
        ver = int(ver_s) if ver_s else 10_000  # unversioned beats numbered
        name = (
            f"PUB_TxOutagesTodayAll_{date_s}.xml"
            if not ver_s
            else f"PUB_TxOutagesTodayAll_{date_s}_v{ver_s}.xml"
        )
        prev = best.get(date_s)
        if prev is None or ver > prev[0]:
            best[date_s] = (ver, name)
    return {d: name for d, (_ver, name) in sorted(best.items())}


def text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_outage_requests(xml_bytes: bytes, snapshot_date: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, Any]] = []
    for req in root.findall(".//ieso:OutageRequest", NS):
        equip_names: list[str] = []
        equip_types: list[str] = []
        voltages: list[str] = []
        for eq in req.findall("ieso:EquipmentRequested", NS):
            equip_names.append(text(eq.find("ieso:EquipmentName", NS)))
            equip_types.append(text(eq.find("ieso:EquipmentType", NS)))
            voltages.append(text(eq.find("ieso:EquipmentVoltage", NS)))
        rows.append(
            {
                "outage_id": text(req.find("ieso:OutageID", NS)),
                "planned_start": text(req.find("ieso:PlannedStart", NS)),
                "planned_end": text(req.find("ieso:PlannedEnd", NS)),
                "priority": text(req.find("ieso:Priority", NS)),
                "recurrence": text(req.find("ieso:Recurrence", NS)),
                "status": text(req.find("ieso:OutageRequestStatus", NS)),
                "recall_time": text(req.find("ieso:EquipmentRecallTime", NS)),
                "equipment_count": len(equip_names),
                "equipment_names": " | ".join(n for n in equip_names if n),
                "equipment_types": " | ".join(sorted(set(t for t in equip_types if t))),
                "equipment_voltages": " | ".join(sorted(set(v for v in voltages if v))),
                "snapshot_date": snapshot_date,
                "source": "ieso_tx_outages_today_all",
                "province": "Ontario",
                "data_source_notes": (
                    "IESO public transmission outage request report "
                    "(TxOutagesTodayAll). Not Hydro One distribution outages."
                ),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out_dir
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    files = list_best_files_per_day()
    dates = list(files.keys())
    if args.max_days and args.max_days > 0:
        dates = dates[-args.max_days :]
    print(f"IESO TxOutagesTodayAll: {len(dates)} days "
          f"({dates[0] if dates else 'n/a'} .. {dates[-1] if dates else 'n/a'})")

    all_rows: list[dict[str, Any]] = []
    daily_counts: list[dict[str, Any]] = []
    for date_s in dates:
        name = files[date_s]
        url = INDEX_URL + name
        iso = f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:8]}"
        dest = raw_dir / name
        if dest.is_file() and dest.stat().st_size > 0:
            xml_bytes = dest.read_bytes()
            print(f"  cache hit {name}")
        else:
            r = http_get(url)
            if r.status_code != 200:
                print(f"  SKIP {name} status={r.status_code}")
                continue
            dest.write_bytes(r.content)
            xml_bytes = r.content
            print(f"  downloaded {name} ({len(xml_bytes)} bytes)")

        rows = parse_outage_requests(xml_bytes, iso)
        all_rows.extend(rows)
        starts = [r["planned_start"][:10] for r in rows if r["planned_start"]]
        daily_counts.append(
            {
                "snapshot_date": iso,
                "active_outage_requests": len(rows),
                "earliest_planned_start": min(starts) if starts else "",
                "latest_planned_start": max(starts) if starts else "",
                "source_file": name,
            }
        )

    # Deduplicate by outage_id keeping the latest snapshot_date row
    by_id: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        oid = row["outage_id"] or f"anon:{row['snapshot_date']}:{row['equipment_names'][:40]}"
        prev = by_id.get(oid)
        if prev is None or row["snapshot_date"] >= prev["snapshot_date"]:
            by_id[oid] = row
    deduped = sorted(by_id.values(), key=lambda r: (r["planned_start"], r["outage_id"]))

    write_csv(out_dir / "outage_requests.csv", deduped)
    write_csv(out_dir / "daily_active_counts.csv", daily_counts)

    start_dates = [r["planned_start"][:10] for r in deduped if r["planned_start"]]
    meta = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "index_url": INDEX_URL,
        "days_downloaded": len(daily_counts),
        "snapshot_date_min": daily_counts[0]["snapshot_date"] if daily_counts else None,
        "snapshot_date_max": daily_counts[-1]["snapshot_date"] if daily_counts else None,
        "raw_rows": len(all_rows),
        "deduped_outage_requests": len(deduped),
        "planned_start_min": min(start_dates) if start_dates else None,
        "planned_start_max": max(start_dates) if start_dates else None,
        "disclaimer": (
            "IESO public transmission outage requests. Not Hydro One distribution. "
            "Public directory retains roughly one month of daily XML snapshots; "
            "PlannedStart on those records can extend years earlier."
        ),
    }
    (out_dir / "fetch_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(
        f"Wrote {out_dir}: {len(deduped)} deduped outage requests "
        f"(planned_start {meta['planned_start_min']} .. {meta['planned_start_max']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
