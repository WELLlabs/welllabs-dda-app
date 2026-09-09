"""Look up watershed polygons from a FlatGeobuf file on S3 via GDAL /vsis3/."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import pyogrio
from shapely import from_wkb, make_valid
from shapely.errors import GEOSException, ShapelyError
from shapely.geometry import MultiPolygon, Polygon, Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.shared.config import settings

logger = logging.getLogger(__name__)

_NAME_KEYS = ("name", "watershed_name", "NAME", "WATERSHED", "ws_name", "basin_name", "uid", "DN")
_ID_KEYS = ("id", "watershed_id", "FID", "fid", "OBJECTID", "objectid", "gid", "HYBAS_ID", "hybas_id", "uid")

# ~25–30 m — enough for map preview / AOI clip without shipping dense census rings.
_PREVIEW_SIMPLIFY_DEG = 0.00025
_village_resolve_cache: dict[str, tuple[float, dict]] = {}
_village_resolve_lock = threading.Lock()
_VILLAGE_RESOLVE_TTL_S = 45 * 60

_VILLAGE_NAME_KEYS = (
    "Village Na",
    "Village Name",
    "VILLAGE_NA",
    "VILLAGE_NAME",
    "village_name",
    "villname",
    "VILLNAME",
    "name",
    "Name",
    "NAME",
)
_VILLAGE_ID_KEYS = ("Village ID", "Village_ID", "vlcode", "VLCODE", "id", "fid", "FID", "OBJECTID")
_VILLAGE_DISTRICT_KEYS = (
    "District N",
    "District",
    "district",
    "DISTRICT",
    "dtname",
    "DTNAME",
)
_VILLAGE_STATE_KEYS = (
    "State Name",
    "State",
    "state",
    "STATE",
    "stname",
    "STNAME",
)

# Guardrails for custom / union AOIs (degrees / vertex count)
_MAX_BBOX_SPAN_DEG = 8.0
_MAX_VERTICES = 50_000
_MAX_UNION_PARTS = 200
_MIN_VILLAGE_QUERY_LEN = 4

# Approximate WGS84 bboxes for state-scoped centroid enrichment (fast spatial reads)
_STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "andaman and nicobar": (92.2, 6.7, 94.3, 13.7),
    "andhra pradesh": (76.5, 12.5, 84.9, 19.3),
    "arunachal pradesh": (91.5, 26.5, 97.5, 29.5),
    "assam": (89.6, 24.1, 96.1, 27.9),
    "bihar": (83.3, 24.2, 88.5, 27.6),
    "chandigarh": (76.68, 30.66, 76.84, 30.80),
    "chhattisgarh": (80.2, 17.8, 84.5, 24.2),
    "dadra and nagar haveli": (72.9, 20.0, 73.3, 20.5),
    "daman and diu": (72.7, 20.3, 73.0, 20.8),
    "delhi": (76.8, 28.4, 77.4, 28.9),
    "goa": (73.6, 14.8, 74.4, 15.9),
    "gujarat": (68.1, 20.1, 74.6, 24.8),
    "haryana": (74.4, 27.6, 77.7, 30.9),
    "himachal pradesh": (75.5, 30.3, 79.1, 33.3),
    "jammu and kashmir": (73.5, 32.2, 80.4, 37.1),
    "jharkhand": (83.3, 21.9, 87.9, 25.4),
    "karnataka": (74.0, 11.4, 78.6, 18.6),
    "kerala": (74.8, 8.2, 77.5, 12.9),
    "ladakh": (74.8, 32.2, 80.4, 36.1),
    "lakshadweep": (71.6, 8.1, 74.2, 12.4),
    "madhya pradesh": (74.0, 21.1, 82.9, 26.9),
    "maharashtra": (72.6, 15.6, 80.9, 22.1),
    "manipur": (93.0, 23.8, 94.8, 25.8),
    "meghalaya": (89.7, 25.0, 92.9, 26.2),
    "mizoram": (92.1, 21.9, 93.5, 24.6),
    "nagaland": (93.2, 25.1, 95.5, 27.1),
    "odisha": (81.3, 17.7, 87.6, 22.6),
    "puducherry": (79.6, 10.8, 79.9, 12.1),
    "punjab": (73.8, 29.5, 76.9, 32.6),
    "rajasthan": (69.4, 23.0, 78.3, 30.3),
    "sikkim": (88.0, 27.0, 88.9, 28.2),
    "tamil nadu": (76.2, 8.0, 80.4, 13.6),
    "telangana": (77.2, 15.8, 81.8, 19.9),
    "tripura": (91.1, 22.9, 92.4, 24.6),
    "uttar pradesh": (77.0, 23.8, 84.7, 30.5),
    "uttarakhand": (77.5, 28.7, 81.1, 31.5),
    "west bengal": (85.8, 21.4, 89.9, 27.3),
}
_INDIA_BBOX = (68.0, 6.0, 98.0, 38.0)

_village_name_index: list[dict] | None = None
_village_by_id: dict[str, dict] | None = None
_village_states_sorted: list[str] = []
_village_districts_by_state: dict[str, list[str]] = {}
_village_by_state_district: dict[tuple[str, str], list[dict]] = {}
_village_index_lock = threading.Lock()
_enriched_states: set[str] = set()
_enrich_lock = threading.Lock()


def _configure_gdal_aws() -> None:
    region = os.environ.get("AWS_DEFAULT_REGION") or settings.aws_default_region
    os.environ.setdefault("AWS_DEFAULT_REGION", region)
    os.environ.setdefault("AWS_REGION", region)


def _fgb_vsis3_path() -> str:
    if not settings.aws_s3_bucket:
        raise ValueError("AWS_S3_BUCKET is not configured")
    key = settings.watersheds_fgb_key.lstrip("/")
    return f"/vsis3/{settings.aws_s3_bucket}/{key}"


def _villages_s3_key() -> str:
    for key in (settings.vector_layers or "").split(","):
        key = key.strip()
        if key and "villages" in key.lower():
            return key.lstrip("/")
    return "vector/villages.fgb"


def _villages_vsis3_path() -> str:
    if not settings.aws_s3_bucket:
        raise ValueError("AWS_S3_BUCKET is not configured")
    return f"/vsis3/{settings.aws_s3_bucket}/{_villages_s3_key()}"


def _pick_prop(props: dict, keys: tuple[str, ...], fallback: str = "") -> str:
    for key in keys:
        if key in props and props[key] not in (None, ""):
            return str(props[key])
    return fallback


def _simplify_for_preview(geom):
    """Drop excess vertices for faster JSON + map paint; keep topology."""
    if geom is None or geom.is_empty:
        return geom
    try:
        simple = geom.simplify(_PREVIEW_SIMPLIFY_DEG, preserve_topology=True)
        if simple is None or simple.is_empty:
            return geom
        if simple.geom_type not in ("Polygon", "MultiPolygon"):
            return geom
        if not simple.is_valid:
            simple = make_valid(simple)
        if simple.geom_type not in ("Polygon", "MultiPolygon") or simple.is_empty:
            return geom
        return simple
    except Exception:
        return geom


def _geojson_geom(geom) -> dict:
    # mapping() is already JSON-serializable; avoid dumps/loads round-trip.
    return mapping(geom)


def _feature_payload(geom, props: dict | None = None, *, simplify: bool = True) -> dict:
    props = props or {}
    name = _pick_prop(props, _NAME_KEYS)
    if not name:
        name = _pick_prop(props, _ID_KEYS, "Unknown watershed")
    wid = _pick_prop(props, _ID_KEYS, name)
    out_geom = _simplify_for_preview(geom) if simplify else geom
    return {
        "watershed_id": wid,
        "watershed_name": name,
        "geometry": _geojson_geom(out_geom),
        "bounds": list(out_geom.bounds),
    }


def _read_bbox(path: str, lng: float, lat: float, pad: float):
    bbox = (lng - pad, lat - pad, lng + pad, lat + pad)
    result = pyogrio.read_arrow(path, bbox=bbox)
    if isinstance(result, tuple):
        meta, table = result
        geom_col = meta.get("geometry_name") or "wkb_geometry"
        if geom_col not in table.column_names and "wkb_geometry" in table.column_names:
            geom_col = "wkb_geometry"
        return table, geom_col
    geom_col = "geometry" if "geometry" in result.column_names else "wkb_geometry"
    return result, geom_col


def _read_bbox_extent(path: str, minx: float, miny: float, maxx: float, maxy: float, pad: float = 0.02):
    bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    result = pyogrio.read_arrow(path, bbox=bbox)
    if isinstance(result, tuple):
        meta, table = result
        geom_col = meta.get("geometry_name") or "wkb_geometry"
        if geom_col not in table.column_names and "wkb_geometry" in table.column_names:
            geom_col = "wkb_geometry"
        return table, geom_col
    geom_col = "geometry" if "geometry" in result.column_names else "wkb_geometry"
    return result, geom_col


def _prepare_geom(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Return a usable geom; skip make_valid on huge/broken rings (can hang or OOM)."""
    if geom is None or geom.is_empty:
        return None
    if geom.is_valid:
        return geom
    # Rough size gate — make_valid on dense census polygons has taken down the
    # single uvicorn worker (Cloudflare 502 for that request).
    try:
        if len(geom.wkb) > 250_000:
            return None
        fixed = make_valid(geom)
    except (GEOSException, ShapelyError, MemoryError, Exception):
        return None
    if fixed is None or fixed.is_empty:
        return None
    if fixed.geom_type not in ("Polygon", "MultiPolygon", "GeometryCollection"):
        return fixed
    return fixed


