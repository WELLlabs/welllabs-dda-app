#!/usr/bin/env python3
"""Convert the national drainage-lines GeoJSON into an indexed FlatGeobuf.

The source is one huge GeoJSON FeatureCollection (~13 GB, no newlines, no
spatial index). GDAL's GeoJSON reader can exhaust RAM on it, so this script
streams the file in fixed-size chunks with bounded memory:

  1. Split the byte stream on the ``{"type":"Feature"`` marker, parse features
     in batches, simplify, and append to a temporary GeoPackage.
  2. ``ogr2ogr`` the GeoPackage into a FlatGeobuf with a packed R-tree.
  3. Delete the temporary GeoPackage.

Only the Strahler stream order (``ORDER``) is kept. Geometries are simplified
at 0.0001 deg (~11 m) — under half a 30 m pixel, the grid the lines were traced
on — which cuts vertex count without changing the network.

Usage (needs pyogrio + shapely from backend/requirements.txt, and ogr2ogr):

  python backend/scripts/build_drainage_fgb.py --source "Drainage Lines" --out drainage_lines.fgb

Then point DESIGN_DRAINAGE_PATH at the output (or its /vsis3/ path after upload).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from pyogrio.raw import write as ogr_write
import shapely

MARKER = b'{"type":"Feature"'
CHUNK_BYTES = 64 * 1024 * 1024
BATCH_FEATURES = 100_000
LAYER = "drainage_lines"


def _iter_feature_bytes(path: Path):
    """Yield each feature's raw JSON bytes from a FeatureCollection, streaming."""
    buf = b""
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_BYTES)
            buf += chunk
            starts = []
            pos = buf.find(MARKER)
            while pos != -1:
                starts.append(pos)
                pos = buf.find(MARKER, pos + 1)
            # Every feature except the last one found is complete.
            complete = starts if not chunk else starts[:-1]
            for i, s in enumerate(complete):
                end = starts[i + 1] if i + 1 < len(starts) else len(buf)
                yield buf[s:end]
            if not chunk:
                return
            buf = buf[starts[-1]:] if starts else buf[-len(MARKER):]


def _clean(raw: bytes) -> dict:
    text = raw.rstrip()
    # Trailing separators: "," between features, "]}" after the last one.
    while text and text[-1:] in (b",", b"]", b"}", b" ", b"\n"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text = text[:-1].rstrip()
    return json.loads(text)


def _flush(gpkg: Path, geoms: list, orders: list, simplify: float, first: bool) -> None:
    arr = np.asarray(geoms, dtype=object)
    if simplify > 0:
        arr = shapely.simplify(arr, simplify, preserve_topology=False)
    keep = ~shapely.is_empty(arr)
    ogr_write(
        str(gpkg),
        geometry=shapely.to_wkb(arr[keep]),
        field_data=[np.asarray(orders, dtype=np.int16)[keep]],
        fields=["ORDER"],
        layer=LAYER,
        driver="GPKG",
        geometry_type="MultiLineString",
        crs="EPSG:4326",
        append=not first,
        promote_to_multi=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Drainage lines GeoJSON (FeatureCollection)")
    parser.add_argument("--out", default="drainage_lines.fgb", help="Output FlatGeobuf path")
    parser.add_argument(
        "--simplify",
        type=float,
        default=0.0001,
        help="Simplification tolerance in degrees (0 disables; default 0.0001 ≈ 11 m)",
    )
    args = parser.parse_args()

    if not shutil.which("ogr2ogr"):
        print("ogr2ogr not found on PATH (install GDAL)", file=sys.stderr)
        return 1
    src = Path(args.source)
    if not src.is_file():
        print(f"Source not found: {src}", file=sys.stderr)
        return 1
    out = Path(args.out)
    gpkg = out.with_suffix(".tmp.gpkg")
    for p in (out, gpkg):
        p.unlink(missing_ok=True)

    total_bytes = src.stat().st_size
    t0 = time.time()
    geoms: list = []
    orders: list = []
    n = skipped = 0
    first = True
    consumed = 0
    for raw in _iter_feature_bytes(src):
        consumed += len(raw)
        try:
            feat = _clean(raw)
            geom = shapely.from_geojson(json.dumps(feat["geometry"]))
            order = int((feat.get("properties") or {}).get("ORDER") or 0)
        except Exception:
            skipped += 1
            continue
        geoms.append(geom)
        orders.append(order)
        if len(geoms) >= BATCH_FEATURES:
            _flush(gpkg, geoms, orders, args.simplify, first)
            first = False
            n += len(geoms)
            geoms, orders = [], []
            pct = 100 * consumed / total_bytes
            print(f"  {n:,} features · {pct:5.1f}% · {time.time() - t0:,.0f}s", flush=True)
    if geoms:
        _flush(gpkg, geoms, orders, args.simplify, first)
        n += len(geoms)
    print(f"Parsed {n:,} features ({skipped:,} skipped) → {gpkg} in {time.time() - t0:,.0f}s", flush=True)

    cmd = [
        "ogr2ogr", "-f", "FlatGeobuf", "-nln", LAYER,
        "-lco", "SPATIAL_INDEX=YES", str(out), str(gpkg), LAYER,
    ]
    print("Running:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"ogr2ogr failed with exit code {result.returncode}; temp GPKG kept at {gpkg}", file=sys.stderr)
        return result.returncode
    gpkg.unlink(missing_ok=True)
    print(f"Wrote {out} ({out.stat().st_size / 1e6:,.0f} MB) in {time.time() - t0:,.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
