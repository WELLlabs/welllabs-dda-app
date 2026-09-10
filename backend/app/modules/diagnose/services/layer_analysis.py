"""Watershed-clipped per-layer analysis (mirrors clinton_code.py stats blocks)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import numpy as np
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

from app.modules.diagnose.services.layer_catalog import LayerConfig

WISER_RANK_ORDER = ["Very low", "Low", "Moderate", "High", "Very high", "NA"]

WISER_GW_NORMALIZE = {
    "safe": "Safe",
    "semi-critical": "Semi-critical",
    "semicritical": "Semi-critical",
    "semi critical": "Semi-critical",
    "critical": "Critical",
    "over-exploited": "Over-exploited",
    "overexploited": "Over-exploited",
    "over exploited": "Over-exploited",
    "oe": "Over-exploited",
    "saline": "Saline",
}

WISER_RANK_NORMALIZE = {
    "very low": "Very low",
    "verylow": "Very low",
    "low": "Low",
    "moderate": "Moderate",
    "medium": "Moderate",
    "high": "High",
    "very high": "Very high",
    "veryhigh": "Very high",
    "na": "NA",
    "n/a": "NA",
    "none": "NA",
}


@dataclass
class AnalysisResult:
    stats: dict[str, str]
    status: str = "ok"
    error: str | None = None


def _normalize_gw(value: Any) -> str:
    if value is None:
        return "Groundwater class unavailable"
    key = str(value).strip().lower()
    return WISER_GW_NORMALIZE.get(key, str(value).strip() or "Groundwater class unavailable")


def _normalize_rank(value: Any) -> str:
    if value is None:
        return "NA"
    key = str(value).strip().lower()
    return WISER_RANK_NORMALIZE.get(key, str(value).strip() or "NA")


def _length_m(geom) -> float:
    """Approximate geodesic length in metres (EPSG:6933)."""
    try:
        import pyproj

        project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
        return float(shp_transform(project, geom).length)
    except Exception:
        return float(geom.length) * 111_320.0


def normalize_soil_label(value: Any) -> str | None:
    if value is None:
        return None
    soil_key = str(value).strip().lower()
    if soil_key.endswith(".0"):
        soil_key = soil_key[:-2]
    if soil_key in {"1", "01"} or "fine" in soil_key or "clay" in soil_key:
        return "Fine/Clay texture"
    if soil_key in {"2", "02"} or "medium" in soil_key or "loam" in soil_key:
        return "Medium/Loam texture"
    if soil_key in {"3", "03"} or "coarse" in soil_key or "sand" in soil_key:
        return "Coarse/Sandy texture"
    if soil_key in {"4", "04"} or "rock" in soil_key or "non soil" in soil_key or "non-soil" in soil_key:
        return "Rocky and non soil"
    if soil_key in {"unknown", "nan", "none", ""}:
        return None
    return str(value).strip().title()


def wiser_rank_source_columns(style_column: str | None) -> tuple[str, ...]:
    """Map each WISER rank style_column to its village_resilience.fgb source field(s)."""
    if style_column == "__wiser_irrigation_access_class":
        return ("Irr_access",)
    if style_column == "__wiser_kharif_resilience_class":
        return ("Kharif_res",)
    if style_column == "__wiser_rabi_resilience_class":
        return ("Rabi_res",)
    return ("Irr_access", "Kharif_res", "Rabi_res")


def enrich_vector_gdf(gdf, layer_cfg: LayerConfig):
    """Derive style columns (soil texture, literacy) on clipped GeoDataFrame."""
    if gdf.empty:
        return gdf
    gdf = gdf.copy()
    column = layer_cfg.style_column
    atype = layer_cfg.analysis_type or ""

    if atype == "vector_soil" or column == "__soil_texture_class":
        col = _find_column(
            gdf,
            column or "__soil_texture_class",
            "Texture",
            search_terms=("texture", "soil", "type", "class", "desc", "grid", "code"),
        )
        if col:
            gdf[column or "__soil_texture_class"] = gdf[col].apply(normalize_soil_label)
    elif atype == "demographics_literacy" or column == "pct_literate":
        target = column or "pct_literate"
        if target not in gdf.columns or gdf[target].isna().all():
            literate = _find_column(gdf, "Total_Lite", "total_lite", "Total_Liter")
            pop = _find_column(gdf, "Total_Popu", "total_popu", "Population")
            if literate and pop:
                pop_v = gdf[pop].replace(0, np.nan)
                gdf[target] = (gdf[literate].fillna(0) / pop_v) * 100
    elif atype == "wiser_gw_stress" and column:
        col = _find_column(gdf, column, "category", search_terms=("category", "gw", "stress", "stage"))
        if col and column not in gdf.columns:
            gdf[column] = gdf[col].apply(_normalize_gw)
        elif column in gdf.columns:
            gdf[column] = gdf[column].apply(_normalize_gw)
    elif atype == "wiser_rank" and column:
        # Each WISER rank layer maps a different source field from village_resilience.fgb.
        # Never fall through Irr_access → Kharif/Rabi or all three choropleths look identical.
        col = _find_column(gdf, *wiser_rank_source_columns(column))
        if col:
            gdf[column] = gdf[col].apply(_normalize_rank)
    elif atype == "demographics_marginalized" or column == "pct_scst":
        target = column or "pct_scst"
        if target not in gdf.columns or gdf[target].isna().all():
            sc = _find_column(gdf, "Total_SC_P", "total_sc_p")
            st = _find_column(gdf, "Total_ST_P", "total_st_p")
            pop = _find_column(gdf, "Total_Popu", "total_popu", "Population")
            if sc and st and pop:
                pop_v = gdf[pop].replace(0, np.nan)
                gdf[target] = ((gdf[sc].fillna(0) + gdf[st].fillna(0)) / pop_v) * 100

    return gdf


def _clip_lines_to_watershed(gdf, watershed_geom: dict):
    import geopandas as gpd
    from shapely.geometry import GeometryCollection, LineString, MultiLineString

    ws = shape(watershed_geom)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    gdf = gdf[gdf.geometry.intersects(ws)].copy()
    gdf.geometry = gdf.geometry.intersection(ws)
    gdf = gdf[~gdf.geometry.is_empty]

    rows = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if isinstance(geom, (LineString, MultiLineString)):
            rows.append(row)
        elif isinstance(geom, GeometryCollection):
            lines = [g for g in geom.geoms if isinstance(g, (LineString, MultiLineString))]
            if lines:
                new_row = row.copy()
                new_row.geometry = MultiLineString(lines) if len(lines) > 1 else lines[0]
                rows.append(new_row)
    if not rows:
        return gpd.GeoDataFrame(columns=gdf.columns, crs=gdf.crs)
    out = gpd.GeoDataFrame(rows, crs=gdf.crs)
    out["calc_length"] = out.geometry.apply(_length_m)
    return out


def _filter_intersecting_watershed(gdf, watershed_geom: dict):
    """Keep full feature geometries that touch the watershed (no cut)."""
    import geopandas as gpd

    ws = shape(watershed_geom)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    out = gdf[gdf.geometry.intersects(ws)].copy()
    out = out[~out.geometry.is_empty]
    if out.empty:
        return gpd.GeoDataFrame(columns=gdf.columns, crs=gdf.crs)
    return out


def _clip_vector_to_watershed(gdf, watershed_geom: dict, layer_cfg: LayerConfig | None = None):
    geometry_kind = "polygon"
    if layer_cfg:
        geometry_kind = layer_cfg.geometry_kind or (
            "line" if layer_cfg.render_type == "line" else "polygon"
        )
    if layer_cfg and (layer_cfg.clip_mode or "").lower() == "intersect":
        return _filter_intersecting_watershed(gdf, watershed_geom)
    if geometry_kind == "line" or (layer_cfg and layer_cfg.render_type == "line"):
        return _clip_lines_to_watershed(gdf, watershed_geom)
    return _clip_to_watershed(gdf, watershed_geom)


def _area_m2(geom) -> float:
    """Approximate geodesic area via equal-area projection (EPSG:6933)."""
    try:
        import pyproj

        project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
        return float(shp_transform(project, geom).area)
    except Exception:
        return float(geom.area)


_FGB_CACHE_DIR = Path(tempfile.gettempdir()) / "dda_vector_fgb_cache"
# Full-file local cache for mid-size GPKGs (Sub Basins ~77MB). Skip huge national files.
_LOCAL_VECTOR_CACHE_MAX_BYTES = 120 * 1024 * 1024
# Hierarchy/preview GPKGs (esp. rivers) are cold-path bottlenecks on vsis3 — cache larger.
_HIERARCHY_LOCAL_CACHE_MAX_BYTES = 450 * 1024 * 1024
_HIERARCHY_LOCAL_CACHE_KEYS = frozenset(
    {
        "vector/india_rivers_level_12.fgb",
        "vector/Basin.fgb",
        "vector/Sub Basins of india.fgb",
        "vector/india_basins_level_7.fgb",
        # Legacy GPKG keys (kept until all hosts/envs use FGB).
        "vector/india_rivers_level_12.gpkg",
        "vector/Basin.gpkg",
        "vector/Sub Basins of india.gpkg",
        "vector/india_basins_level_7.gpkg",
    }
)
# FGB hierarchy files need local cache too — vsis3 cold reads still hurt first project open.
_LOCAL_VECTOR_SUFFIXES = {".gpkg", ".fgb"}
_vector_cache_locks: dict[str, Any] = {}
_vector_cache_guard = None


def _download_bytes(url: str) -> bytes:
    with urlopen(url, timeout=300) as resp:  # noqa: S310 — URL is our own S3 presign
        return resp.read()


def _watershed_bbox(
    watershed_geom: dict, *, pad_frac: float = 0.05
) -> tuple[float, float, float, float]:
    ws = shape(watershed_geom)
    minx, miny, maxx, maxy = ws.bounds
    pad = max((maxx - minx), (maxy - miny), 0.01) * pad_frac
    return (minx - pad, miny - pad, maxx + pad, maxy + pad)


def _vsis3_path(s3_key: str) -> str:
    from app.shared.config import settings

    return f"/vsis3/{settings.aws_s3_bucket}/{s3_key.lstrip('/')}"


def _cache_lock_for(s3_key: str):
    import threading

    global _vector_cache_guard
    if _vector_cache_guard is None:
        _vector_cache_guard = threading.Lock()
    with _vector_cache_guard:
        lock = _vector_cache_locks.get(s3_key)
        if lock is None:
            lock = threading.Lock()
            _vector_cache_locks[s3_key] = lock
        return lock


def _ensure_local_vector_cache(s3_key: str) -> Path | None:
    """Download mid-size GPKG/FGB once for fast local bbox reads; None → use /vsis3/."""
    suffix = Path(s3_key).suffix.lower()
    if suffix not in _LOCAL_VECTOR_SUFFIXES:
        return None

    from app.shared.config import settings

    try:
        import boto3
    except ImportError:
        return None

    safe = s3_key.replace("/", "_").replace("..", "_")
    path = _FGB_CACHE_DIR / safe
    with _cache_lock_for(s3_key):
        try:
            client = boto3.client("s3")
            head = client.head_object(Bucket=settings.aws_s3_bucket, Key=s3_key.lstrip("/"))
            size = int(head.get("ContentLength") or 0)
        except Exception:
            return None
        max_bytes = (
            _HIERARCHY_LOCAL_CACHE_MAX_BYTES
            if s3_key.lstrip("/") in _HIERARCHY_LOCAL_CACHE_KEYS
            or s3_key in _HIERARCHY_LOCAL_CACHE_KEYS
            else _LOCAL_VECTOR_CACHE_MAX_BYTES
        )
        if size <= 0 or size > max_bytes:
            return None
        if path.exists() and path.stat().st_size == size:
            return path
        _FGB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            client.download_file(settings.aws_s3_bucket, s3_key.lstrip("/"), str(tmp))
            tmp.replace(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            return None
        if path.exists() and path.stat().st_size > 0:
            return path
        return None


def warm_hierarchy_vector_caches() -> None:
    """Best-effort download of basin/rivers FGBs so first preview isn't the cold miss."""
    for key in _HIERARCHY_LOCAL_CACHE_KEYS:
        try:
            _ensure_local_vector_cache(key)
        except Exception:
            continue


