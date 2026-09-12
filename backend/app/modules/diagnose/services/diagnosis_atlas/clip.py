"""Clip enabled catalog layers to the project watershed (same calcs as toolbox analysis)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape

from app.modules.diagnose.services.layer_analysis import (
    clipped_vector_gdf_for_watershed,
    enrich_vector_gdf,
)
from app.modules.diagnose.services.layer_catalog import (
    LayerConfig,
    get_catalog,
    resolve_enabled_cog_keys,
    resolve_enabled_vector_keys,
)
from app.modules.diagnose.services.package_progress import PackageProgress

# Layers clipped for the reference atlas (no standalone JRC / literacy pages).
ATLAS_LAYER_ORDER = [
    "dem",
    "drainage",
    "lulc250k",
    "cropping_intensity",
    "irrigation_access_wiser",
    "kharif_resilience_wiser",
    "rabi_resilience_wiser",
    "gw_stress_wiser",
    "aquifers",
    "canals",
    "baseline_population",
    "marginalized_scst",
]

# Paired comparison spreads only (clinton REQUESTED_COMPARISON_PAIRS) — no duplicate standalones.
COMPARISON_PAIRS = [
    ("gw_stress_wiser", "irrigation_access_wiser"),
    ("kharif_resilience_wiser", "rabi_resilience_wiser"),
    ("dem", "lulc250k"),
    ("baseline_population", "marginalized_scst"),
]

# Standalone analytical pages that appear in the reference (paired layers are omitted as singles).
STANDALONE_ATLAS_LAYERS = ("cropping_intensity", "aquifers")
PAIRED_LAYER_IDS = {lid for pair in COMPARISON_PAIRS for lid in pair}


def _enabled_configs() -> list[LayerConfig]:
    enabled_cog = set(resolve_enabled_cog_keys())
    enabled_vec = set(resolve_enabled_vector_keys())
    out: list[LayerConfig] = []
    by_id = {cfg.id: cfg for cfg in get_catalog().layers}
    for lid in ATLAS_LAYER_ORDER:
        cfg = by_id.get(lid)
        if not cfg or not cfg.analysis_type:
            continue
        if cfg.render_type == "outline":
            continue
        if cfg.source == "cog" and cfg.s3_key in enabled_cog:
            out.append(cfg)
        elif cfg.source == "vector_fgb" and cfg.s3_key in enabled_vec:
            out.append(cfg)
    return out


LEVEL7_S3_KEY = "vector/india_basins_level_7.fgb"
_LEVEL7_LOCAL_CANDIDATES = (
    Path(__file__).resolve().parents[6] / ".tmp_hierarchy_fgb" / "india_basins_level_7.fgb",
    Path(__file__).resolve().parents[6] / ".tmp_hierarchy_fgb" / "india_basins_level_7.gpkg",
)

# India state/UT polygons for Location Context (clinton State Boundaries.gpkg).
STATE_BOUNDARIES_S3_KEY = "vector/india_state_boundaries.fgb"
_STATE_NAME_COLS = ("ST_NM", "st_nm", "STATE", "State", "NAME_1", "name", "State_Name", "STATE_NAME")
_STATE_GEOJSON_URL = (
    "https://raw.githubusercontent.com/geohacker/india/master/state/india_telengana.geojson"
)
_STATE_LOCAL_CANDIDATES = (
    Path(__file__).resolve().parent.parent / "data" / "india_state_boundaries.fgb",
    Path("/tmp/india_state_boundaries.fgb"),
    Path(__file__).resolve().parents[6] / ".tmp_hierarchy_fgb" / "india_state_boundaries.fgb",
)
_INDIA_STATES_CACHE = None


def _ensure_wgs84(gdf):
    if gdf is None or getattr(gdf, "empty", True):
        return gdf
    if gdf.crs is None:
        return gdf.set_crs(4326)
    return gdf.to_crs(4326)


def _normalize_state_gdf(gdf):
    """Ensure WGS84 + a single ST_NM column for legends/labels."""
    if gdf is None or getattr(gdf, "empty", True):
        return gdf
    gdf = _ensure_wgs84(gdf)
    if "ST_NM" not in gdf.columns:
        for col in _STATE_NAME_COLS:
            if col in gdf.columns:
                gdf = gdf.rename(columns={col: "ST_NM"})
                break
    keep = [c for c in ("ST_NM", "geometry") if c in gdf.columns]
    return gdf[keep].copy() if keep else gdf


def _download_india_states_fgb(dest: Path):
    """Fetch public India state polygons and cache a slim FlatGeobuf."""
    import urllib.request

    import geopandas as gpd

    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = dest.with_suffix(".geojson")
    req = urllib.request.Request(_STATE_GEOJSON_URL, headers={"User-Agent": "geo-field-pipeline/diagnose-atlas"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw.write_bytes(resp.read())
    gdf = _normalize_state_gdf(gpd.read_file(raw))
    gdf.to_file(dest, driver="FlatGeobuf")
    try:
        raw.unlink(missing_ok=True)
    except Exception:
        pass
    return gdf


def load_india_states():
    """All India state/UT boundaries (cached). Prefer S3, then local, then download."""
    global _INDIA_STATES_CACHE
    if _INDIA_STATES_CACHE is not None and not getattr(_INDIA_STATES_CACHE, "empty", True):
        return _INDIA_STATES_CACHE.copy()

    import geopandas as gpd

    # 1) S3 (optional — may not be uploaded yet)
    try:
        from app.modules.diagnose.services.layer_analysis import _vsis3_path

        gdf = gpd.read_file(_vsis3_path(STATE_BOUNDARIES_S3_KEY))
        gdf = _normalize_state_gdf(gdf)
        if gdf is not None and not gdf.empty:
            _INDIA_STATES_CACHE = gdf
            return gdf.copy()
    except Exception:
        pass

    # 2) Local candidates
    for path in _STATE_LOCAL_CANDIDATES:
        try:
            if path.exists():
                gdf = _normalize_state_gdf(gpd.read_file(path))
                if gdf is not None and not gdf.empty:
                    _INDIA_STATES_CACHE = gdf
                    return gdf.copy()
        except Exception:
            continue

    # 3) Download once into /tmp
    try:
        dest = Path("/tmp/india_state_boundaries.fgb")
        gdf = _download_india_states_fgb(dest)
        if gdf is not None and not gdf.empty:
            _INDIA_STATES_CACHE = gdf
            return gdf.copy()
    except Exception:
        pass
    return None


def get_state_context(watershed_geom: dict):
    """State/UT polygons intersecting the project watershed (clinton get_state_context)."""
    try:
        from shapely.geometry import shape
    except Exception:
        return None

    states = load_india_states()
    if states is None or states.empty:
        return None
    try:
        geom = shape(watershed_geom)
        hit = states[states.intersects(geom)].copy()
        return hit if not hit.empty else None
    except Exception:
        return None


def state_context_names(context_states) -> list[str]:
    if context_states is None or getattr(context_states, "empty", True):
        return []
    if "ST_NM" not in context_states.columns:
        return []
    return [str(v).strip() for v in context_states["ST_NM"].dropna().unique().tolist() if str(v).strip()]


def _read_level7_bbox(bbox: tuple[float, float, float, float]):
    import geopandas as gpd

    try:
        from app.modules.diagnose.services.layer_analysis import _read_vector_gdf_bbox

        gdf = _read_vector_gdf_bbox(LEVEL7_S3_KEY, bbox)
        if gdf is not None and not gdf.empty:
            return gdf
    except Exception:
        pass
    for path in _LEVEL7_LOCAL_CANDIDATES:
        try:
            if path.exists():
                gdf = gpd.read_file(path, bbox=bbox)
                if gdf is not None and not gdf.empty:
                    return gdf
        except Exception:
            continue
    return None


def load_level7_parent(watershed_geom: dict):
    """Parent Level-7 basin containing the project AOI (full polygon, not clipped to L12)."""
    try:
        from shapely.geometry import shape

        from app.modules.diagnose.services.layer_analysis import _watershed_bbox
    except Exception:
        return None

    try:
        geom = shape(watershed_geom)
        bbox = _watershed_bbox(watershed_geom, pad_frac=0.25)
        gdf = _ensure_wgs84(_read_level7_bbox(bbox))
        if gdf is None or gdf.empty:
            return None
        rep = geom.representative_point()
        covers = gdf[gdf.geometry.apply(lambda g: g is not None and not g.is_empty and (g.covers(rep) or g.contains(rep)))]
        if covers.empty:
            hits = gdf[gdf.intersects(geom)].copy()
            if hits.empty:
                return None
            # Prefer the L7 with the largest overlap with the AOI.
            try:
                hits = hits.assign(_overlap=hits.geometry.intersection(geom).area)
                covers = hits.sort_values("_overlap", ascending=False).drop(columns=["_overlap"], errors="ignore")
            except Exception:
                covers = hits
        out = covers.head(1).copy()
        return out if not out.empty else None
    except Exception:
        return None


def _as_shapely(boundary) -> Any:
    from shapely.geometry import shape

    if boundary is None:
        return None
    if isinstance(boundary, dict):
        return shape(boundary)
    if hasattr(boundary, "geometry"):
        geom_col = boundary.geometry
        if hasattr(geom_col, "iloc"):
            return geom_col.iloc[0]
        return geom_col
    return boundary


def load_level12_within(boundary, *, clip_to_boundary: bool = True):
    """Level-12 basins intersecting a boundary (typically the parent L7), with UP_AREA."""
    try:
        import geopandas as gpd

        from app.shared import watersheds as ws
    except Exception:
        return None

    try:
        geom = _as_shapely(boundary)
        if geom is None or geom.is_empty:
            return None

        path = ws._fgb_vsis3_path()
        minx, miny, maxx, maxy = geom.bounds
        pad = max((maxx - minx), (maxy - miny), 0.02) * 0.08
        gdf = gpd.read_file(path, bbox=(minx - pad, miny - pad, maxx + pad, maxy + pad))
        if gdf.empty:
            return None
        gdf = _ensure_wgs84(gdf)
        hit = gdf[gdf.intersects(geom)].copy()
        if hit.empty:
            return None
        if clip_to_boundary:
            boundary_gdf = gpd.GeoDataFrame(geometry=[geom], crs=4326)
            try:
                hit = gpd.clip(hit, boundary_gdf)
            except Exception:
                hit["geometry"] = hit.geometry.intersection(geom)
            hit = hit[hit.geometry.notna() & ~hit.geometry.is_empty]
        return hit if not hit.empty else None
    except Exception:
        return None


def load_level12_subbasins(watershed_geom: dict):
    """GeoDataFrame of Level-12 basins clipped to the project AOI boundary (with UP_AREA)."""
    return load_level12_within(watershed_geom, clip_to_boundary=True)


def _nodata_for_dtype(dtype, nodata, src_nodata):
    """Pick a fill/nodata value that fits the raster dtype (DEM is uint16 but yaml says -9999)."""
    import numpy as np

    candidate = nodata if nodata is not None else src_nodata
    if candidate is None:
        return None
    try:
        if np.issubdtype(dtype, np.integer):
            info = np.iinfo(dtype)
            if candidate < info.min or candidate > info.max:
                return int(0)
        else:
            # floats accept nan as display nodata; keep configured value when in range
            return candidate
    except Exception:
        return None
    return candidate


def _finalize_raster_clip(src, geom, cfg: LayerConfig) -> dict[str, Any] | None:
    import numpy as np
    from rasterio.mask import mask as rio_mask
    from rasterio.transform import array_bounds

    dtype = src.dtypes[0] if src.dtypes else src.dtypes
    nodata = _nodata_for_dtype(dtype, cfg.nodata, src.nodata)
    # Prefer unfilled mask so outside-polygon cells stay masked without dtype-incompatible fills.
    try:
        out_image, out_transform = rio_mask(src, [geom], crop=True, filled=False)
        data = np.ma.array(out_image[0], mask=np.ma.getmaskarray(out_image[0]))
    except Exception:
        fill = 0 if nodata is None else nodata
        out_image, out_transform = rio_mask(src, [geom], crop=True, nodata=fill, filled=True)
        data = out_image[0]
        data = np.ma.masked_equal(data, fill)

    display_nodata = cfg.nodata if cfg.nodata is not None else src.nodata
    if display_nodata is not None:
        try:
            # NaN nodata must use masked_invalid — masked_equal(NaN) never matches.
            if isinstance(display_nodata, float) and np.isnan(display_nodata):
                data = np.ma.masked_invalid(data)
            else:
                data = np.ma.masked_equal(data, display_nodata)
        except Exception:
            pass
    # Capture AOI exterior before float NaN remask — CI fills NaN to 0.0 for display.
    outside_aoi = np.ma.getmaskarray(data).copy()
    # Float COGs store empty cells as NaN even when GeoTIFF nodata is unset.
    if cfg.id != "cropping_intensity":
        try:
            if np.issubdtype(np.asanyarray(data).dtype, np.floating):
                data = np.ma.masked_invalid(data)
        except Exception:
            pass
    # DEM / continuous elevation: treat zeros outside valid terrain as empty when yaml nodata is unusable.
    if cfg.id == "dem":
        data = np.ma.masked_equal(data, 0)
        data = np.ma.masked_less_equal(data.astype(float), -9999)
    # Cropping intensity: map NaN / negative to spectrum floor (0.0); keep only
    # outside-AOI cells masked so the watershed fills continuously.
    if cfg.id == "cropping_intensity":
        try:
            work = np.array(data.filled(np.nan), dtype=float)
            fill = ~outside_aoi & (~np.isfinite(work) | (work < 0))
            work[fill] = 0.0
            data = np.ma.array(work, mask=outside_aoi)
        except Exception:
            pass

    height, width = data.shape
    west, south, east, north = array_bounds(height, width, out_transform)
    return {
        "array": data,
        "transform": out_transform,
        "extent": (west, east, south, north),
        "crs": src.crs,
        # Prefer an explicit sentinel for float empty cells so plotters can remask.
        "nodata": display_nodata if display_nodata is not None else (np.nan if np.issubdtype(np.asanyarray(data).dtype, np.floating) else None),
    }


def _clip_raster_array(cfg: LayerConfig, watershed_geom: dict) -> dict[str, Any] | None:
    """Windowed raster clip for map rendering via rasterio + shapely mask."""
    try:
        import rasterio
        from rasterio.warp import transform_geom
    except ImportError:
        return None

    from app.modules.diagnose.services.layer_analysis import _vsis3_path

    path = _vsis3_path(cfg.s3_key)
    ws = shape(watershed_geom)
    try:
        with rasterio.open(path) as src:
            geom = transform_geom("EPSG:4326", src.crs, mapping(ws), precision=6)
            return _finalize_raster_clip(src, geom, cfg)
    except Exception:
        return None


def process_layers(
    watershed_geom: dict,
    *,
    progress: PackageProgress | None = None,
) -> dict[str, dict[str, Any]]:
    """Clip + analyze all enabled atlas layers. Returns results keyed by layer id."""
    from app.modules.diagnose.routers.layers import _presigned_url_cached, _run_layer_analysis_sync

    configs = _enabled_configs()
    results: dict[str, dict[str, Any]] = {}
    n = max(1, len(configs))
    for i, cfg in enumerate(configs):
        pct = 8 + int(50 * i / n)
        if progress:
            progress.emit(pct, f"Clipping {cfg.name}…")
        entry: dict[str, Any] = {
            "cfg": cfg,
            "name": cfg.name,
            "category": cfg.category or "",
            "status": "failed",
            "stats": {},
            "type": "vector" if cfg.source == "vector_fgb" else "raster",
            "gdf": None,
            "raster": None,
            "error": None,
        }
        try:
            analysis = _run_layer_analysis_sync(cfg, watershed_geom)
            entry["stats"] = analysis.stats or {}
            entry["status"] = "success" if analysis.status == "ok" else "failed"
            entry["error"] = analysis.error

            if cfg.source == "vector_fgb":
                gdf = clipped_vector_gdf_for_watershed(cfg.s3_key, watershed_geom, cfg)
                gdf = enrich_vector_gdf(gdf, cfg)
                entry["gdf"] = gdf
                entry["type"] = "vector"
                if gdf is None or getattr(gdf, "empty", True):
                    if entry["status"] == "success":
                        entry["status"] = "empty"
            else:
                entry["raster"] = _clip_raster_array(cfg, watershed_geom)
                entry["type"] = "raster"
                # Prefer presigned path for map if vsis3 mask failed
                if entry["raster"] is None:
                    try:
                        url = _presigned_url_cached(cfg.s3_key)
                        entry["raster"] = _clip_raster_from_url(cfg, watershed_geom, url)
                    except Exception:
                        pass
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
        results[cfg.id] = entry
    return results


def _clip_raster_from_url(cfg: LayerConfig, watershed_geom: dict, url: str) -> dict[str, Any] | None:
    try:
        import rasterio
        from rasterio.warp import transform_geom
    except ImportError:
        return None
    ws = shape(watershed_geom)
    try:
        with rasterio.open(url) as src:
            geom = transform_geom("EPSG:4326", src.crs, mapping(ws), precision=6)
            return _finalize_raster_clip(src, geom, cfg)
    except Exception:
        return None