def _geom_from_cell(raw) -> BaseGeometry | None:
    """Parse an Arrow geometry cell; skip null/truncated WKB instead of crashing."""
    if raw is None:
        return None
    if isinstance(raw, BaseGeometry):
        return raw
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    if isinstance(raw, str):
        # Occasional hex WKB
        try:
            raw = bytes.fromhex(raw)
        except ValueError:
            return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    if len(raw) < 5:
        return None
    try:
        return from_wkb(raw)
    except (GEOSException, ShapelyError, TypeError, ValueError) as exc:
        logger.debug("Skipping unreadable WKB (%s bytes): %s", len(raw), exc)
        return None


def _row_props(table, index: int) -> dict:
    props = {}
    for name in table.column_names:
        if name in ("geometry", "wkb_geometry"):
            continue
        props[name] = table.column(name)[index].as_py()
    return props


_MAX_SCAN_ROWS = 600
_MAX_SCAN_ROWS_QUICK = 200


def _find_containing(table, geom_col: str, point: Point, *, quick: bool = False):
    if table.num_rows == 0:
        return None, None

    geoms = table.column(geom_col)
    limit = min(table.num_rows, _MAX_SCAN_ROWS_QUICK if quick else _MAX_SCAN_ROWS)
    for i in range(limit):
        raw = _geom_from_cell(geoms[i].as_py())
        # Quick path: never call make_valid — invalid/huge census rings are why
        # no-village clicks were taking down the API worker.
        geom = raw if quick else _prepare_geom(raw)
        if geom is None or geom.is_empty:
            continue
        try:
            if geom.contains(point) or geom.intersects(point):
                return geom, _row_props(table, i)
        except (GEOSException, ShapelyError):
            continue
    return None, None


