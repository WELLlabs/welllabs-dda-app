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


def _area_m2(geom) -> float:
    """Approximate geodesic area via equal-area projection (EPSG:6933)."""
    try:
        import pyproj

        project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
        return float(shp_transform(project, geom).area)
    except Exception:
        return float(geom.area)


_FGB_CACHE_DIR = Path(tempfile.gettempdir()) / "dda_vector_fgb_cache"


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


def _read_vector_gdf_bbox(s3_key: str, bbox: tuple[float, float, float, float]):
    """Read only features intersecting bbox via GDAL /vsis3/ HTTP range requests.

    Does NOT download the full national FGB (critical for villages.fgb ~600MB).
    """
    import geopandas as gpd

    path = _vsis3_path(s3_key)
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


def clip_vector_geojson(s3_key: str, vector_url: str, watershed_geom: dict) -> dict:
    """Return watershed-clipped GeoJSON FeatureCollection for map rendering.

    Reads only the watershed bbox from S3 via /vsis3/ range requests — never the
    full national FGB.
    """
    del vector_url  # unused; vsis3 uses IAM/env credentials
    bbox = _watershed_bbox(watershed_geom)
    gdf = _read_vector_gdf_bbox(s3_key, bbox)
    clipped = _clip_to_watershed(gdf, watershed_geom)
    if clipped.empty:
        return {"type": "FeatureCollection", "features": []}
    drop_cols = [c for c in ("calc_area",) if c in clipped.columns]
    if drop_cols:
        clipped = clipped.drop(columns=drop_cols)
    return json.loads(clipped.to_json())


_CLIP_MEM: dict[tuple[str, str], dict] = {}


def clipped_vector_geojson_for_watershed(
    s3_key: str, vector_url: str, watershed_geom: dict
) -> dict:
    key = (s3_key, json.dumps(watershed_geom, sort_keys=True))
    cached = _CLIP_MEM.get(key)
    if cached is not None:
        return cached
    result = clip_vector_geojson(s3_key, vector_url, watershed_geom)
    if len(_CLIP_MEM) > 64:
        _CLIP_MEM.clear()
    _CLIP_MEM[key] = result
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
        "__wiser_irrigation_access_class",
        "__wiser_kharif_resilience_class",
        "__wiser_rabi_resilience_class",
        "Irr_access",
        "Kharif_res",
        "Rabi_res",
    ]
    col = _find_column(clipped, *[c for c in candidates if c], search_terms=("class", "rank", "access", "resilien"))
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

        if not vector_url and layer_cfg.source == "vector_fgb":
            # Analysis can proceed with vsis3 even without a presigned URL
            vector_url = "vsis3"

        if not vector_url:
            return AnalysisResult(stats={}, status="error", error="Missing vector URL for analysis")

        bbox = _watershed_bbox(watershed_geom)
        gdf = _read_vector_gdf_bbox(layer_cfg.s3_key, bbox)
        clipped = _clip_to_watershed(gdf, watershed_geom)

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
        elif atype == "categorical_area":
            stats = {"Status": "Raster class-area analysis not yet enabled for live sidebar"}
        else:
            stats = {"Count": str(len(clipped))} if not clipped.empty else {"Status": "No features in watershed"}

        return AnalysisResult(stats=stats)
    except Exception as exc:
        return AnalysisResult(stats={}, status="error", error=str(exc))
