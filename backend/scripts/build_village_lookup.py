#!/usr/bin/env python3
"""Build national village lookup JSONL (id, name, state, district, lng, lat).

Dropdowns and map-click village resolve should use this file — not live per-state
S3 spatial enrich.

Usage (from backend/, with AWS creds / .env loaded):

  python scripts/build_village_lookup.py
  python scripts/build_village_lookup.py --upload
  python scripts/build_village_lookup.py --source /path/to/villages.fgb --out ./villages_lookup.jsonl

Writes:
  - local: packages_dir/villages_lookup.jsonl (or --out)
  - optional S3: s3://$AWS_S3_BUCKET/vector/villages_lookup.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def build_from_fgb(source: str, out_path: Path) -> int:
    from app.shared.watersheds import (
        _STATE_BBOXES,
        _VILLAGE_ID_KEYS,
        _VILLAGE_NAME_KEYS,
        _configure_gdal_aws,
        _geom_from_cell,
        _pick_prop,
        _read_bbox_extent,
        _row_props,
    )

    _configure_gdal_aws()
    t0 = time.time()
    by_id: dict[str, dict] = {}

    bboxes = list(_STATE_BBOXES.items()) or [("india", (68.0, 6.0, 98.0, 38.0))]

    for state_key, bbox in bboxes:
        print(f"Reading {state_key} {bbox} …", flush=True)
        try:
            table, geom_col = _read_bbox_extent(
                source, bbox[0], bbox[1], bbox[2], bbox[3], pad=0.05
            )
        except Exception as exc:
            print(f"  skip {state_key}: {exc}", flush=True)
            continue
        geoms = table.column(geom_col) if geom_col in table.column_names else None
        for i in range(table.num_rows):
            props = _row_props(table, i)
            name = _pick_prop(props, _VILLAGE_NAME_KEYS)
            if not name:
                continue
            vid = _pick_prop(props, _VILLAGE_ID_KEYS)
            if not vid:
                continue
            try:
                vid = str(int(float(vid)))
            except (TypeError, ValueError):
                vid = str(vid).strip()
            if not vid or vid in by_id:
                continue
            district = None
            state = None
            for key in ("District N", "District Name", "DISTRICT", "district"):
                if key in props and props[key] not in (None, ""):
                    district = str(props[key]).strip()
                    break
            for key in ("State Name", "STATE", "state"):
                if key in props and props[key] not in (None, ""):
                    state = str(props[key]).strip()
                    break
            lng = lat = None
            if geoms is not None:
                geom = _geom_from_cell(geoms[i].as_py())
                if geom is not None and not geom.is_empty:
                    c = geom.centroid
                    lng, lat = float(c.x), float(c.y)
            by_id[vid] = {
                "id": vid,
                "name": name,
                "name_l": name.lower(),
                "district": district,
                "state": state,
                "lng": lng,
                "lat": lat,
            }
        print(f"  cumulative unique villages: {len(by_id)}", flush=True)

    records = sorted(by_id.values(), key=lambda r: r["name_l"])
    with_c = sum(1 for r in records if r.get("lng") is not None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in records:
            payload = {
                "id": row["id"],
                "name": row["name"],
                "district": row.get("district"),
                "state": row.get("state"),
            }
            if row.get("lng") is not None and row.get("lat") is not None:
                payload["lng"] = row["lng"]
                payload["lat"] = row["lat"]
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    tmp.replace(out_path)
    print(
        f"Wrote {len(records)} villages ({with_c} with centroids) to {out_path} "
        f"in {time.time() - t0:.1f}s",
        flush=True,
    )
    return len(records)


def upload_to_s3(path: Path, key: str) -> None:
    import boto3
    from app.shared.config import settings

    bucket = settings.aws_s3_bucket
    if not bucket:
        raise SystemExit("AWS_S3_BUCKET is not set")
    client = boto3.client("s3", region_name=settings.aws_default_region or None)
    print(f"Uploading {path} → s3://{bucket}/{key} …", flush=True)
    client.upload_file(str(path), bucket, key)
    print("Upload complete.", flush=True)


def main() -> int:
    from app.shared.config import settings
    from app.shared.watersheds import _villages_vsis3_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="", help="Local villages.fgb, or empty for /vsis3/")
    parser.add_argument("--out", default="", help="Output JSONL path")
    parser.add_argument("--upload", action="store_true", help="Upload to S3 vector/villages_lookup.jsonl")
    parser.add_argument("--s3-key", default="vector/villages_lookup.jsonl")
    args = parser.parse_args()

    source = args.source.strip() or _villages_vsis3_path()
    if args.out:
        out = Path(args.out)
    else:
        packages = Path(settings.packages_dir)
        if str(packages).startswith("/app") or not packages.exists():
            out = Path(__file__).resolve().parents[1] / "packages" / "villages_lookup.jsonl"
        else:
            out = packages / "villages_lookup.jsonl"

    print(f"source={source}")
    print(f"out={out}")
    build_from_fgb(source, out)
    if args.upload:
        upload_to_s3(out, args.s3_key.lstrip("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