def _find_intersecting(table, geom_col: str, shape_geom, *, quick: bool = False):
    if table.num_rows == 0:
        return None, None

    geoms = table.column(geom_col)
    limit = min(table.num_rows, _MAX_SCAN_ROWS_QUICK if quick else _MAX_SCAN_ROWS)
    for i in range(limit):
        raw = _geom_from_cell(geoms[i].as_py())
        geom = raw if quick else _prepare_geom(raw)
        if geom is None or geom.is_empty:
            continue
        try:
            if geom.intersects(shape_geom):
                return geom, _row_props(table, i)
        except (GEOSException, ShapelyError):
            continue
    return None, None


def _collect_intersecting(table, geom_col: str, shape_geom) -> list[tuple[Any, dict]]:
    if table.num_rows == 0:
        return []
    out: list[tuple[Any, dict]] = []
    geoms = table.column(geom_col)
    limit = min(table.num_rows, _MAX_SCAN_ROWS)
    for i in range(limit):
        geom = _prepare_geom(_geom_from_cell(geoms[i].as_py()))
        if geom is None:
            continue
        try:
            if geom.intersects(shape_geom):
                out.append((geom, _row_props(table, i)))
        except (GEOSException, ShapelyError):
            continue
    return out


def lookup_watershed(lng: float, lat: float) -> dict:
    """Return the watershed feature containing (lng, lat) using S3 range reads."""
    _configure_gdal_aws()
    path = _fgb_vsis3_path()
    point = Point(lng, lat)
    logger.info("Watershed lookup at (%s, %s) via %s", lng, lat, path)

    geom = None
    props = None
    for pad in (0.05, 0.2, 0.5):
        try:
            table, geom_col = _read_bbox(path, lng, lat, pad)
        except Exception as exc:
            logger.exception("Failed reading watersheds from %s", path)
            raise ValueError(f"Could not read watersheds file: {exc}") from exc

        geom, props = _find_containing(table, geom_col, point)
        if geom is not None:
            break

        geom, props = _find_intersecting(table, geom_col, point.buffer(0.01))
        if geom is not None:
            break

    if geom is None or props is None:
        raise ValueError(f"No watershed contains point ({lng}, {lat})")

    return _feature_payload(geom, props)


def village_containing_point(
    lng: float,
    lat: float,
    *,
    quick: bool = False,
) -> tuple[Any, dict]:
    """Return the village polygon containing (lng, lat), if any.

    ``quick=True`` is for map-click enrichment: one small bbox, no make_valid,
    so points with *no* village still return immediately instead of scanning
    (and potentially OOMing on) surrounding census polygons.
    """
    _configure_gdal_aws()
    path = _villages_vsis3_path()
    point = Point(lng, lat)
    pads = (0.015,) if quick else (0.02, 0.06, 0.12)
    for pad in pads:
        try:
            table, geom_col = _read_bbox(path, lng, lat, pad)
        except Exception as exc:
            logger.warning("Village containing-point read failed pad=%s: %s", pad, exc)
            continue
        geom, props = _find_containing(table, geom_col, point, quick=quick)
        if geom is None and not quick:
            geom, props = _find_intersecting(
                table, geom_col, point.buffer(0.002), quick=False
            )
        if geom is not None and props is not None:
            return geom, props
    raise ValueError(f"No village contains point ({lng}, {lat})")


_VILLAGE_ENRICH_TIMEOUT_S = 8.0


