import httpx
import boto3
import json
import math
import time
import asyncio
import numpy as np
from collections import OrderedDict
from functools import lru_cache
from botocore.exceptions import ClientError
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rio_tiler.io import Reader
from rio_tiler.models import ImageData
from shapely.geometry import shape as shp_shape

from app.modules.diagnose.services.layer_analysis import (
    analyze_layer,
    clipped_vector_geojson_for_watershed,
)
from app.modules.diagnose.services.terrain_drape import (
    dem_layer_config,
    get_cached_dem_mesh,
    get_cached_drape,
    get_cached_drape_grid,
    render_cog_drape,
    render_drape_grid,
    render_terrarium_tile,
    render_vector_drape,
)
from app.modules.diagnose.services.layer_catalog import (
    LayerConfig,
    display_name_for_key,
    get_catalog,
    get_layer_by_id,
    get_layer_for_key,
)
from app.shared.access import assert_diagnosis_access
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor

router = APIRouter()

PRESIGN_TTL = 3600

_presign_cache: dict[str, tuple[str, float]] = {}


class LegendItem(BaseModel):
    value: int | str | None = None
    label: str
    color: str


class ChoroplethStopItem(BaseModel):
    min: float
    max: float
    label: str
    color: str


class CogLayer(BaseModel):
    id: str
    name: str
    s3_key: str
    cog_url: str
    tiles_url: str
    info_url: str
    render_type: str | None = None
    legend: list[LegendItem] = []
    bounds: list[float] | None = None
    status: str = "unknown"
    error: str | None = None
    interpretation: str = ""
    meaning: str = ""
    uncertainty: str = ""
    field_check: str = ""
    analysis_type: str | None = None
    category: str | None = None


class LayersResponse(BaseModel):
    cog_layers: list[CogLayer]
    titiler_url: str


class VectorLayer(BaseModel):
    id: str
    name: str
    s3_key: str
    url: str
    render_type: str
    style_column: str | None = None
    label_column: str | None = None
    legend: list[LegendItem] = []
    choropleth_stops: list[ChoroplethStopItem] = []
    interpretation: str = ""
    meaning: str = ""
    uncertainty: str = ""
    field_check: str = ""
    analysis_type: str | None = None
    map_render: bool = True
    category: str | None = None
    status: str = "ok"
    error: str | None = None


class VectorLayersResponse(BaseModel):
    vector_layers: list[VectorLayer]


class LayerAnalysisResponse(BaseModel):
    layer_id: str
    stats: dict[str, str]
    evidence: str = ""
    meaning: str = ""
    uncertainty: str = ""
    interpretation: str = ""
    field_check: str = ""
    status: str = "ok"
    error: str | None = None


class BatchAnalysisResponse(BaseModel):
    analyses: list[LayerAnalysisResponse]


class DemMeshResponse(BaseModel):
    cols: int
    rows: int
    elevations: list[list[float | None]]
    mask: list[list[int]]
    bounds: list[float]
    elev_min: float
    elev_max: float
    max_size: int = 256


def _layer_id(key: str) -> str:
    return key.replace("/", "_").replace(".", "_")


def _cog_keys() -> list[str]:
    return [key.strip() for key in settings.cog_layers.split(",") if key.strip()]


def _vector_keys() -> list[str]:
    return [key.strip() for key in settings.vector_layers.split(",") if key.strip()]


def _cog_id_for_key(key: str) -> str:
    cfg = get_layer_for_key(key)
    return cfg.id if cfg else _layer_id(key)


def _key_from_id(layer_id: str) -> str | None:
    cfg = get_layer_by_id(layer_id)
    if cfg and cfg.source == "cog" and cfg.s3_key in _cog_keys():
        return cfg.s3_key
    for key in _cog_keys():
        if _layer_id(key) == layer_id or _cog_id_for_key(key) == layer_id:
            return key
    return None


def _s3_client():
    region = settings.aws_default_region
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
    )


def _presigned_url(key: str) -> str:
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": key},
        ExpiresIn=PRESIGN_TTL,
    )


def _presigned_url_cached(key: str) -> str:
    now = time.time()
    cached = _presign_cache.get(key)
    if cached and now < cached[1] - 120:
        return cached[0]
    url = _presigned_url(key)
    _presign_cache[key] = (url, now + PRESIGN_TTL)
    return url