def _read_vector_gdf_bbox(s3_key: str, bbox: tuple[float, float, float, float]):
    """Read only features intersecting bbox.

    Mid-size GPKG/FGB hierarchy files are cached locally (vsis3 range reads on
    GPKG are very slow; FGB is better but still benefits from a warm local copy).
    Large national FGBs stay on /vsis3/ HTTP range requests when over the size cap.
    """
    import geopandas as gpd

    local = _ensure_local_vector_cache(s3_key)
    path = str(local) if local is not None else _vsis3_path(s3_key)
    return gpd.read_file(path, bbox=bbox)


def cached_fgb_path(s3_key: str, url: str) -> Path:
    """Legacy full-file cache — prefer _read_vector_gdf_bbox for large FGBs."""
    _FGB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = s3_key.replace("/", "_").replace("..", "_")
    path = _FGB_CACHE_DIR / safe
    if path.exists() and path.stat().st_size > 0:
        return path
    data = _download_bytes(url)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def _read_vector_gdf(url: str, *, bbox: tuple[float, float, float, float] | None = None):
    import geopandas as gpd

    data = _download_bytes(url)
    with tempfile.NamedTemporaryFile(suffix=".fgb", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        if bbox is not None:
            return gpd.read_file(tmp_path, bbox=bbox)
        return gpd.read_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _read_vector_gdf_from_path(
    path: Path, *, bbox: tuple[float, float, float, float] | None = None
):
    import geopandas as gpd

    if bbox is not None:
        return gpd.read_file(path, bbox=bbox)
    return gpd.read_file(path)


def _to_polygons(gdf):
    """Ensure GeoDataFrame contains only (Multi)Polygon geometries."""
    import geopandas as gpd
    from shapely.geometry import (
        MultiPolygon,
        Polygon,
        GeometryCollection,
    )

    # Explode multi-part first
    gdf = gdf.explode(index_parts=False)
    # Keep only polygon types; extract polygons from geometry collections
    rows = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if isinstance(geom, (Polygon, MultiPolygon)):
            rows.append(row)
        elif isinstance(geom, GeometryCollection):
            polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
            if polys:
                new_row = row.copy()
                new_row.geometry = MultiPolygon(polys) if len(polys) > 1 else polys[0]
                rows.append(new_row)
    if not rows:
        return gpd.GeoDataFrame(columns=gdf.columns, crs=gdf.crs)
    return gpd.GeoDataFrame(rows, crs=gdf.crs)


def _clip_to_watershed(gdf, watershed_geom: dict):
    import geopandas as gpd

    ws = shape(watershed_geom)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    # Normalise to polygon-only before overlay to avoid mixed-type errors
    gdf = _to_polygons(gdf)
    if gdf.empty:
        return gdf

    ws_gdf = gpd.GeoDataFrame(geometry=[ws], crs="EPSG:4326")
    clipped = gpd.overlay(gdf, ws_gdf, how="intersection", keep_geom_type=True)
    if clipped.empty:
        return clipped
    clipped = clipped.copy()
    clipped["calc_area"] = clipped.geometry.apply(_area_m2)
    return clipped


def _clip_mode_signature(layer_cfg: LayerConfig | None) -> tuple[str, str]:
    """Clip behaviour that must match for raw-clip reuse across sibling layers."""
    if layer_cfg is None:
        return ("polygon", "")
    geometry_kind = layer_cfg.geometry_kind or (
        "line" if layer_cfg.render_type == "line" else "polygon"
    )
    clip_mode = (layer_cfg.clip_mode or "").lower()
    return (str(geometry_kind), clip_mode)


_RAW_CLIP_MEM: dict[tuple, Any] = {}
_CLIP_MEM: dict[tuple, dict] = {}


def clipped_vector_gdf_for_watershed(
    s3_key: str,
    watershed_geom: dict,
    layer_cfg: LayerConfig | None = None,
    *,
    pad_frac: float = 0.05,
):
    """Watershed-clipped GeoDataFrame memoized by (s3_key, geom, clip mode).

    Sibling catalog layers that share one FGB (WISER trio, village demographics)
    reuse the expensive S3 bbox read + spatial clip; only enrich/analyze diverge.
    """
    cache_key = (
        s3_key,
        json.dumps(watershed_geom, sort_keys=True),
        round(float(pad_frac), 4),
        _clip_mode_signature(layer_cfg),
    )
    cached = _RAW_CLIP_MEM.get(cache_key)
    if cached is not None:
        return cached.copy()

    bbox = _watershed_bbox(watershed_geom, pad_frac=pad_frac)
    gdf = _read_vector_gdf_bbox(s3_key, bbox)
    clipped = _clip_vector_to_watershed(gdf, watershed_geom, layer_cfg)
    if len(_RAW_CLIP_MEM) > 48:
        _RAW_CLIP_MEM.clear()
    _RAW_CLIP_MEM[cache_key] = clipped
    return clipped.copy()


def clip_vector_geojson(
    s3_key: str,
    vector_url: str,
    watershed_geom: dict,
    *,
    layer_cfg: LayerConfig | None = None,
    pad_frac: float = 0.05,
) -> dict:
    """Return watershed-clipped GeoJSON FeatureCollection for map rendering.

    Reads only the watershed bbox from S3 via /vsis3/ range requests — never the
    full national FGB. Shares the raw clip with analysis via
    clipped_vector_gdf_for_watershed.
    """
    del vector_url  # unused; vsis3 uses IAM/env credentials
    clipped = clipped_vector_gdf_for_watershed(
        s3_key, watershed_geom, layer_cfg, pad_frac=pad_frac
    )
    if clipped.empty:
        return {"type": "FeatureCollection", "features": []}
    if layer_cfg:
        clipped = enrich_vector_gdf(clipped, layer_cfg)
    drop_cols = [c for c in ("calc_area", "calc_length") if c in clipped.columns]
    if drop_cols:
        clipped = clipped.drop(columns=drop_cols)
    return json.loads(clipped.to_json())


def clipped_vector_geojson_for_watershed(
    s3_key: str,
    vector_url: str,
    watershed_geom: dict,
    layer_cfg: LayerConfig | None = None,
    *,
    pad_frac: float = 0.05,
) -> dict:
    """Clip with in-process memo — shared by map vector data, preview, and hierarchy."""
    cache_key = (
        s3_key,
        json.dumps(watershed_geom, sort_keys=True),
        getattr(layer_cfg, "id", None) or "",
        round(float(pad_frac), 4),
    )
    cached = _CLIP_MEM.get(cache_key)
    if cached is not None:
        return cached
    result = clip_vector_geojson(
        s3_key, vector_url, watershed_geom, layer_cfg=layer_cfg, pad_frac=pad_frac
    )
    if len(_CLIP_MEM) > 96:
        _CLIP_MEM.clear()
    _CLIP_MEM[cache_key] = result
    return result


def _find_column(gdf, *candidates: str, search_terms: tuple[str, ...] = ()) -> str | None:
    cols = {c.lower(): c for c in gdf.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    if search_terms:
        for col in gdf.columns:
            low = col.lower()
            if any(term in low for term in search_terms):
                return col
    return None


def analyze_wiser_gw_stress(clipped) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    total = float(clipped["calc_area"].sum()) or 1.0
    col = _find_column(
        clipped,
        "__wiser_gw_stress_class",
        "category",
        search_terms=("category", "gw", "groundwater", "stress", "stage", "extraction", "status"),
    )
    if not col:
        return {"Data Warning": "WISER groundwater stress category field was not found."}
    labels = clipped[col].apply(_normalize_gw)
    clipped = clipped.assign(__class=labels)
    areas = clipped.groupby("__class")["calc_area"].sum()
    dominant_label, dominant_area = None, 0.0
    for label, area in areas.items():
        pct = (area / total) * 100
        if area > dominant_area:
            dominant_label, dominant_area = label, float(area)
        if pct >= 0.1:
            stats[f"{label} area"] = f"{pct:.1f}%"
    if dominant_label:
        stats["Dominant class"] = str(dominant_label)
    stats["Count"] = str(len(clipped))
    return stats


def analyze_wiser_rank(clipped, style_column: str | None = None) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    total = float(clipped["calc_area"].sum()) or 1.0
    candidates = [
        style_column or "",
        *wiser_rank_source_columns(style_column),
    ]
    col = _find_column(clipped, *[c for c in candidates if c])
    if not col:
        return {"Data Warning": "WISER class field was not found."}
    labels = clipped[col].apply(_normalize_rank)
    clipped = clipped.assign(__class=labels)
    areas = clipped.groupby("__class")["calc_area"].sum()
    ordered = [lbl for lbl in WISER_RANK_ORDER if lbl in areas.index]
    ordered.extend(sorted(set(areas.index) - set(ordered)))
    dominant_label, dominant_area = None, 0.0
    for label in ordered:
        area = float(areas.loc[label])
        pct = (area / total) * 100
        if area > dominant_area:
            dominant_label, dominant_area = label, area
        if pct >= 0.1:
            stats[f"{label} area"] = f"{pct:.1f}%"
    if dominant_label:
        stats["Dominant class"] = str(dominant_label)

    village_col = _find_column(clipped, "vlcode", "Village ID", "village")
    if village_col:
        stats["Villages represented"] = str(clipped[village_col].nunique())

    mean_ci_col = _find_column(clipped, "MeanCI", "mean_ci")
    if mean_ci_col:
        try:
            import pandas as pd

            stats["Mean cropping intensity"] = f"{float(pd.to_numeric(clipped[mean_ci_col], errors='coerce').mean()):.2f}"
        except Exception:
            pass

    for dev_cand in ("avg_kharif_dev", "avg_rabi_dev"):
        if dev_cand in clipped.columns:
            try:
                import pandas as pd

                stats["Average crop-area reduction"] = (
                    f"{float(pd.to_numeric(clipped[dev_cand], errors='coerce').mean()):.1f}%"
                )
            except Exception:
                pass
            break

    stats["Count"] = str(len(clipped))
    return stats


def analyze_aquifers(clipped) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    total = float(clipped["calc_area"].sum()) or 1.0
    aq_col = _find_column(clipped, "aquifer", "Major_Aqui", "aquifers")
    if not aq_col:
        return {"Data Warning": "Aquifer column was not found."}
    areas = clipped.groupby(aq_col)["calc_area"].sum()
    dom_aq = areas.idxmax()
    for aq, area in areas.items():
        pct = (float(area) / total) * 100
        if pct > 1:
            stats[f"{aq} Area"] = f"{pct:.1f}%"
    dom_row = clipped[clipped[aq_col] == dom_aq].iloc[0]
    stats["Dominant Aquifer"] = str(dom_aq)
    for label, cand in (
        ("Major Material", "Major_Aqui"),
        ("Confinement", "aquifers"),
        ("Depth (mbgl)", "avg_mbgl"),
        ("Yield Potential", "yeild__"),
        ("Discharge (m3/day)", "m3_per_day"),
    ):
        col = _find_column(clipped, cand)
        if col and col in dom_row.index and str(dom_row[col]) not in ("", "nan", "None"):
            stats[label] = str(dom_row[col])
    stats["Count"] = str(len(clipped))
    return stats


def analyze_demographics(clipped, marginalized: bool = False) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    id_col = _find_column(clipped, "Village ID", "vlcode", "village")
    unique = clipped.drop_duplicates(subset=[id_col]) if id_col else clipped
    stats["Intersecting Villages"] = str(len(unique))

    pop_col = _find_column(unique, "Total_Popu", "total_popu", "Population")
    sc_col = _find_column(unique, "Total_SC_P", "total_sc_p")
    st_col = _find_column(unique, "Total_ST_P", "total_st_p")
    try:
        total_pop = float(unique[pop_col].sum()) if pop_col else 0.0
        stats["Population in AOI"] = f"{int(total_pop):,}"
        if total_pop > 0 and sc_col and st_col:
            sc_pop = float(unique[sc_col].sum())
            st_pop = float(unique[st_col].sum())
            scst_pct = ((sc_pop + st_pop) / total_pop) * 100
            stats["SC/ST Community"] = f"{int(sc_pop + st_pop):,} ({scst_pct:.1f}%)"
            if marginalized:
                stats["Mean % SC/ST"] = f"{scst_pct:.1f}%"
    except Exception as exc:
        stats["Data Warning"] = f"Could not aggregate demographics: {exc}"
    return stats


def analyze_demographics_literacy(clipped) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    id_col = _find_column(clipped, "Village ID", "vlcode", "village")
    unique = clipped.drop_duplicates(subset=[id_col]) if id_col else clipped
    stats["Intersecting Villages"] = str(len(unique))
    literate_col = _find_column(unique, "pct_literate")
    if not literate_col:
        literate = _find_column(unique, "Total_Lite", "total_lite")
        pop = _find_column(unique, "Total_Popu", "total_popu", "Population")
        if literate and pop:
            pop_v = unique[pop].replace(0, np.nan)
            unique = unique.assign(pct_literate=(unique[literate].fillna(0) / pop_v) * 100)
            literate_col = "pct_literate"
    if literate_col:
        try:
            import pandas as pd

            vals = pd.to_numeric(unique[literate_col], errors="coerce")
            stats["Mean literacy (%)"] = f"{float(vals.mean()):.1f}"
            stats["Min literacy (%)"] = f"{float(vals.min()):.1f}"
            stats["Max literacy (%)"] = f"{float(vals.max()):.1f}"
        except Exception as exc:
            stats["Data Warning"] = f"Could not aggregate literacy: {exc}"
    else:
        stats["Data Warning"] = "Literacy field was not found."
    return stats


def analyze_vector_length(clipped) -> dict[str, str]:
    if clipped.empty:
        return {"Status": "No features in watershed"}
    if "calc_length" not in clipped.columns:
        clipped = clipped.copy()
        clipped["calc_length"] = clipped.geometry.apply(_length_m)
    total_m = float(clipped["calc_length"].sum())
    return {
        "Total length (km)": f"{total_m / 1000:.1f}",
        "Segment count": str(len(clipped)),
    }


def analyze_vector_categorical(clipped, style_column: str | None = None) -> dict[str, str]:
    stats: dict[str, str] = {}
    if clipped.empty:
        return {"Status": "No features in watershed"}
    col = style_column or _find_column(clipped, search_terms=("class", "type", "category"))
    if not col:
        return {"Count": str(len(clipped))}
    if "calc_length" in clipped.columns and clipped["calc_length"].sum() > 0:
        total = float(clipped["calc_length"].sum()) or 1.0
        grouped = clipped.groupby(col)["calc_length"].sum()
        metric = "length"
    elif "calc_area" in clipped.columns and clipped["calc_area"].sum() > 0:
        total = float(clipped["calc_area"].sum()) or 1.0
        grouped = clipped.groupby(col)["calc_area"].sum()
        metric = "area"
    else:
        grouped = clipped[col].value_counts()
        total = float(grouped.sum()) or 1.0
        metric = "count"
    dominant_label, dominant_val = None, 0.0
    for label, val in grouped.items():
        pct = (float(val) / total) * 100
        if float(val) > dominant_val:
            dominant_label, dominant_val = label, float(val)
        if pct >= 0.1:
            suffix = "%" if metric != "count" else ""
            stats[f"{label} {metric}"] = f"{pct:.1f}{suffix}" if suffix else str(int(val))
    if dominant_label is not None:
        stats["Dominant class"] = str(dominant_label)
    stats["Count"] = str(len(clipped))
    return stats


def analyze_continuous_raster(
    cog_url: str, watershed_geom: dict, nodata: float | int | None = None
) -> dict[str, str]:
    """Sample continuous raster values inside the watershed bbox."""
    try:
        from rio_tiler.io import Reader

        ws = shape(watershed_geom)
        minx, miny, maxx, maxy = ws.bounds
        with Reader(cog_url) as src:
            img = src.part([minx, miny, maxx, maxy], indexes=[1], max_size=512)
        arr = img.array[0].astype(float)
        if nodata is not None:
            arr = np.where(arr == nodata, np.nan, arr)
        if img.alpha_mask is not None:
            arr = np.where(img.alpha_mask > 0, arr, np.nan)
        valid = arr[~np.isnan(arr)]
        if valid.size == 0:
            return {"Status": "No valid raster pixels in watershed"}
        return {
            "Min": f"{float(np.nanmin(valid)):.2f}",
            "Max": f"{float(np.nanmax(valid)):.2f}",
            "Mean": f"{float(np.nanmean(valid)):.2f}",
            "Median": f"{float(np.nanmedian(valid)):.2f}",
        }
    except Exception as exc:
        return {"Status": f"Continuous raster analysis error: {exc}"}


def analyze_dem(cog_url: str, watershed_geom: dict, nodata: float | int | None = -9999) -> dict[str, str]:
    """Read only the watershed bbox from the COG via HTTP range reads (no full download)."""
    try:
        from rio_tiler.io import Reader
        import rasterio
        from rasterio.warp import transform_geom

        ws = shape(watershed_geom)
        minx, miny, maxx, maxy = ws.bounds

        with Reader(cog_url) as src:
            # part() reads only the bbox window using COG range requests — fast even for 3.5 GB.
            img = src.part([minx, miny, maxx, maxy], indexes=[1], max_size=512)

        arr = img.array[0].astype(float)
        nd = nodata
        if nd is not None:
            arr = np.where(arr == nd, np.nan, arr)
        # Also mask the alpha channel if present
        if img.alpha_mask is not None:
            arr = np.where(img.alpha_mask > 0, arr, np.nan)
        valid = arr[~np.isnan(arr)]
        if valid.size == 0:
            return {"Status": "No valid DEM pixels in watershed"}
        elev_min = float(np.nanmin(valid))
        elev_max = float(np.nanmax(valid))
        return {
            "Elevation min (m)": f"{elev_min:.1f}",
            "Elevation max (m)": f"{elev_max:.1f}",
            "Relief (m)": f"{elev_max - elev_min:.1f}",
            "Mean elevation (m)": f"{float(np.nanmean(valid)):.1f}",
        }
    except Exception as exc:
        return {"Status": f"DEM analysis error: {exc}"}


def analyze_jrc_occurrence(cog_url: str, watershed_geom: dict) -> dict[str, str]:
    """Analyze JRC Surface Water Occurrence (0-100% + 255=nodata)."""
    try:
        from rio_tiler.io import Reader
        ws = shape(watershed_geom)
        minx, miny, maxx, maxy = ws.bounds

        with Reader(cog_url) as src:
            img = src.part([minx, miny, maxx, maxy], indexes=[1], max_size=512)

        arr = img.array[0]
        if img.alpha_mask is not None:
            valid_mask = (img.alpha_mask > 0) & (arr != 255)
        else:
            valid_mask = arr != 255

        valid = arr[valid_mask]
        if valid.size == 0:
            return {"Status": "No valid water occurrence data in watershed"}

        # Categorize by occurrence percentage
        rare = np.sum((valid >= 1) & (valid <= 20))
        low = np.sum((valid >= 21) & (valid <= 40))
        intermittent = np.sum((valid >= 41) & (valid <= 60))
        frequent = np.sum((valid >= 61) & (valid <= 80))
        very_frequent = np.sum((valid >= 81) & (valid <= 99))
        permanent = np.sum(valid == 100)
        
        total_water = rare + low + intermittent + frequent + very_frequent + permanent
        if total_water == 0:
            return {"Status": "No water pixels detected in watershed"}

        return {
            "Rare (1-20%)": f"{rare / total_water * 100:.1f}%",
            "Low (21-40%)": f"{low / total_water * 100:.1f}%",
            "Intermittent (41-60%)": f"{intermittent / total_water * 100:.1f}%",
            "Frequent (61-80%)": f"{frequent / total_water * 100:.1f}%",
            "Very frequent (81-99%)": f"{very_frequent / total_water * 100:.1f}%",
            "Permanent (100%)": f"{permanent / total_water * 100:.1f}%",
        }
    except Exception as exc:
        return {"Status": f"JRC occurrence analysis error: {exc}"}


def analyze_jrc_transitions(cog_url: str, watershed_geom: dict) -> dict[str, str]:
    """Analyze JRC Surface Water Transitions (0-10 + 255=nodata)."""
    try:
        from rio_tiler.io import Reader
        ws = shape(watershed_geom)
        minx, miny, maxx, maxy = ws.bounds

        with Reader(cog_url) as src:
            img = src.part([minx, miny, maxx, maxy], indexes=[1], max_size=512)

        arr = img.array[0]
        if img.alpha_mask is not None:
            valid_mask = (img.alpha_mask > 0) & (arr != 255)
        else:
            valid_mask = arr != 255

        valid = arr[valid_mask]
        if valid.size == 0:
            return {"Status": "No valid transition data in watershed"}

        # Count each transition class
        transitions = {
            1: "Permanent",
            2: "New permanent",
            3: "Lost permanent",
            4: "Seasonal",
            5: "New seasonal",
            6: "Lost seasonal",
            7: "Seasonal→permanent",
            8: "Permanent→seasonal",
            9: "Ephemeral permanent",
            10: "Ephemeral seasonal",
        }

        total_water = np.sum((valid >= 1) & (valid <= 10))
        if total_water == 0:
            return {"Status": "No water transition pixels in watershed"}

        result = {}
        for value, label in transitions.items():
            count = np.sum(valid == value)
            if count > 0:
                result[label] = f"{count / total_water * 100:.1f}%"

        return result
    except Exception as exc:
        return {"Status": f"JRC transitions analysis error: {exc}"}


def analyze_layer(
    layer_cfg: LayerConfig,
    watershed_geom: dict,
    *,
    vector_url: str | None = None,
    cog_url: str | None = None,
) -> AnalysisResult:
    """Compute watershed-clipped stats for a catalog layer."""
    try:
        atype = layer_cfg.analysis_type or ""
        if atype == "dem":
            if not cog_url:
                return AnalysisResult(stats={}, status="error", error="Missing COG URL for DEM analysis")
            stats = analyze_dem(cog_url, watershed_geom, nodata=layer_cfg.nodata)
            return AnalysisResult(stats=stats)
        
        if atype == "jrc_occurrence":
            if not cog_url:
                return AnalysisResult(stats={}, status="error", error="Missing COG URL for JRC occurrence analysis")
            stats = analyze_jrc_occurrence(cog_url, watershed_geom)
            return AnalysisResult(stats=stats)
        
        if atype == "jrc_transitions":
            if not cog_url:
                return AnalysisResult(stats={}, status="error", error="Missing COG URL for JRC transitions analysis")
            stats = analyze_jrc_transitions(cog_url, watershed_geom)
            return AnalysisResult(stats=stats)

        if atype == "continuous_raster":
            if not cog_url:
                return AnalysisResult(stats={}, status="error", error="Missing COG URL for raster analysis")
            stats = analyze_continuous_raster(cog_url, watershed_geom, nodata=layer_cfg.nodata)
            return AnalysisResult(stats=stats)

        if atype == "watershed_hierarchy" or layer_cfg.source == "watershed_hierarchy":
            from app.modules.diagnose.services.preview_context import analyze_watershed_hierarchy

            stats = analyze_watershed_hierarchy(watershed_geom)
            return AnalysisResult(stats=stats)

        if not vector_url and layer_cfg.source == "vector_fgb":
            # Analysis can proceed with vsis3 even without a presigned URL
            vector_url = "vsis3"

        if not vector_url:
            return AnalysisResult(stats={}, status="error", error="Missing vector URL for analysis")

        clipped = clipped_vector_gdf_for_watershed(layer_cfg.s3_key, watershed_geom, layer_cfg)
        if layer_cfg.source == "vector_fgb":
            clipped = enrich_vector_gdf(clipped, layer_cfg)

        if atype == "wiser_gw_stress":
            stats = analyze_wiser_gw_stress(clipped)
        elif atype == "wiser_rank":
            stats = analyze_wiser_rank(clipped, style_column=layer_cfg.style_column)
        elif atype == "aquifers":
            stats = analyze_aquifers(clipped)
        elif atype == "demographics":
            stats = analyze_demographics(clipped, marginalized=False)
        elif atype == "demographics_marginalized":
            stats = analyze_demographics(clipped, marginalized=True)
        elif atype == "demographics_literacy":
            stats = analyze_demographics_literacy(clipped)
        elif atype == "vector_length":
            stats = analyze_vector_length(clipped)
        elif atype == "vector_categorical":
            stats = analyze_vector_categorical(clipped, style_column=layer_cfg.style_column)
        elif atype == "vector_soil":
            stats = analyze_vector_categorical(clipped, style_column=layer_cfg.style_column)
        elif atype == "categorical_area":
            stats = {"Status": "Raster class-area analysis not yet enabled for live sidebar"}
        else:
            stats = {"Count": str(len(clipped))} if not clipped.empty else {"Status": "No features in watershed"}

        return AnalysisResult(stats=stats)
    except Exception as exc:
        return AnalysisResult(stats={}, status="error", error=str(exc))
