#!/usr/bin/env python3
"""Build national village lookup JSONL from Village_pan_India.fgb.

Dropdowns and map-click village resolve should use this file — not live per-state
S3 spatial enrich.

Usage (from backend/, with AWS creds / .env loaded):

  python scripts/build_village_lookup.py
  python scripts/build_village_lookup.py --upload
  python scripts/build_village_lookup.py --source /path/to/Village_pan_India.fgb

Writes:
  - local: packages_dir/Village_pan_India_lookup.jsonl (or --out)
  - optional S3: s3://$AWS_S3_BUCKET/vector/Village_pan_India_lookup.jsonl
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
        _build_village_name_index_from_fgb,
        _configure_gdal_aws,
        _index_centroid_coverage,
        _write_village_index_cache,
    )

    _configure_gdal_aws()
    t0 = time.time()
    records = _build_village_name_index_from_fgb(source)
    _write_village_index_cache(out_path, records)
    print(
        f"Wrote {len(records)} villages "
        f"({int(100 * _index_centroid_coverage(records))}% centroids) to {out_path} "
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
    from app.shared.watersheds import _VILLAGE_LOOKUP_FILENAME, _villages_lookup_s3_key, _villages_vsis3_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="", help="Local Village_pan_India.fgb, or empty for /vsis3/")
    parser.add_argument("--out", default="", help="Output JSONL path")
    parser.add_argument("--upload", action="store_true", help="Upload lookup JSONL to S3")
    parser.add_argument("--s3-key", default="", help="Override S3 key (default vector/Village_pan_India_lookup.jsonl)")
    args = parser.parse_args()

    source = args.source.strip() or _villages_vsis3_path()
    if args.out:
        out = Path(args.out)
    else:
        packages = Path(settings.packages_dir)
        if str(packages).startswith("/app") or not packages.exists():
            out = Path(__file__).resolve().parents[1] / "packages" / _VILLAGE_LOOKUP_FILENAME
        else:
            out = packages / _VILLAGE_LOOKUP_FILENAME

    print(f"source={source}")
    print(f"out={out}")
    build_from_fgb(source, out)
    if args.upload:
        upload_to_s3(out, (args.s3_key or _villages_lookup_s3_key()).lstrip("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