# 256×256 transparent PNG — returned for tiles outside the watershed or on clip errors.
_TRANSPARENT_TILE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x01\x00\x00\x00\x01\x00"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _tile_bounds_wgs84(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) in WGS-84 for a Web Mercator tile."""
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return (west, south, east, north)


def _bbox_intersects(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


# In-process rendered-tile cache: (s3_key, z, x, y, project_id) → PNG bytes.
# 512 tiles × ~20 KB ≈ ~10 MB max footprint.
_TILE_CACHE: OrderedDict[tuple, bytes] = OrderedDict()
_TILE_CACHE_MAX = 512


def _tile_cache_get(key: tuple) -> bytes | None:
    if key in _TILE_CACHE:
        _TILE_CACHE.move_to_end(key)
        return _TILE_CACHE[key]
    return None


def _tile_cache_set(key: tuple, data: bytes) -> None:
    if key in _TILE_CACHE:
        _TILE_CACHE.move_to_end(key)
    else:
        _TILE_CACHE[key] = data
        if len(_TILE_CACHE) > _TILE_CACHE_MAX:
            _TILE_CACHE.popitem(last=False)


# Per-(s3_key, project_id) elevation range cache for consistent cross-tile scaling.
_ELEV_RANGE_CACHE: dict[tuple[str, str], tuple[float, float]] = {}


def _watershed_elev_range(s3_key: str, http_url: str, watershed_geom: dict) -> tuple[float, float]:
    """Return (lo, hi) elevation percentiles for the watershed, computed once and cached."""
    cache_key = (s3_key, json.dumps(watershed_geom, sort_keys=True, separators=(",", ":")))
    if cache_key in _ELEV_RANGE_CACHE:
        return _ELEV_RANGE_CACHE[cache_key]
    try:
        ws = shp_shape(watershed_geom)
        minx, miny, maxx, maxy = ws.bounds
        img = Reader(http_url).part([minx, miny, maxx, maxy], indexes=[1], max_size=256)
        arr = img.array[0].astype(np.float32)
        if img.alpha_mask is not None:
            arr = np.where(img.alpha_mask > 0, arr, np.nan)
        valid = arr[~np.isnan(arr)]
        if valid.size < 4:
            result = (0.0, 3000.0)
        else:
            result = (float(np.percentile(valid, 2)), float(np.percentile(valid, 98)))
    except Exception:
        result = (0.0, 3000.0)
    _ELEV_RANGE_CACHE[cache_key] = result
    return result


@lru_cache(maxsize=64)
def _watershed_feature_json(project_id: str) -> str:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT ST_AsGeoJSON(watershed_geom, 9)::json AS geom
            FROM diagnosis WHERE id = %(id)s
            """,
            {"id": project_id},
        )
        row = cur.fetchone()
    if not row or not row["geom"]:
        raise HTTPException(404, "Project watershed not found")
    return json.dumps({"type": "Feature", "geometry": row["geom"], "properties": {}})


def _watershed_feature(project_id: str) -> dict:
    return json.loads(_watershed_feature_json(project_id))


def _render_params(layer_cfg: LayerConfig | None, bbox: list[float] | None = None) -> str:
    params = "&bidx=1"
    if layer_cfg and layer_cfg.render_type == "categorical" and layer_cfg.classes:
        colormap = quote(json.dumps(layer_cfg.titiler_colormap(), separators=(",", ":")), safe="")
        params += f"&colormap={colormap}"
    elif layer_cfg and layer_cfg.render_type == "continuous":
        cmap_name = str(layer_cfg.continuous.get("colormap") or "terrain")
        params += f"&colormap_name={quote(cmap_name, safe='')}"
    if bbox and len(bbox) == 4:
        bbox_str = ",".join(str(v) for v in bbox)
        params += f"&bbox={bbox_str}"
    return params


def _titiler_tile_url(
    http_url: str,
    z: int,
    x: int,
    y: int,
    layer_cfg: LayerConfig | None = None,
    bbox: list[float] | None = None,
) -> str:
    encoded = quote(http_url, safe="")
    base = settings.titiler_url.rstrip("/")
    return f"{base}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}?url={encoded}{_render_params(layer_cfg, bbox)}"


def _titiler_info_url(http_url: str) -> str:
    encoded = quote(http_url, safe="")
    base = settings.titiler_url.rstrip("/")
    return f"{base}/cog/info?url={encoded}"


def _render_clipped_tile(
    http_url: str,
    z: int,
    x: int,
    y: int,
    feature: dict,
    layer_cfg: LayerConfig | None,
    elev_range: tuple[float, float] | None = None,
) -> bytes:
    """Mask raster to the watershed in Web Mercator tile space."""
    geom = feature.get("geometry", feature)
    rio_cmap = layer_cfg.rio_colormap() if layer_cfg and layer_cfg.render_type == "categorical" else None
    continuous_cmap = None
    if layer_cfg and layer_cfg.render_type == "continuous":
        try:
            from rio_tiler.colormap import cmap as rio_cmaps
            continuous_cmap = rio_cmaps.get(str(layer_cfg.continuous.get("colormap") or "gist_earth"))
        except Exception:
            continuous_cmap = None
    nodata = layer_cfg.nodata if layer_cfg else 0

    with Reader(http_url) as src:
        img = src.tile(x, y, z, tilesize=256, indexes=[1])

    # Step 1: determine which pixels have real data (not nodata / outside file extent).
    if img.alpha_mask is not None:
        if not np.any(img.alpha_mask):
            return _TRANSPARENT_TILE
        base = img.alpha_mask > 0
    elif img.array.size:
        base = (img.array[0] != nodata) if nodata is not None else np.ones(img.array[0].shape, dtype=bool)
    else:
        return _TRANSPARENT_TILE

    # Step 2: compute watershed clip mask (MUST come before rescaling so we can use it).
    geom_wm = transform_geom("EPSG:4326", "EPSG:3857", geom)
    tile_mask = geometry_mask(
        [geom_wm],
        out_shape=(img.height, img.width),
        transform=img.transform,
        invert=True,
        all_touched=True,
    )
    if not tile_mask.any():
        return _TRANSPARENT_TILE

    # Step 3: for continuous layers (DEM stored as uint16), rescale to 0–255 using
    # the watershed-level range so ALL tiles share the same colour scale.
    if continuous_cmap is not None and img.array.dtype != np.uint8:
        arr = img.array[0].astype(np.float32)
        if elev_range:
            lo, hi = elev_range
        else:
            valid_px = arr[base & tile_mask]
            lo = float(valid_px.min()) if valid_px.size else 0.0
            hi = float(valid_px.max()) if valid_px.size else 1.0
        if hi <= lo:
            hi = lo + 1.0
        scaled = np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
        img = ImageData(
            scaled[np.newaxis, :, :],
            alpha_mask=img.alpha_mask,
            crs=img.crs,
            bounds=img.bounds,
        )
        base = np.ones(scaled.shape, dtype=bool)

    # Step 4: build final alpha and render.
    alpha = np.where(tile_mask & base, 255, 0).astype(np.uint8)
    masked = ImageData(img.array, alpha_mask=alpha, crs=img.crs, bounds=img.bounds)
    if rio_cmap:
        return masked.render(img_format="PNG", colormap=rio_cmap, add_mask=True)
    if continuous_cmap:
        return masked.render(img_format="PNG", colormap=continuous_cmap, add_mask=True)
    return masked.render(img_format="PNG", add_mask=True)


def _intersect_bounds(cog_bounds: list[float] | None, clip: list[float] | None) -> list[float] | None:
    if not clip or len(clip) != 4:
        return cog_bounds
    if not cog_bounds or len(cog_bounds) != 4:
        return clip
    west = max(cog_bounds[0], clip[0])
    south = max(cog_bounds[1], clip[1])
    east = min(cog_bounds[2], clip[2])
    north = min(cog_bounds[3], clip[3])
    if west >= east or south >= north:
        return clip
    return [west, south, east, north]


def _tile_query(bbox: list[float] | None, project_id: str | None) -> str:
    parts = []
    if bbox:
        parts.append(f"bbox={','.join(str(v) for v in bbox)}")
    if project_id:
        parts.append(f"project_id={project_id}")
    return f"?{'&'.join(parts)}" if parts else ""


def _legend_items(layer_cfg: LayerConfig | None) -> list[LegendItem]:
    if not layer_cfg:
        return []
    return [
        LegendItem(value=e.value, label=e.label, color=e.color)
        for e in layer_cfg.legend_entries()
    ]


def _evidence_from_stats(stats: dict[str, str]) -> str:
    parts = []
    for key, value in (stats or {}).items():
        if str(key).lower().startswith("data warning"):
            continue
        text = str(value or "").strip()
        if not text or text.lower() in {"n/a", "na", "none", "nan", "unknown"}:
            continue
        parts.append(f"{key}: {text}")
    return "; ".join(parts) if parts else "Field verification should fill this signal."


def _analysis_response(cfg: LayerConfig, result) -> LayerAnalysisResponse:
    meaning = cfg.meaning or cfg.interpretation
    return LayerAnalysisResponse(
        layer_id=cfg.id,
        stats=result.stats,
        evidence=_evidence_from_stats(result.stats) if result.status == "ok" else "",
        meaning=meaning,
        uncertainty=cfg.uncertainty,
        interpretation=meaning,
        field_check=cfg.field_check,
        status=result.status,
        error=result.error,
    )


def _build_layer(
    key: str,
    bbox: list[float] | None = None,
    project_id: str | None = None,
) -> CogLayer:
    layer_cfg = get_layer_for_key(key)
    name = display_name_for_key(key)
    layer_id = _cog_id_for_key(key)
    cog_url = f"s3://{settings.aws_s3_bucket}/{key}"
    legend = _legend_items(layer_cfg)
    render_type = layer_cfg.render_type if layer_cfg else None
    meaning = (layer_cfg.meaning or layer_cfg.interpretation) if layer_cfg else ""
    uncertainty = layer_cfg.uncertainty if layer_cfg else ""
    field_check = layer_cfg.field_check if layer_cfg else ""
    analysis_type = layer_cfg.analysis_type if layer_cfg else None
    category = layer_cfg.category if layer_cfg else None

    try:
        _presigned_url_cached(key)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        return CogLayer(
            id=layer_id,
            name=name,
            s3_key=key,
            cog_url=cog_url,
            tiles_url="",
            info_url="",
            render_type=render_type,
            legend=legend,
            status="error",
            error=f"{err.get('Code', 'S3Error')}: {err.get('Message', str(exc))}",
            interpretation=meaning,
            meaning=meaning,
            uncertainty=uncertainty,
            field_check=field_check,
            analysis_type=analysis_type,
            category=category,
        )

    tiles_url = f"/api/layers/cog/{layer_id}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}{_tile_query(bbox, project_id)}"
    return CogLayer(
        id=layer_id,
        name=name,
        s3_key=key,
        cog_url=cog_url,
        tiles_url=tiles_url,
        info_url="",
        render_type=render_type,
        legend=legend,
        interpretation=meaning,
        meaning=meaning,
        uncertainty=uncertainty,
        field_check=field_check,
        analysis_type=analysis_type,
        category=category,
    )


async def _check_cog(layer: CogLayer, bbox: list[float] | None = None) -> CogLayer:
    if layer.status == "error":
        return layer
    if not settings.aws_s3_bucket:
        return layer.model_copy(
            update={"status": "error", "error": "AWS_S3_BUCKET is not configured"}
        )

    try:
        http_url = _presigned_url_cached(layer.s3_key)
        internal_url = _titiler_info_url(http_url)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(internal_url)
        if not resp.is_success:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.reason_phrase
            return layer.model_copy(update={"status": "error", "error": str(detail)})
        info = resp.json()
        bounds = _intersect_bounds(info.get("bounds"), bbox)
        return layer.model_copy(update={"status": "ok", "bounds": bounds})
    except ClientError as exc:
        err = exc.response.get("Error", {})
        return layer.model_copy(
            update={"status": "error", "error": f"{err.get('Code')}: {err.get('Message')}"}
        )
    except httpx.HTTPError as exc:
        return layer.model_copy(update={"status": "error", "error": str(exc)})


@router.get("/dem/mesh", response_model=DemMeshResponse)
async def dem_mesh(
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Downsampled watershed DEM elevation grid for the 3D terrain viewer."""
    assert_diagnosis_access(user["id"], project_id)
    dem_cfg = dem_layer_config()
    if not dem_cfg:
        raise HTTPException(404, "DEM layer not configured")
    if dem_cfg.s3_key not in _cog_keys():
        raise HTTPException(404, "DEM not enabled in COG_LAYERS")

    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature

    try:
        http_url = _presigned_url_cached(dem_cfg.s3_key)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise HTTPException(403, f"S3 error: {err.get('Message')}") from exc

    try:
        mesh = await asyncio.to_thread(
            get_cached_dem_mesh, project_id, http_url, geom, dem_cfg.nodata
        )
    except Exception as exc:
        raise HTTPException(500, f"DEM mesh failed: {exc}") from exc

    return DemMeshResponse(**mesh)


@router.get("/dem/terrain/WebMercatorQuad/{z}/{x}/{y}")
async def dem_terrarium_tile(
    z: int,
    x: int,
    y: int,
    project_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Terrarium-encoded DEM tiles for MapLibre ``raster-dem`` terrain."""
    if project_id:
        assert_diagnosis_access(user["id"], project_id)

    dem_cfg = dem_layer_config()
    if not dem_cfg:
        raise HTTPException(404, "DEM layer not configured")
    if dem_cfg.s3_key not in _cog_keys():
        raise HTTPException(404, "DEM not enabled in COG_LAYERS")

    if z < 0 or z > 15:
        raise HTTPException(400, "z out of range")

    cache_key = ("terrarium", dem_cfg.s3_key, z, x, y)
    cached = _tile_cache_get(cache_key)
    if cached is not None:
        return Response(
            content=cached,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    try:
        http_url = _presigned_url_cached(dem_cfg.s3_key)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise HTTPException(403, f"S3 error: {err.get('Message')}") from exc

    try:
        png = await asyncio.to_thread(
            render_terrarium_tile,
            http_url,
            z,
            x,
            y,
            nodata=dem_cfg.nodata,
        )
    except Exception:
        from app.modules.diagnose.services.terrain_drape import encode_terrarium
        from PIL import Image
        import io as _io

        buf = _io.BytesIO()
        Image.fromarray(encode_terrarium(np.zeros((256, 256), dtype=np.float32)), mode="RGB").save(
            buf, format="PNG"
        )
        png = buf.getvalue()

    _tile_cache_set(cache_key, png)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{layer_id}/drape")
async def layer_drape_texture(
    layer_id: str,
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """PNG texture of a layer draped over the watershed DEM mesh grid."""
    assert_diagnosis_access(user["id"], project_id)
    cfg = _resolve_analysis_layer(layer_id)

    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature

    dem_cfg = dem_layer_config()
    if not dem_cfg or dem_cfg.s3_key not in _cog_keys():
        raise HTTPException(404, "DEM not available for drape alignment")

    try:
        dem_url = _presigned_url_cached(dem_cfg.s3_key)
        mesh = await asyncio.to_thread(
            get_cached_dem_mesh, project_id, dem_url, geom, dem_cfg.nodata
        )
    except Exception as exc:
        raise HTTPException(500, f"DEM mesh failed: {exc}") from exc

    cols, rows = mesh["cols"], mesh["rows"]
    bounds = mesh["bounds"]
    cache_key = (layer_id, project_id)

    def _build() -> bytes:
        if cfg.source == "cog":
            url = _presigned_url_cached(cfg.s3_key)
            return render_cog_drape(
                url, geom, cfg, cols=cols, rows=rows, bounds=bounds
            )
        if cfg.source == "vector_fgb":
            return render_vector_drape(
                cfg.s3_key, geom, cfg, cols=cols, rows=rows, bounds=bounds
            )
        raise ValueError(f"Unsupported layer source: {cfg.source}")

    try:
        png = await asyncio.to_thread(get_cached_drape, cache_key, _build)
    except Exception as exc:
        raise HTTPException(500, f"Drape failed: {exc}") from exc

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


class DrapeGridResponse(BaseModel):
    values: list[list[float | None]]
    colorscale: list | str
    cmin: float
    cmax: float
    title: str
    value_type: str = "continuous"
    category_labels: list[str] = []


@router.get("/{layer_id}/drape-grid", response_model=DrapeGridResponse)
async def layer_drape_grid(
    layer_id: str,
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Plotly surfacecolor grid aligned to the DEM mesh (layer draped on relief)."""
    assert_diagnosis_access(user["id"], project_id)
    cfg = _resolve_analysis_layer(layer_id)

    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature

    dem_cfg = dem_layer_config()
    if not dem_cfg or dem_cfg.s3_key not in _cog_keys():
        raise HTTPException(404, "DEM not available for drape alignment")

    try:
        dem_url = _presigned_url_cached(dem_cfg.s3_key)
        mesh = await asyncio.to_thread(
            get_cached_dem_mesh, project_id, dem_url, geom, dem_cfg.nodata
        )
    except Exception as exc:
        raise HTTPException(500, f"DEM mesh failed: {exc}") from exc

    cols, rows = mesh["cols"], mesh["rows"]
    bounds = mesh["bounds"]

    def _build() -> dict:
        is_dem = cfg.id == "dem" or cfg.analysis_type == "dem"
        elev_grid = None
        if is_dem:
            elev_grid = np.array(
                [
                    [np.nan if v is None else float(v) for v in row]
                    for row in mesh["elevations"]
                ],
                dtype=np.float64,
            )
        cog_url = None
        if cfg.source == "cog" and not is_dem:
            cog_url = _presigned_url_cached(cfg.s3_key)

        return render_drape_grid(
            watershed_geom=geom,
            layer_cfg=cfg,
            cols=cols,
            rows=rows,
            bounds=bounds,
            cog_url=cog_url,
            elev_grid=elev_grid,
        )

    try:
        grid = await asyncio.to_thread(
            get_cached_drape_grid, (layer_id, project_id), _build
        )
    except Exception as exc:
        raise HTTPException(500, f"Drape grid failed: {exc}") from exc

    return DrapeGridResponse(**grid)


@router.get("/cog", response_model=LayersResponse)
async def list_cog_layers(
    bbox: str | None = None,
    project_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Return COG layers; pass project_id to mask tiles to the project watershed polygon."""
    clip_bbox = None
    if bbox:
        try:
            clip_bbox = [float(v) for v in bbox.split(",")]
            if len(clip_bbox) != 4:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(400, "bbox must be west,south,east,north") from exc

    if project_id:
        assert_diagnosis_access(user["id"], project_id)
        _watershed_feature(project_id)

    layers: list[CogLayer] = []
    for key in _cog_keys():
        layer = _build_layer(key, clip_bbox, project_id)
        layer = await _check_cog(layer, clip_bbox)
        layers.append(layer)
    return LayersResponse(cog_layers=layers, titiler_url=settings.titiler_public_url)


def _parse_bbox_param(bbox: str | None) -> list[float] | None:
    if not bbox:
        return None
    try:
        values = [float(v) for v in bbox.split(",")]
        if len(values) != 4:
            raise ValueError
        return values
    except ValueError as exc:
        raise HTTPException(400, "bbox must be west,south,east,north") from exc


@router.get("/cog/{layer_id}/tiles/WebMercatorQuad/{z}/{x}/{y}")
async def proxy_cog_tile(
    layer_id: str,
    z: int,
    x: int,
    y: int,
    bbox: str | None = None,
    project_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Proxy COG tiles; with project_id, mask pixels outside the watershed polygon."""
    key = _key_from_id(layer_id)
    if not key:
        raise HTTPException(404, "Layer not found")

    if project_id:
        assert_diagnosis_access(user["id"], project_id)

    clip_bbox = _parse_bbox_param(bbox)
    layer_cfg = get_layer_for_key(key)

    try:
        http_url = _presigned_url_cached(key)

        if project_id:
            feature = _watershed_feature(project_id)

            # Pre-flight: skip tiles that cannot intersect the watershed bbox.
            ws_geom = feature.get("geometry") or feature
            ws_bounds = shp_shape(ws_geom).bounds  # (minx, miny, maxx, maxy)
            ws_bbox = (ws_bounds[0], ws_bounds[1], ws_bounds[2], ws_bounds[3])
            tile_bbox = _tile_bounds_wgs84(z, x, y)
            if not _bbox_intersects(tile_bbox, ws_bbox):
                return Response(
                    content=_TRANSPARENT_TILE,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"},
                )

            # Check in-process tile cache.
            cache_key = (key, z, x, y, project_id)
            cached = _tile_cache_get(cache_key)
            if cached is not None:
                return Response(
                    content=cached,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"},
                )

            # For continuous COG layers, compute a consistent watershed-level
            # elevation range once and cache it so all tiles share the same scale.
            elev_range = None
            if layer_cfg and layer_cfg.render_type == "continuous":
                elev_range = await asyncio.to_thread(
                    _watershed_elev_range, key, http_url, ws_geom
                )

            try:
                content = await asyncio.to_thread(
                    _render_clipped_tile, http_url, z, x, y, feature, layer_cfg, elev_range
                )
            except Exception:
                content = _TRANSPARENT_TILE
            _tile_cache_set(cache_key, content)
            return Response(
                content=content,
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )

        titiler_url = _titiler_tile_url(http_url, z, x, y, layer_cfg, clip_bbox)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(titiler_url)
        if not resp.is_success:
            raise HTTPException(resp.status_code, resp.text)
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/png"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise HTTPException(403, f"S3 error: {err.get('Message')}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Titiler error: {exc}") from exc


def _build_vector_layer(cfg: LayerConfig) -> VectorLayer:
    legend = _legend_items(cfg)
    stops = [
        ChoroplethStopItem(min=s.min, max=s.max, label=s.label, color=s.color)
        for s in cfg.choropleth_stops
    ]
    meaning = cfg.meaning or cfg.interpretation
    try:
        url = _presigned_url_cached(cfg.s3_key)
        return VectorLayer(
            id=cfg.id,
            name=cfg.name,
            s3_key=cfg.s3_key,
            url=url,
            render_type=cfg.render_type,
            style_column=cfg.style_column,
            label_column=cfg.label_column,
            legend=legend,
            choropleth_stops=stops,
            interpretation=meaning,
            meaning=meaning,
            uncertainty=cfg.uncertainty,
            field_check=cfg.field_check,
            analysis_type=cfg.analysis_type,
            map_render=cfg.map_render,
            category=cfg.category,
        )
    except ClientError as exc:
        err = exc.response.get("Error", {})
        return VectorLayer(
            id=cfg.id,
            name=cfg.name,
            s3_key=cfg.s3_key,
            url="",
            render_type=cfg.render_type,
            style_column=cfg.style_column,
            label_column=cfg.label_column,
            legend=legend,
            choropleth_stops=stops,
            interpretation=meaning,
            meaning=meaning,
            uncertainty=cfg.uncertainty,
            field_check=cfg.field_check,
            analysis_type=cfg.analysis_type,
            map_render=cfg.map_render,
            category=cfg.category,
            status="error",
            error=f"{err.get('Code', 'S3Error')}: {err.get('Message', str(exc))}",
        )


@router.get("/vector", response_model=VectorLayersResponse)
async def list_vector_layers(
    project_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Return FlatGeobuf vector layer metadata. url is watershed-clipped GeoJSON endpoint."""
    enabled = set(_vector_keys())
    if not enabled:
        return VectorLayersResponse(vector_layers=[])
    if project_id:
        assert_diagnosis_access(user["id"], project_id)
    layers: list[VectorLayer] = []
    for cfg in get_catalog().vector_layers():
        if cfg.s3_key not in enabled:
            continue
        entry = _build_vector_layer(cfg)
        q = f"?project_id={quote(project_id, safe='')}" if project_id else ""
        proxy_url = f"/api/diagnose/layers/vector/{cfg.id}/data{q}"
        layers.append(entry.model_copy(update={"url": proxy_url}))
    return VectorLayersResponse(vector_layers=layers)


@router.get("/vector/{layer_id}/data")
async def clipped_vector_layer_data(
    layer_id: str,
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Return watershed-clipped GeoJSON for map rendering (not the full national FGB)."""
    assert_diagnosis_access(user["id"], project_id)
    cfg = get_layer_by_id(layer_id)
    if not cfg or cfg.source != "vector_fgb":
        raise HTTPException(404, "Vector layer not found")

    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature

    try:
        vector_url = _presigned_url_cached(cfg.s3_key)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise HTTPException(404, f"S3 error: {err.get('Code')} – {err.get('Message')}") from exc

    try:
        geojson = await asyncio.to_thread(
            clipped_vector_geojson_for_watershed, cfg.s3_key, vector_url, geom
        )
    except Exception as exc:
        raise HTTPException(500, f"Clip failed: {exc}") from exc

    return Response(
        content=json.dumps(geojson, separators=(",", ":")),
        media_type="application/geo+json",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _resolve_analysis_layer(layer_id: str) -> LayerConfig:
    cfg = get_layer_by_id(layer_id)
    if cfg:
        return cfg
    key = _key_from_id(layer_id)
    if key:
        cfg = get_layer_for_key(key)
        if cfg:
            return cfg
    raise HTTPException(404, "Layer not found")


def _run_layer_analysis_sync(cfg: LayerConfig, geom: dict):
    """Run analyze_layer with vsis3/presign; used by single + batch endpoints."""
    from app.modules.diagnose.services.layer_analysis import AnalysisResult

    # Outline / reference overlays have no watershed stats.
    if cfg.render_type == "outline" or not cfg.analysis_type:
        return AnalysisResult(stats={}, status="ok")

    # COG layers with implemented raster analysis
    raster_analysis = {"dem", "jrc_occurrence", "jrc_transitions"}
    if cfg.source == "cog" and cfg.analysis_type not in raster_analysis:
        # LULC etc. — catalog text until zonal class-area exists
        return AnalysisResult(stats={"Status": "See map classes in the watershed"}, status="ok")

    vector_url = None
    cog_url = None
    try:
        if cfg.source == "cog":
            cog_url = _presigned_url_cached(cfg.s3_key)
        else:
            vector_url = _presigned_url_cached(cfg.s3_key)
    except ClientError:
        if cfg.source == "vector_fgb":
            vector_url = "vsis3"
        else:
            raise
    return analyze_layer(cfg, geom, vector_url=vector_url, cog_url=cog_url)


@router.get("/analysis/batch", response_model=BatchAnalysisResponse)
async def batch_layer_analysis(
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Preload watershed analysis for all enabled secondary layers at once."""
    assert_diagnosis_access(user["id"], project_id)
    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature

    enabled_cog = set(_cog_keys())
    enabled_vec = set(_vector_keys())
    configs: list[LayerConfig] = []
    for cfg in get_catalog().layers:
        # Skip outline overlays (e.g. village boundaries) — no thematic evidence
        if cfg.render_type == "outline" or not cfg.analysis_type:
            continue
        if cfg.source == "cog" and cfg.s3_key in enabled_cog:
            configs.append(cfg)
        elif cfg.source == "vector_fgb" and cfg.s3_key in enabled_vec:
            configs.append(cfg)

    async def _one(cfg: LayerConfig) -> LayerAnalysisResponse:
        try:
            result = await asyncio.to_thread(_run_layer_analysis_sync, cfg, geom)
            return _analysis_response(cfg, result)
        except Exception as exc:
            meaning = cfg.meaning or cfg.interpretation
            return LayerAnalysisResponse(
                layer_id=cfg.id,
                stats={},
                evidence="",
                meaning=meaning,
                uncertainty=cfg.uncertainty,
                interpretation=meaning,
                field_check=cfg.field_check,
                status="error",
                error=str(exc),
            )

    analyses = await asyncio.gather(*[_one(cfg) for cfg in configs])
    return BatchAnalysisResponse(analyses=list(analyses))


@router.get("/vector/{layer_id}/analysis", response_model=LayerAnalysisResponse)
async def analyze_vector_layer(
    layer_id: str,
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Watershed-clipped stats + Evidence / meaning / uncertainty / field check."""
    assert_diagnosis_access(user["id"], project_id)
    cfg = _resolve_analysis_layer(layer_id)
    feature = _watershed_feature(project_id)
    geom = feature.get("geometry") or feature
    result = await asyncio.to_thread(_run_layer_analysis_sync, cfg, geom)
    return _analysis_response(cfg, result)


@router.get("/cog/{layer_id}/analysis", response_model=LayerAnalysisResponse)
async def analyze_cog_layer(
    layer_id: str,
    project_id: str,
    user: dict = Depends(get_current_user),
):
    """Watershed-clipped analysis for a COG layer (e.g. DEM)."""
    return await analyze_vector_layer(layer_id, project_id, user)
