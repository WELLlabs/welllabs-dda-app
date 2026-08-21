"""Look up watershed polygons from a FlatGeobuf file on S3 via GDAL /vsis3/."""

from __future__ import annotations

import json
import logging
import os

import pyogrio
from shapely import from_wkb
from shapely.geometry import Point, mapping

from app.shared.config import settings

logger = logging.getLogger(__name__)

_NAME_KEYS = ("name", "watershed_name", "NAME", "WATERSHED", "ws_name", "basin_name", "uid", "DN")
_ID_KEYS = ("id", "watershed_id", "FID", "fid", "OBJECTID", "objectid", "gid", "HYBAS_ID", "hybas_id", "uid")


def _configure_gdal_aws() -> None:
    region = os.environ.get("AWS_DEFAULT_REGION") or settings.aws_default_region
    os.environ.setdefault("AWS_DEFAULT_REGION", region)
    os.environ.setdefault("AWS_REGION", region)


def _fgb_vsis3_path() -> str:
    if not settings.aws_s3_bucket:
        raise ValueError("AWS_S3_BUCKET is not configured")
    key = settings.watersheds_fgb_key.lstrip("/")
    return f"/vsis3/{settings.aws_s3_bucket}/{key}"


def _pick_prop(props: dict, keys: tuple[str, ...], fallback: str = "") -> str:
    for key in keys:
        if key in props and props[key] not in (None, ""):
            return str(props[key])
    return fallback


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


def _row_props(table, index: int) -> dict:
    props = {}
    for name in table.column_names:
        if name in ("geometry", "wkb_geometry"):
            continue
        props[name] = table.column(name)[index].as_py()
    return props


def _find_containing(table, geom_col: str, point: Point):
    if table.num_rows == 0:
        return None, None

    geoms = table.column(geom_col)
    for i in range(table.num_rows):
        geom = from_wkb(geoms[i].as_py())
        if geom is None or not geom.is_valid:
            continue
        if geom.contains(point):
            return geom, _row_props(table, i)
    return None, None


def _find_intersecting(table, geom_col: str, shape):
    if table.num_rows == 0:
        return None, None

    geoms = table.column(geom_col)
    for i in range(table.num_rows):
        geom = from_wkb(geoms[i].as_py())
        if geom is not None and geom.intersects(shape):
            return geom, _row_props(table, i)
    return None, None


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

    watershed_name = _pick_prop(props, _NAME_KEYS)
    if not watershed_name:
        watershed_name = _pick_prop(props, _ID_KEYS, "Unknown watershed")
    watershed_id = _pick_prop(props, _ID_KEYS, watershed_name)

    return {
        "watershed_id": watershed_id,
        "watershed_name": watershed_name,
        "geometry": json.loads(json.dumps(mapping(geom))),
        "bounds": list(geom.bounds),
    }
