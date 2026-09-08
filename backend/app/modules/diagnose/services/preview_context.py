"""Reference layers for diagnose project-creation map preview."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from typing import Any

from app.modules.diagnose.services.layer_analysis import clip_vector_geojson

logger = logging.getLogger(__name__)

# Keys under the diagnose S3 bucket (dev: well-labs-dda-product-dev-bucket).
# One colour per hierarchy level (micro watersheds all share blue).
PREVIEW_CONTEXT_LAYERS: tuple[dict[str, Any], ...] = (
    {
        "id": "rivers",
        "name": "Rivers",
        "s3_key": "vector/india_rivers_level_12.gpkg",
        "geometry_kind": "line",
        "render_type": "line",
        "clip_mode": "clip",
        "line_color": "#457b9d",
        "line_width": 1.6,
        "fill_color": None,
        "fill_opacity": 0,
    },
    {
        "id": "basin",
        "name": "Basin",
        "s3_key": "vector/Basin.gpkg",
        "geometry_kind": "polygon",
        "render_type": "outline",
        "clip_mode": "intersect",
        "line_color": "#00306d",
        "line_width": 2.4,
        "fill_color": "#00306d",
        "fill_opacity": 0.05,
    },
    {
        "id": "sub_basin",
        "name": "Sub basin",
        "s3_key": "vector/Sub Basins of india.gpkg",
        "geometry_kind": "polygon",
        "render_type": "outline",
        "clip_mode": "intersect",
        "line_color": "#7c3aed",
        "line_width": 2.0,
        "fill_color": "#7c3aed",
        "fill_opacity": 0.07,
    },
    {
        "id": "level7",
        "name": "Level-7 watershed",
        "s3_key": "vector/india_basins_level_7.gpkg",
        "geometry_kind": "polygon",
        "render_type": "outline",
        "clip_mode": "intersect",
        "line_color": "#db2777",
        "line_width": 1.8,
        "fill_color": "#db2777",
        "fill_opacity": 0.08,
    },
)


def _layer_cfg(meta: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=meta["id"],
        geometry_kind=meta["geometry_kind"],
        render_type=meta["render_type"],
        clip_mode=meta["clip_mode"],
        style_column=None,
        analysis_type=None,
    )


def _clip_one(meta: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "id": meta["id"],
        "name": meta["name"],
        "s3_key": meta["s3_key"],
        "geometry_kind": meta["geometry_kind"],
        "render_type": meta["render_type"],
        "line_color": meta["line_color"],
        "line_width": meta["line_width"],
        "fill_color": meta["fill_color"],
        "fill_opacity": meta["fill_opacity"],
        "status": "ok",
        "error": None,
        "geojson": {"type": "FeatureCollection", "features": []},
    }
    try:
        entry["geojson"] = clip_vector_geojson(
            meta["s3_key"],
            "",
            geometry,
            layer_cfg=_layer_cfg(meta),
            pad_frac=0.08,
        )
    except Exception as exc:
        logger.warning("Preview context layer %s failed: %s", meta["id"], exc)
        entry["status"] = "error"
        entry["error"] = str(exc)
    return entry


def preview_context_layers(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Clip/filter configured reference layers to the preview AOI geometry."""
    if not geometry:
        raise ValueError("geometry is required")

    # Parallel S3/local reads — wall time ≈ slowest layer, not sum.
    by_id: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(PREVIEW_CONTEXT_LAYERS)) as pool:
        futures = {
            pool.submit(_clip_one, meta, geometry): meta["id"] for meta in PREVIEW_CONTEXT_LAYERS
        }
        for fut in as_completed(futures):
            by_id[futures[fut]] = fut.result()
    return [by_id[meta["id"]] for meta in PREVIEW_CONTEXT_LAYERS]