def _enrich_point_with_village(hit: dict, lng: float, lat: float) -> dict:
    """Attach village outline + intersecting micros when present; never raise.

    Points outside any village return the L12 hit unchanged (no error, no 502).
    """
    try:
        village_geom, village_props = village_containing_point(lng, lat, quick=True)
    except ValueError:
        # Expected for clicks with no village — keep L12 clip only.
        return hit
    except Exception as exc:
        logger.warning(
            "Village context for point (%s, %s) failed; returning L12 only: %s",
            lng,
            lat,
            exc,
        )
        return hit

    try:
        village_name = _pick_prop(village_props, _VILLAGE_NAME_KEYS) or None
        hit["village_geometry"] = _geojson_geom(_simplify_for_preview(village_geom))
        hit["village_name"] = village_name

        parts = watersheds_intersecting(village_geom)
        hit["parts"] = parts
        if len(parts) > 1:
            unioned = union_geometries(parts, village_name=village_name)
            hit["all_geometry"] = unioned["geometry"]
            hit["all_watershed_id"] = unioned["watershed_id"]
            hit["all_watershed_name"] = unioned["watershed_name"]
            hit["all_bounds"] = unioned["bounds"]
    except ValueError:
        # Village found but micro intersect failed — still keep village outline.
        return hit
    except Exception as exc:
        logger.warning(
            "Village multi-micro enrich for (%s, %s) failed; returning L12 only: %s",
            lng,
            lat,
            exc,
        )
    return hit


