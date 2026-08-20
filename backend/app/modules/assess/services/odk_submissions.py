"""Normalize ODK Central OData submissions for MEL form explore."""

from __future__ import annotations

import re
from typing import Any

META_SKIP = {
    "__id",
    "__system",
    "meta",
    "instanceid",
    "instancename",
    "deviceid",
    "subscriberid",
    "simid",
    "phonenumber",
}


def parse_geopoint(raw: Any) -> tuple[float | None, float | None]:
    """Parse ODK geopoint from submission XML string or OData GeoJSON Point.

    XML / Collect style: ``\"lat lon altitude accuracy\"``
    OData style: ``{\"type\": \"Point\", \"coordinates\": [lon, lat, alt?]}``
    """
    if raw is None:
        return None, None
    if isinstance(raw, dict):
        coords = raw.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                lon = float(coords[0])
                lat = float(coords[1])
                if abs(lat) > 90 or abs(lon) > 180:
                    return None, None
                return lat, lon
            except (TypeError, ValueError):
                return None, None
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    parts = text.replace(",", " ").split()
    if len(parts) < 2:
        return None, None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
        if abs(lat) > 90 or abs(lon) > 180:
            return None, None
        return lat, lon
    except ValueError:
        return None, None


def _is_geojson_point(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("type") or "").lower() != "point":
        return False
    coords = value.get("coordinates")
    return isinstance(coords, (list, tuple)) and len(coords) >= 2


def humanize_label(name: str) -> str:
    text = re.sub(r"[_\-]+", " ", name or "").strip()
    if not text:
        return "Field"
    return text[:1].upper() + text[1:]


def _is_date_name(name: str) -> bool:
    return bool(re.search(r"date|time", name, re.I))


def _is_geo_name(name: str) -> bool:
    return bool(re.search(r"coord|geopoint|gps|location|lat|lon", name, re.I))


def _looks_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if value is None or value == "":
        return False
    try:
        float(str(value).strip().replace(",", ""))
        return True
    except ValueError:
        return False


def _looks_date(value: Any) -> bool:
    if value is None or value == "":
        return False
    text = str(value).strip()
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", text))


def infer_columns(raw_rows: list[dict]) -> list[dict]:
    """Infer column metadata from OData submission rows."""
    keys: list[str] = []
    seen: set[str] = set()
    for row in raw_rows:
        for key in row.keys():
            if key.startswith("@") or key.startswith("__"):
                continue
            lower = key.lower()
            if lower in META_SKIP or lower in {"lat", "lon"}:
                continue
            value = row.get(key)
            if isinstance(value, dict) and not _is_geojson_point(value):
                continue
            if key not in seen:
                seen.add(key)
                keys.append(key)

    columns: list[dict] = []
    for key in keys:
        samples = [row.get(key) for row in raw_rows if row.get(key) not in (None, "")]
        sample = samples[0] if samples else None
        if key in {"observation_date"} or (_is_date_name(key) and (_looks_date(sample) or not samples)):
            col_type = "date"
        elif (
            key in {"coordinates"}
            or _is_geojson_point(sample)
            or (
                _is_geo_name(key)
                and isinstance(sample, str)
                and len(str(sample).split()) >= 2
            )
        ):
            col_type = "geopoint"
        elif samples and sum(1 for s in samples[:40] if _looks_number(s)) >= max(1, int(0.6 * min(40, len(samples)))):
            col_type = "number"
        else:
            col_type = "text"
        columns.append({"name": key, "label": humanize_label(key), "type": col_type})
    return columns


def normalize_submissions(odata_rows: list[dict]) -> dict[str, Any]:
    """Return { columns, rows } with lat/lon extracted from geopoints."""
    cleaned: list[dict] = []
    for raw in odata_rows:
        if not isinstance(raw, dict):
            continue
        row: dict[str, Any] = {}
        instance_id = raw.get("__id") or raw.get("instanceId") or raw.get("instanceID")
        if isinstance(raw.get("__system"), dict):
            instance_id = instance_id or raw["__system"].get("submissionID")
            row["_submittedAt"] = raw["__system"].get("submissionDate")
        row["instanceId"] = instance_id
        for key, value in raw.items():
            if key.startswith("@") or key.startswith("__"):
                continue
            if isinstance(value, dict):
                if key.lower() == "meta":
                    continue
                if _is_geojson_point(value):
                    row[key] = value
                continue
            row[key] = value
        cleaned.append(row)

    columns = infer_columns(cleaned)
    geo_cols = [c["name"] for c in columns if c["type"] == "geopoint"]
    geo_name = "coordinates" if "coordinates" in geo_cols else (geo_cols[0] if geo_cols else None)

    rows: list[dict] = []
    for row in cleaned:
        out = dict(row)
        lat = lon = None
        if geo_name:
            lat, lon = parse_geopoint(row.get(geo_name))
        # Drop raw geopoint object from row payload (lat/lon are enough for clients)
        if geo_name and geo_name in out and isinstance(out.get(geo_name), dict):
            out[geo_name] = f"{lat} {lon} 0 0" if lat is not None and lon is not None else ""
        out["lat"] = lat
        out["lon"] = lon
        for col in columns:
            if col["type"] != "number":
                continue
            val = out.get(col["name"])
            if val in (None, ""):
                continue
            try:
                out[col["name"]] = float(str(val).strip().replace(",", ""))
            except ValueError:
                pass
        rows.append(out)

    return {"columns": columns, "rows": rows, "count": len(rows)}