def _micro_layer(geometry: dict[str, Any], *, clip_to_project: bool = False) -> dict[str, Any]:
    """Level-12 micro watersheds intersecting the AOI (same blues as create preview)."""
    from shapely.geometry import mapping, shape

    from app.shared.watersheds import watersheds_intersecting

    entry = {
        "id": "micro",
        "name": "Micro watershed (L12)",
        "s3_key": None,
        "geometry_kind": "polygon",
        "render_type": "outline",
        "line_color": "#1c75e9",
        "line_width": 1.8,
        "fill_color": "#1c75e9",
        "fill_opacity": 0.28,
        "status": "ok",
        "error": None,
        "geojson": {"type": "FeatureCollection", "features": []},
    }
    try:
        parts = watersheds_intersecting(geometry)
        project_shape = shape(geometry) if clip_to_project else None
        features = []
        for part in parts:
            geom = part.get("geometry")
            if not geom:
                continue
            if project_shape is not None:
                micro = shape(geom)
                if micro.is_empty:
                    continue
                inter = micro.intersection(project_shape)
                if inter.is_empty:
                    continue
                # Keep micros that make up the project; drop ones that only skim the edge.
                try:
                    frac = float(inter.area / micro.area) if micro.area else 0.0
                except Exception:
                    frac = 0.0
                inside = False
                try:
                    inside = project_shape.contains(micro.representative_point())
                except Exception:
                    inside = False
                if frac < 0.2 and not inside:
                    continue
                geom = mapping(inter)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "watershed_id": part.get("watershed_id"),
                        "watershed_name": part.get("watershed_name"),
                        "name": part.get("watershed_name"),
                    },
                    "geometry": geom,
                }
            )
        entry["geojson"] = {"type": "FeatureCollection", "features": features}
    except Exception as exc:
        logger.warning("Preview micro watersheds failed: %s", exc)
        entry["status"] = "error"
        entry["error"] = str(exc)
    return entry


def project_hierarchy_layers(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Full hierarchy for analysis (basin → rivers → L12)."""
    layers = preview_context_layers(geometry)
    layers.append(_micro_layer(geometry, clip_to_project=False))
    return layers


def project_hierarchy_map_layers(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Project map: basin / sub-basin / L7 / rivers + only L12 micros in the project AOI."""
    layers = preview_context_layers(geometry)
    layers.append(_micro_layer(geometry, clip_to_project=True))
    return layers


def analyze_watershed_hierarchy(geometry: dict[str, Any]) -> dict[str, str]:
    """Evidence stats for the Watershed hierarchy layer."""
    layers = project_hierarchy_layers(geometry)
    by_id = {layer["id"]: layer for layer in layers}

    def _n(layer_id: str) -> int:
        layer = by_id.get(layer_id) or {}
        if layer.get("status") == "error":
            return 0
        return len(((layer.get("geojson") or {}).get("features")) or [])

    def _names(layer_id: str, limit: int = 4) -> str:
        layer = by_id.get(layer_id) or {}
        feats = ((layer.get("geojson") or {}).get("features")) or []
        names: list[str] = []
        for feat in feats:
            props = feat.get("properties") or {}
            for key in (
                "watershed_name",
                "name",
                "NAME",
                "Name",
                "ba_name",
                "basin_name",
                "Basin_Name",
                "sub_basin",
                "SUB_BASIN",
                "Sub_Basin",
                "HYBAS_ID",
                "PFAF_ID",
            ):
                val = props.get(key)
                if val is not None and str(val).strip():
                    text = str(val).strip()
                    if text not in names:
                        names.append(text)
                    break
            if len(names) >= limit:
                break
        if not names:
            return "—"
        extra = _n(layer_id) - len(names)
        if extra > 0:
            return ", ".join(names) + f" (+{extra} more)"
        return ", ".join(names)

    return {
        "Basin": _names("basin") if _n("basin") else "None intersecting",
        "Sub basin": _names("sub_basin") if _n("sub_basin") else "None intersecting",
        "Level-7 watersheds": str(_n("level7")),
        "Micro watersheds (L12)": str(_n("micro")),
        "River segments in AOI": str(_n("rivers")),
    }