def lookup_watershed_with_village_context(lng: float, lat: float) -> dict:
    """Point L12 lookup, plus village micros when the point falls in a village.

    Default clip geometry remains the L12 under the click. When the containing
    village intersects multiple micros, ``parts`` lists them and ``all_*`` holds
    the union clip for an optional "all intersecting" choice.

    Village enrichment is time-boxed so a slow/corrupt FGB read cannot hang the
    single uvicorn worker long enough for Cloudflare to return HTML 502.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    hit = lookup_watershed(lng, lat)
    hit["parts"] = []
    hit["source"] = "point"
    hit["seed_lng"] = float(lng)
    hit["seed_lat"] = float(lat)
    hit["village_geometry"] = None
    hit["village_name"] = None

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_enrich_point_with_village, dict(hit), lng, lat)
        try:
            return fut.result(timeout=_VILLAGE_ENRICH_TIMEOUT_S)
        except FuturesTimeout:
            logger.warning(
                "Village enrich timed out after %.0fs for (%s, %s); returning L12 only",
                _VILLAGE_ENRICH_TIMEOUT_S,
                lng,
                lat,
            )
            return hit
        except Exception as exc:
            logger.warning(
                "Village enrich failed for (%s, %s); returning L12 only: %s",
                lng,
                lat,
                exc,
            )
            return hit


def parse_geojson_polygon(geometry: dict) -> Polygon | MultiPolygon:
    """Validate client GeoJSON as a non-empty Polygon/MultiPolygon in WGS84."""
    if not isinstance(geometry, dict) or "type" not in geometry:
        raise ValueError("geometry must be a GeoJSON object")
    gtype = geometry.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        raise ValueError("geometry must be a Polygon or MultiPolygon")
    try:
        geom = shape(geometry)
    except Exception as exc:
        raise ValueError(f"Invalid GeoJSON geometry: {exc}") from exc
    if geom is None or geom.is_empty:
        raise ValueError("geometry is empty")
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            raise ValueError("geometry must contain a polygon")
        geom = unary_union(polys)
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("geometry must resolve to a Polygon or MultiPolygon")
    if geom.area <= 0:
        raise ValueError("geometry has no area")

    minx, miny, maxx, maxy = geom.bounds
    if (maxx - minx) > _MAX_BBOX_SPAN_DEG or (maxy - miny) > _MAX_BBOX_SPAN_DEG:
        raise ValueError(
            f"geometry bbox exceeds {_MAX_BBOX_SPAN_DEG}° — use a smaller area of interest"
        )
    coords = geometry.get("coordinates") or []
    flat = json.dumps(coords)
    vertex_est = flat.count("[") // 2
    if vertex_est > _MAX_VERTICES:
        raise ValueError(f"geometry has too many vertices (max {_MAX_VERTICES})")
    return geom


def custom_aoi_from_geometry(geometry: dict, *, name: str | None = None) -> dict:
    """Treat an uploaded polygon as the clip boundary."""
    geom = parse_geojson_polygon(geometry)
    label = (name or "").strip() or "Custom AOI"
    centroid = geom.centroid
    return {
        "watershed_id": "custom",
        "watershed_name": label,
        "geometry": _geojson_geom(geom),
        "bounds": list(geom.bounds),
        "parts": [],
        "source": "custom",
        "seed_lng": float(centroid.x),
        "seed_lat": float(centroid.y),
    }


def watersheds_intersecting(geom) -> list[dict]:
    """Return all Level-12 watershed features intersecting geom."""
    _configure_gdal_aws()
    path = _fgb_vsis3_path()
    if isinstance(geom, dict):
        geom = parse_geojson_polygon(geom)
    minx, miny, maxx, maxy = geom.bounds
    try:
        table, geom_col = _read_bbox_extent(path, minx, miny, maxx, maxy, pad=0.05)
    except Exception as exc:
        logger.exception("Failed reading watersheds for intersect from %s", path)
        raise ValueError(f"Could not read watersheds file: {exc}") from exc

    hits = _collect_intersecting(table, geom_col, geom)
    if not hits:
        try:
            table, geom_col = _read_bbox_extent(path, minx, miny, maxx, maxy, pad=0.15)
            hits = _collect_intersecting(table, geom_col, geom)
        except Exception as exc:
            raise ValueError(f"Could not read watersheds file: {exc}") from exc

    if not hits:
        raise ValueError("No watersheds intersect the given geometry")
    if len(hits) > _MAX_UNION_PARTS:
        raise ValueError(
            f"Too many intersecting watersheds ({len(hits)}; max {_MAX_UNION_PARTS})"
        )

    return [_feature_payload(g, props) for g, props in hits]


def union_geometries(
    features: list[dict],
    *,
    village_name: str | None = None,
) -> dict:
    """Union watershed feature payloads into one clip preview."""
    if not features:
        raise ValueError("No watershed features to union")

    geoms = []
    for feat in features:
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        geoms.append(g)

    merged = unary_union(geoms)
    if merged.is_empty:
        raise ValueError("Union of watersheds is empty")
    if not merged.is_valid:
        merged = make_valid(merged)
    if merged.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Union did not produce a polygon")
    merged = _simplify_for_preview(merged)

    ids = [str(f.get("watershed_id") or "") for f in features if f.get("watershed_id")]
    ids = [i for i in ids if i]
    if len(ids) == 1:
        wid = ids[0]
    elif ids:
        joined = ",".join(ids[:12])
        wid = joined if len(ids) <= 12 else f"union:{len(ids)}"
    else:
        wid = f"union:{len(features)}"

    n = len(features)
    base_name = f"{n} watershed{'s' if n != 1 else ''} (union)"
    if village_name:
        base_name = f"{village_name} — {base_name}"

    centroid = merged.centroid
    return {
        "watershed_id": wid,
        "watershed_name": base_name,
        "geometry": _geojson_geom(merged),
        "bounds": list(merged.bounds),
        "parts": features,
        "source": "village",
        "seed_lng": float(centroid.x),
        "seed_lat": float(centroid.y),
    }


def _escape_ogr_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def _village_row_to_hit(props: dict, geom=None) -> dict:
    vid = _pick_prop(props, _VILLAGE_ID_KEYS, "")
    name = _pick_prop(props, _VILLAGE_NAME_KEYS, "Unnamed village")
    if not vid:
        if geom is not None and not geom.is_empty:
            c = geom.centroid
            vid = f"v:{name}:{c.x:.5f}:{c.y:.5f}"
        else:
            vid = f"v:{name}"
    hit = {
        "id": vid,
        "name": name,
        "district": _pick_prop(props, _VILLAGE_DISTRICT_KEYS) or None,
        "state": _pick_prop(props, _VILLAGE_STATE_KEYS) or None,
    }
    if geom is not None and not geom.is_empty:
        hit["bounds"] = list(geom.bounds)
        hit["geometry"] = _geojson_geom(geom)
    return hit


def _village_index_cache_path() -> Path:
    return Path(settings.packages_dir) / "villages_name_index.jsonl"


def _set_village_indexes(records: list[dict]) -> list[dict]:
    global _village_name_index, _village_by_id
    records.sort(key=lambda r: r["name_l"])
    _village_name_index = records
    _village_by_id = {r["id"]: r for r in records if r.get("id")}
    _rebuild_village_lookup_indexes(records)
    return records


def _rebuild_village_lookup_indexes(records: list[dict]) -> None:
    global _village_states_sorted, _village_districts_by_state, _village_by_state_district
    states: set[str] = set()
    districts_by_state: dict[str, set[str]] = {}
    by_sd: dict[tuple[str, str], list[dict]] = {}
    for row in records:
        state_raw = row.get("state")
        district_raw = row.get("district")
        if not state_raw:
            continue
        states.add(state_raw)
        state_key = str(state_raw).lower()
        if not district_raw:
            continue
        district_key = str(district_raw).lower()
        districts_by_state.setdefault(state_key, set()).add(district_raw)
        key = (state_key, district_key)
        bucket = by_sd.setdefault(key, [])
        bucket.append(
            {
                "id": row["id"],
                "name": row["name"],
                "district": district_raw,
                "state": state_raw,
            }
        )
    _village_states_sorted = sorted(states, key=str.lower)
    _village_districts_by_state = {
        s: sorted(ds, key=str.lower) for s, ds in districts_by_state.items()
    }
    _village_by_state_district = by_sd


def warm_state_village_centroids_async(state: str) -> None:
    """Background S3 read so district/village lists stay instant."""
    s = (state or "").strip()
    if not s:
        return
    threading.Thread(
        target=ensure_state_village_centroids,
        args=(s,),
        name=f"village-centroids-{s[:24]}",
        daemon=True,
    ).start()


def _load_village_index_from_cache(path: Path) -> list[dict] | None:
    if not path.is_file():
        return None
    records: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                name = str(row.get("name") or "").strip()
                vid = str(row.get("id") or "").strip()
                if not name or not vid:
                    continue
                rec = {
                    "id": vid,
                    "name": name,
                    "name_l": name.lower(),
                    "district": row.get("district") or None,
                    "state": row.get("state") or None,
                }
                if row.get("lng") is not None and row.get("lat") is not None:
                    rec["lng"] = float(row["lng"])
                    rec["lat"] = float(row["lat"])
                records.append(rec)
    except Exception as exc:
        logger.warning("Failed to read village name index cache %s: %s", path, exc)
        return None
    return records or None


def _write_village_index_cache(path: Path, records: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
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
        tmp.replace(path)
        logger.info("Wrote village name index cache (%s rows) to %s", len(records), path)
    except Exception as exc:
        logger.warning("Could not write village name index cache: %s", exc)


def _build_village_name_index_from_fgb() -> list[dict]:
    """One-time attribute-only read of villages.fgb (~40s over S3); centroids added per-state later."""
    _configure_gdal_aws()
    path = _villages_vsis3_path()
    logger.info("Building village name index from %s …", path)
    df = pyogrio.read_dataframe(
        path,
        columns=["Village Na", "Village ID", "District N", "State Name"],
        read_geometry=False,
    )
    records: list[dict] = []
    name_series = df["Village Na"] if "Village Na" in df.columns else None
    id_series = df["Village ID"] if "Village ID" in df.columns else None
    dist_series = df["District N"] if "District N" in df.columns else None
    state_series = df["State Name"] if "State Name" in df.columns else None
    for i in range(len(df)):
        name = str(name_series.iloc[i] if name_series is not None else "").strip()
        if not name or name.lower() == "nan":
            continue
        raw_id = id_series.iloc[i] if id_series is not None else None
        vid = str(int(raw_id)) if raw_id is not None and str(raw_id) not in ("", "nan") else ""
        if not vid:
            continue
        district = None
        state = None
        if dist_series is not None:
            d = str(dist_series.iloc[i]).strip()
            if d and d.lower() != "nan":
                district = d
        if state_series is not None:
            s = str(state_series.iloc[i]).strip()
            if s and s.lower() != "nan":
                state = s
        records.append(
            {
                "id": vid,
                "name": name,
                "name_l": name.lower(),
                "district": district,
                "state": state,
            }
        )
    logger.info("Village name index ready (%s rows)", len(records))
    return records


def ensure_village_name_index(*, force_rebuild: bool = False) -> list[dict]:
    """Load or build the national village name index (cached under packages_dir)."""
    global _village_name_index
    if _village_name_index is not None and not force_rebuild:
        return _village_name_index
    with _village_index_lock:
        if _village_name_index is not None and not force_rebuild:
            return _village_name_index
        cache_path = _village_index_cache_path()
        if not force_rebuild:
            cached = _load_village_index_from_cache(cache_path)
            if cached is not None:
                logger.info("Loaded village name index from cache (%s rows)", len(cached))
                return _set_village_indexes(cached)
        records = _build_village_name_index_from_fgb()
        _write_village_index_cache(cache_path, records)
        return _set_village_indexes(records)


def warm_village_name_index() -> None:
    """Best-effort background warm so the first typeahead is instant."""
    try:
        ensure_village_name_index()
    except Exception as exc:
        logger.warning("Village name index warm failed: %s", exc)


def ensure_state_village_centroids(state: str) -> None:
    """Spatial-read one state bbox and attach centroids to the in-memory index."""
    s = (state or "").strip().lower()
    if not s:
        return
    if s in _enriched_states:
        return
    with _enrich_lock:
        if s in _enriched_states:
            return
        ensure_village_name_index()
        if _village_by_id is None:
            return
        bbox = _STATE_BBOXES.get(s, _INDIA_BBOX)
        _configure_gdal_aws()
        path = _villages_vsis3_path()
        logger.info("Enriching village centroids for state=%s bbox=%s", s, bbox)
        t0 = time.time()
        try:
            table, geom_col = _read_bbox_extent(path, bbox[0], bbox[1], bbox[2], bbox[3], pad=0.05)
        except Exception as exc:
            logger.warning("Centroid enrich failed for %s: %s", s, exc)
            return
        geoms = table.column(geom_col) if geom_col in table.column_names else None
        updated = 0
        for i in range(table.num_rows):
            props = _row_props(table, i)
            vid = _pick_prop(props, _VILLAGE_ID_KEYS)
            if not vid:
                continue
            try:
                vid = str(int(float(vid)))
            except (TypeError, ValueError):
                vid = str(vid).strip()
            rec = _village_by_id.get(vid)
            if rec is None or geoms is None:
                continue
            geom = _geom_from_cell(geoms[i].as_py())
            if geom is None or geom.is_empty:
                continue
            c = geom.centroid
            rec["lng"] = float(c.x)
            rec["lat"] = float(c.y)
            updated += 1
        _enriched_states.add(s)
        logger.info(
            "Enriched %s village centroids for %s in %.1fs",
            updated,
            s,
            time.time() - t0,
        )


def _village_record_by_id(village_id: str) -> dict | None:
    ensure_village_name_index()
    if _village_by_id is None:
        return None
    return _village_by_id.get(str(village_id).strip())


def search_villages(
    query: str,
    *,
    limit: int = 20,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """National typeahead against a cached name index (vector/villages.fgb).

    Requires at least 4 characters. ``bbox`` is ignored (kept for API compat).
    Geometry is loaded later via ``village_geometry_by_id`` on select.
    """
    del bbox  # national index search; bbox no longer required
    q = (query or "").strip()
    if len(q) < _MIN_VILLAGE_QUERY_LEN:
        return []
    limit = max(1, min(int(limit), 50))
    q_lower = q.lower()

    try:
        index = ensure_village_name_index()
    except Exception as exc:
        logger.warning("Village search index unavailable: %s", exc)
        raise ValueError(f"Village search failed: {exc}") from exc

    starts: list[dict] = []
    contains: list[dict] = []
    first = q_lower[0]
    pool = [r for r in index if r["name_l"] and r["name_l"][0] == first]
    if not pool:
        pool = index

    for row in pool:
        name_l = row["name_l"]
        if q_lower not in name_l:
            continue
        hit = {
            "id": row["id"],
            "name": row["name"],
            "district": row.get("district"),
            "state": row.get("state"),
        }
        if name_l.startswith(q_lower):
            starts.append(hit)
            if len(starts) >= limit:
                return starts
        else:
            contains.append(hit)
            if len(starts) + len(contains) >= limit * 3:
                break

    return (starts + contains)[:limit]


def _village_id_matches(props: dict, vid: str) -> bool:
    for key in _VILLAGE_ID_KEYS:
        if key not in props or props[key] in (None, ""):
            continue
        raw = props[key]
        try:
            if str(int(float(raw))) == vid:
                return True
        except (TypeError, ValueError):
            if str(raw).strip() == vid:
                return True
    return False


def village_geometry_by_id(village_id: str) -> tuple[Any, dict]:
    """Load a village polygon by id using centroid-scoped S3 range reads."""
    vid = (village_id or "").strip()
    if not vid:
        raise ValueError("village_id is required")

    _configure_gdal_aws()
    path = _villages_vsis3_path()

    syn = re.match(r"^v:(.+):(-?\d+\.\d+):(-?\d+\.\d+)$", vid)
    if syn:
        lng, lat = float(syn.group(2)), float(syn.group(3))
        point = Point(lng, lat)
        for pad in (0.02, 0.1, 0.3):
            table, geom_col = _read_bbox(path, lng, lat, pad)
            geom, props = _find_containing(table, geom_col, point)
            if geom is None:
                geom, props = _find_intersecting(table, geom_col, point.buffer(0.005))
            if geom is not None and props is not None:
                return geom, props
        raise ValueError(f"Village not found for id {vid}")

    # Preferred path: centroid from name index → small spatial read (seconds, not minutes)
    meta = _village_record_by_id(vid)
    if meta and (meta.get("lng") is None or meta.get("lat") is None) and meta.get("state"):
        ensure_state_village_centroids(str(meta["state"]))
        meta = _village_record_by_id(vid)

    if meta and meta.get("lng") is not None and meta.get("lat") is not None:
        lng = float(meta["lng"])
        lat = float(meta["lat"])
        point = Point(lng, lat)
        for pad in (0.02, 0.05, 0.12, 0.3):
            try:
                table, geom_col = _read_bbox(path, lng, lat, pad)
            except Exception as exc:
                logger.warning("Village bbox read failed pad=%s: %s", pad, exc)
                continue
            geoms = table.column(geom_col) if geom_col in table.column_names else None
            if geoms is None:
                continue
            for i in range(table.num_rows):
                props = _row_props(table, i)
                if not _village_id_matches(props, vid):
                    continue
                geom = _geom_from_cell(geoms[i].as_py())
                if geom is None or geom.is_empty:
                    continue
                return geom, props
            # Fallback: polygon containing the indexed centroid
            geom, props = _find_containing(table, geom_col, point)
            if geom is not None and props is not None:
                return geom, props
        raise ValueError(f"Village not found for id {vid} near ({lng}, {lat})")

    raise ValueError(
        f"Village location unknown for id {vid} — pick the state again to load locations, then retry"
    )


def resolve_village_watersheds(
    *,
    village_id: str | None = None,
    geometry: dict | None = None,
) -> dict:
    """Village polygon → intersecting Level-12 basins → union clip preview."""
    cache_key = (village_id or "").strip() or None
    if cache_key and geometry is None:
        with _village_resolve_lock:
            hit = _village_resolve_cache.get(cache_key)
        if hit is not None:
            ts, payload = hit
            if (time.monotonic() - ts) < _VILLAGE_RESOLVE_TTL_S:
                logger.info("Village watershed resolve cache hit id=%s", cache_key)
                return payload

    t0 = time.monotonic()
    village_name = None
    village_geom_geojson = None
    if geometry is not None:
        village_geom = parse_geojson_polygon(geometry)
        village_geom_geojson = _geojson_geom(_simplify_for_preview(village_geom))
    elif village_id:
        village_geom, props = village_geometry_by_id(village_id)
        village_name = _pick_prop(props, _VILLAGE_NAME_KEYS) or None
        village_geom_geojson = _geojson_geom(_simplify_for_preview(village_geom))
    else:
        raise ValueError("Provide village_id or geometry")

    parts = watersheds_intersecting(village_geom)
    result = union_geometries(parts, village_name=village_name)
    result["village_geometry"] = village_geom_geojson
    result["village_name"] = village_name
    # Client snapshots geometry as the "all" choice — avoid duplicating large polygons
    # in the JSON body (was doubling response size / parse time).
    logger.info(
        "Village watershed resolve id=%s parts=%s in %.2fs",
        cache_key or "geometry",
        len(parts),
        time.monotonic() - t0,
    )

    if cache_key and geometry is None:
        with _village_resolve_lock:
            _village_resolve_cache[cache_key] = (time.monotonic(), result)
            # Bound memory if many villages are probed in one process.
            if len(_village_resolve_cache) > 256:
                oldest = sorted(_village_resolve_cache.items(), key=lambda kv: kv[1][0])[:64]
                for key, _ in oldest:
                    _village_resolve_cache.pop(key, None)

    return result


def list_village_states() -> list[str]:
    ensure_village_name_index()
    return list(_village_states_sorted)


def list_village_districts(state: str) -> list[str]:
    s = (state or "").strip().lower()
    if not s:
        raise ValueError("state is required")
    ensure_village_name_index()
    # Kick warm early so by-district rarely blocks on first open.
    warm_state_village_centroids_async(state)
    return list(_village_districts_by_state.get(s, []))


def _norm_place_token(value: str) -> str:
    """Normalize state/district strings for fuzzy matching (Tiruvallur ↔ Thiruvallur)."""
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    # Common Tamil Nadu / census spelling variants
    s = s.replace("thiru", "tiru")
    s = s.replace("kanchee", "kanchi")
    s = s.replace("puducherry", "pondicherry")
    return s


def _resolve_district_bucket_key(state_key: str, district: str) -> tuple[str, str] | None:
    """Return (state_key, district_key) for village lookup, with fuzzy district match."""
    d_raw = (district or "").strip()
    if not state_key or not d_raw:
        return None
    d_key = d_raw.lower()
    if (state_key, d_key) in _village_by_state_district:
        return state_key, d_key

    target = _norm_place_token(d_raw)
    if not target:
        return None
    for cand in _village_districts_by_state.get(state_key, []):
        if _norm_place_token(cand) == target:
            return state_key, str(cand).lower()
    # Partial contains either way (e.g. "thiruvallur district")
    for cand in _village_districts_by_state.get(state_key, []):
        cn = _norm_place_token(cand)
        if target in cn or cn in target:
            return state_key, str(cand).lower()
    return None


def list_villages_for_district(
    state: str,
    district: str,
    *,
    q: str = "",
    limit: int | None = None,
) -> list[dict]:
    s = (state or "").strip().lower()
    d = (district or "").strip().lower()
    if not s or not d:
        raise ValueError("state and district are required")
    ensure_village_name_index()
    # Finish centroid enrich before the user picks a village — otherwise
    # village_geometry_by_id blocks on a full-state S3 read (often minutes).
    ensure_state_village_centroids(state)
    q_lower = (q or "").strip().lower()

    resolved = _resolve_district_bucket_key(s, d)
    rows = list(_village_by_state_district.get(resolved, [])) if resolved else []
    if not rows:
        # Last resort: scan index for fuzzy state+district (handles odd casing/spacing).
        target_state = _norm_place_token(s)
        target_district = _norm_place_token(d)
        index = _village_name_index or []
        rows = []
        seen: set[str] = set()
        for row in index:
            if _norm_place_token(str(row.get("state") or "")) != target_state:
                continue
            if _norm_place_token(str(row.get("district") or "")) != target_district:
                continue
            rid = str(row.get("id") or "")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            rows.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "district": row.get("district"),
                    "state": row.get("state"),
                }
            )

    # Deduplicate identical census ids while preserving order
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for row in rows:
        rid = str(row.get("id") or "")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        deduped.append(row)
    rows = deduped

    if q_lower:
        rows = [r for r in rows if q_lower in str(r.get("name") or "").lower()]
    rows.sort(key=lambda r: str(r.get("name") or "").lower())
    if limit is None:
        return rows
    return rows[: max(1, min(int(limit), 10_000))]
