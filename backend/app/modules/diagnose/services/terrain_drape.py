"""Watershed DEM mesh + layer drape texture for the Flat/3D terrain viewer.

Mesh and drape share the same bbox / resolution so UVs align 1:1.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from rasterio.features import geometry_mask, rasterize
from rasterio.transform import from_bounds
from shapely.geometry import shape

from app.modules.diagnose.services.layer_analysis import (
    _clip_to_watershed,
    _find_column,
    _normalize_gw,
    _normalize_rank,
    _read_vector_gdf_bbox,
    _watershed_bbox,
)
from app.modules.diagnose.services.layer_catalog import LayerConfig, _hex_to_rgba

MESH_MAX_SIZE = 256

# In-process caches
_MESH_CACHE: dict[str, dict[str, Any]] = {}
_DRAPE_CACHE: dict[tuple[str, str], bytes] = {}
_DRAPE_GRID_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_MESH_CACHE_MAX = 32
_DRAPE_CACHE_MAX = 64
_DRAPE_GRID_CACHE_MAX = 64
_SENTINEL = -1.0e30


def _hex_to_rgba_safe(hex_color: str) -> tuple[int, int, int, int]:
    try:
        return _hex_to_rgba(hex_color)
    except Exception:
        return (200, 200, 200, 255)


def dem_layer_config() -> LayerConfig | None:
    from app.modules.diagnose.services.layer_catalog import get_catalog

    for layer in get_catalog().layers:
        if layer.id == "dem" or layer.analysis_type == "dem":
            return layer
    return None


def build_dem_mesh(
    cog_url: str,
    watershed_geom: dict,
    *,
    nodata: float | int | None = -9999,
    max_size: int = MESH_MAX_SIZE,
) -> dict[str, Any]:
    """Return downsampled DEM grid for the watershed.

    Elevations outside the watershed are zeroed and flagged in ``mask`` (0/1)
    so the client can build a mesh in the watershed outline only.
    Heights are true metres (not percentile-clipped) for consistent relief.
    """
    from rio_tiler.io import Reader

    ws = shape(watershed_geom)
    minx, miny, maxx, maxy = ws.bounds

    with Reader(cog_url) as src:
        img = src.part(
            [minx, miny, maxx, maxy],
            indexes=[1],
            max_size=max_size,
            dst_crs="EPSG:4326",
            bounds_crs="EPSG:4326",
        )

    arr = img.array[0].astype(np.float32)
    if nodata is not None:
        arr = np.where(arr == float(nodata), np.nan, arr)
    # Empty / ocean / nodata sentinels common in DEM products
    arr = np.where(arr <= 0, np.nan, arr)
    if img.alpha_mask is not None:
        arr = np.where(img.alpha_mask > 0, arr, np.nan)

    rows, cols = arr.shape
    transform = from_bounds(minx, miny, maxx, maxy, cols, rows)
    inside = geometry_mask(
        [watershed_geom],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
        all_touched=False,  # tighter watershed silhouette
    )
    arr = np.where(inside, arr, np.nan)

    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        raise ValueError("No valid DEM pixels in watershed")

    # Soften single-pixel DEM noise, then cap outliers so one cell can't form a needle.
    arr = _smooth_valid(arr, inside=np.isfinite(arr))
    valid = arr[np.isfinite(arr)]
    p_lo = float(np.percentile(valid, 2))
    p_hi = float(np.percentile(valid, 98))
    if p_hi <= p_lo:
        p_lo = float(np.nanmin(valid))
        p_hi = float(np.nanmax(valid))
        if p_hi <= p_lo:
            p_hi = p_lo + 1.0

    arr = np.clip(arr, p_lo, p_hi)
    mask = np.isfinite(arr)
    elev_min = p_lo
    elev_max = p_hi

    # null outside watershed — Plotly Surface treats null as holes (watershed shape)
    elevations: list[list[float | None]] = []
    for r in range(arr.shape[0]):
        row: list[float | None] = []
        for c in range(arr.shape[1]):
            if mask[r, c]:
                row.append(round(float(arr[r, c]), 1))
            else:
                row.append(None)
        elevations.append(row)

    return {
        "cols": int(arr.shape[1]),
        "rows": int(arr.shape[0]),
        "elevations": elevations,
        "mask": mask.astype(np.uint8).tolist(),
        "bounds": [float(minx), float(miny), float(maxx), float(maxy)],
        "elev_min": elev_min,
        "elev_max": elev_max,
        "max_size": max_size,
    }


def _smooth_valid(arr: np.ndarray, *, inside: np.ndarray) -> np.ndarray:
    """Gaussian-ish smooth on valid cells only (preserves NaN outside)."""
    out = arr.astype(np.float32, copy=True)
    try:
        from scipy.ndimage import gaussian_filter

        filled = _fill_nearest(arr)
        # Stronger blur so Plotly surface isn't faceted/spiky
        smooth = gaussian_filter(filled, sigma=1.25, mode="nearest")
        out = np.where(inside, 0.35 * arr + 0.65 * smooth, np.nan).astype(np.float32)
        return out
    except Exception:
        try:
            from scipy.ndimage import uniform_filter

            filled = _fill_nearest(arr)
            smooth = uniform_filter(filled, size=5, mode="nearest")
            out = np.where(inside, 0.35 * arr + 0.65 * smooth, np.nan).astype(np.float32)
            return out
        except Exception:
            return out


def _fill_nearest(arr: np.ndarray) -> np.ndarray:
    """Replace NaN with nearest finite elevation (for smoothing helper only)."""
    out = arr.astype(np.float32, copy=True)
    mask = ~np.isfinite(out)
    if not mask.any():
        return out
    if mask.all():
        return np.zeros_like(out)

    try:
        from rasterio.fill import fillnodata

        filled = fillnodata(out, mask=~mask, max_search_distance=max(out.shape))
        remaining = ~np.isfinite(filled)
        if remaining.any():
            filled = np.where(remaining, float(np.nanmean(out[~mask])), filled)
        return filled.astype(np.float32)
    except Exception:
        pass

    try:
        from scipy.ndimage import distance_transform_edt

        indices = distance_transform_edt(mask, return_distances=False, return_indices=True)
        return out[tuple(indices)]
    except Exception:
        fill_val = float(np.nanmean(out[~mask]))
        return np.where(mask, fill_val, out).astype(np.float32)


def get_cached_dem_mesh(project_id: str, cog_url: str, watershed_geom: dict, nodata) -> dict[str, Any]:
    if project_id in _MESH_CACHE:
        return _MESH_CACHE[project_id]
    mesh = build_dem_mesh(cog_url, watershed_geom, nodata=nodata)
    if len(_MESH_CACHE) >= _MESH_CACHE_MAX:
        _MESH_CACHE.clear()
    _MESH_CACHE[project_id] = mesh
    return mesh


def _png_rgba(rgba: np.ndarray) -> bytes:
    """Encode HxWx4 uint8 array as PNG."""
    from PIL import Image

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _categorical_color_lut(layer_cfg: LayerConfig, max_val: int = 255) -> np.ndarray:
    """Build (max_val+1, 4) LUT. Range classes color all values until the next break."""
    lut = np.zeros((max_val + 1, 4), dtype=np.uint8)
    entries = []
    for e in layer_cfg.classes:
        if e.value is None:
            continue
        try:
            v = int(e.value)
        except (TypeError, ValueError):
            continue
        if layer_cfg.nodata is not None and v == int(layer_cfg.nodata):
            continue
        entries.append((v, _hex_to_rgba_safe(e.color)))
    entries.sort(key=lambda t: t[0])
    if not entries:
        return lut
    for i, (v, rgba) in enumerate(entries):
        end = entries[i + 1][0] if i + 1 < len(entries) else max_val + 1
        for k in range(v, min(end, max_val + 1)):
            lut[k] = rgba
    return lut


def _colorize_cog_array(
    arr: np.ndarray,
    layer_cfg: LayerConfig,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """Return HxWx4 RGBA from raster values."""
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    if layer_cfg.render_type == "continuous":
        try:
            from rio_tiler.colormap import cmap as rio_cmaps

            cmap = rio_cmaps.get(str(layer_cfg.continuous.get("colormap") or "gist_earth"))
        except Exception:
            cmap = None
        valid_px = arr[valid_mask]
        if valid_px.size < 4:
            return rgba
        # Match mesh scaling: 2nd–98th percentile so colour and height agree.
        lo = float(np.percentile(valid_px, 2))
        hi = float(np.percentile(valid_px, 98))
        if hi <= lo:
            lo = float(np.nanmin(valid_px))
            hi = float(np.nanmax(valid_px))
            if hi <= lo:
                hi = lo + 1.0
        scaled = np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
        if cmap is not None:
            lut = np.zeros((256, 4), dtype=np.uint8)
            for i in range(256):
                lut[i] = cmap.get(i, (0, 0, 0, 0))
            rgba = lut[scaled]
        else:
            rgba[..., 0] = scaled
            rgba[..., 1] = scaled
            rgba[..., 2] = scaled
            rgba[..., 3] = 255
        rgba[~valid_mask, 3] = 0
        return rgba

    # Categorical (and default)
    max_needed = int(np.nanmax(arr[valid_mask])) if valid_mask.any() else 255
    lut = _categorical_color_lut(layer_cfg, max_val=max(255, max_needed))
    clipped = np.clip(arr.astype(np.int32), 0, len(lut) - 1)
    rgba = lut[clipped]
    rgba[~valid_mask, 3] = 0
    return rgba


def render_cog_drape(
    cog_url: str,
    watershed_geom: dict,
    layer_cfg: LayerConfig,
    *,
    cols: int,
    rows: int,
    bounds: list[float],
) -> bytes:
    from rio_tiler.io import Reader

    west, south, east, north = bounds
    with Reader(cog_url) as src:
        # Force exact output size to match DEM mesh
        img = src.part(
            [west, south, east, north],
            indexes=[1],
            height=rows,
            width=cols,
            dst_crs="EPSG:4326",
            bounds_crs="EPSG:4326",
        )

    arr = img.array[0].astype(np.float32)
    nodata = layer_cfg.nodata
    if nodata is not None:
        valid = arr != nodata
    else:
        valid = np.ones(arr.shape, dtype=bool)
    if img.alpha_mask is not None:
        valid &= img.alpha_mask > 0

    transform = from_bounds(west, south, east, north, cols, rows)
    ws_mask = geometry_mask(
        [watershed_geom],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
        all_touched=True,
    )
    valid &= ws_mask

    rgba = _colorize_cog_array(arr, layer_cfg, valid)
    return _png_rgba(rgba)


def _prepare_style_column(gdf, layer_cfg: LayerConfig):
    """Normalize vector attributes to style_column (mirrors frontend normalizeVectorFeatures)."""
    column = layer_cfg.style_column
    if not column:
        return gdf, None
    gdf = gdf.copy()
    atype = layer_cfg.analysis_type or ""

    if column in gdf.columns and gdf[column].notna().any():
        if atype == "wiser_gw_stress":
            gdf[column] = gdf[column].apply(_normalize_gw)
        elif atype == "wiser_rank":
            gdf[column] = gdf[column].apply(_normalize_rank)
        return gdf, column

    if atype == "wiser_gw_stress":
        col = _find_column(
            gdf,
            "__wiser_gw_stress_class",
            "category",
            search_terms=("category", "gw", "groundwater", "stress", "stage", "status"),
        )
        if col:
            gdf[column] = gdf[col].apply(_normalize_gw)
    elif atype == "wiser_rank":
        # Match frontend: each WISER rank layer has its own source column
        if column == "__wiser_irrigation_access_class":
            preferred = ("Irr_access", column)
        elif column == "__wiser_kharif_resilience_class":
            preferred = ("Kharif_res", column)
        elif column == "__wiser_rabi_resilience_class":
            preferred = ("Rabi_res", column)
        else:
            preferred = (column, "Irr_access", "Kharif_res", "Rabi_res")
        col = _find_column(gdf, *preferred)
        if col:
            gdf[column] = gdf[col].apply(_normalize_rank)
    elif atype == "aquifers":
        col = _find_column(gdf, "aquifer", "Major_Aqui", "aquifers")
        if col:
            gdf[column] = gdf[col].astype(str)
    elif atype == "demographics_marginalized" or column == "pct_scst":
        if "pct_scst" not in gdf.columns:
            sc = _find_column(gdf, "Total_SC_P", "SC")
            st = _find_column(gdf, "Total_ST_P", "ST")
            pop = _find_column(gdf, "Total_Popu", "TOT_P", "population")
            if sc and st and pop:
                pop_v = gdf[pop].replace(0, np.nan)
                gdf[column] = ((gdf[sc].fillna(0) + gdf[st].fillna(0)) / pop_v) * 100
            else:
                gdf[column] = np.nan
    elif column and column not in gdf.columns:
        # leave missing — rasterize will use default
        pass

    return gdf, column if column in gdf.columns else None


def render_vector_drape(
    s3_key: str,
    watershed_geom: dict,
    layer_cfg: LayerConfig,
    *,
    cols: int,
    rows: int,
    bounds: list[float],
) -> bytes:
    west, south, east, north = bounds
    bbox = _watershed_bbox(watershed_geom)
    gdf = _read_vector_gdf_bbox(s3_key, bbox)
    clipped = _clip_to_watershed(gdf, watershed_geom)
    if clipped.empty:
        return _png_rgba(np.zeros((rows, cols, 4), dtype=np.uint8))

    clipped, column = _prepare_style_column(clipped, layer_cfg)
    transform = from_bounds(west, south, east, north, cols, rows)

    rgba = np.zeros((rows, cols, 4), dtype=np.uint8)
    default_color = (180, 180, 180, 200)

    if layer_cfg.render_type == "choropleth" and layer_cfg.choropleth_stops and column:
        shapes = []
        for _, row in clipped.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            try:
                val = float(row[column])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(val):
                continue
            color = default_color
            for stop in layer_cfg.choropleth_stops:
                if stop.min <= val < stop.max:
                    color = _hex_to_rgba_safe(stop.color)
                    break
            else:
                last = layer_cfg.choropleth_stops[-1]
                if val >= last.min:
                    color = _hex_to_rgba_safe(last.color)
            shapes.append((geom, color))

        # Rasterize each color separately (rasterize takes single fill value)
        for geom, color in shapes:
            band = rasterize(
                [(geom, 1)],
                out_shape=(rows, cols),
                transform=transform,
                fill=0,
                dtype=np.uint8,
                all_touched=True,
            )
            mask = band > 0
            rgba[mask] = color

    elif layer_cfg.render_type == "categorical" and column:
        color_map: dict[str, tuple[int, int, int, int]] = {}
        for e in layer_cfg.classes:
            if e.value is None:
                continue
            color_map[str(e.value)] = _hex_to_rgba_safe(e.color)

        for _, row in clipped.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            key = str(row[column]) if row[column] is not None else ""
            color = color_map.get(key) or color_map.get("Other") or color_map.get("Unclassified") or default_color
            band = rasterize(
                [(geom, 1)],
                out_shape=(rows, cols),
                transform=transform,
                fill=0,
                dtype=np.uint8,
                all_touched=True,
            )
            rgba[band > 0] = color
    else:
        # Flat fill
        geoms = [(g, 1) for g in clipped.geometry if g is not None and not g.is_empty]
        if geoms:
            band = rasterize(
                geoms,
                out_shape=(rows, cols),
                transform=transform,
                fill=0,
                dtype=np.uint8,
                all_touched=True,
            )
            rgba[band > 0] = default_color

    # Clip to watershed
    ws_mask = geometry_mask(
        [watershed_geom],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
        all_touched=True,
    )
    rgba[~ws_mask, 3] = 0
    return _png_rgba(rgba)


def get_cached_drape(
    cache_key: tuple[str, str],
    builder,
) -> bytes:
    cached = _DRAPE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    png = builder()
    if len(_DRAPE_CACHE) >= _DRAPE_CACHE_MAX:
        _DRAPE_CACHE.clear()
    _DRAPE_CACHE[cache_key] = png
    return png


def _hex_color(color: str) -> str:
    c = str(color or "#888888")
    if c.startswith("#"):
        return c[:7] if len(c) >= 7 else c
    return f"#{c}"


def _is_skip_class_label(label: str) -> bool:
    lbl = str(label or "").strip().lower()
    return (
        not lbl
        or "background" in lbl
        or "no data" in lbl
        or lbl == "nodata"
    )


def _stepped_colorscale(colors: list[str]) -> list[list]:
    """Clinton-style hard steps so each class gets a flat colour band."""
    n = len(colors)
    if n == 0:
        return [[0.0, "#cccccc"], [1.0, "#cccccc"]]
    if n == 1:
        return [[0.0, colors[0]], [1.0, colors[0]]]
    scale: list[list] = []
    for i, c in enumerate(colors):
        scale.append([i / n, c])
        scale.append([(i + 1) / n, c])
    return scale


def _grid_to_json(values: np.ndarray) -> list[list[float | None]]:
    rows, cols = values.shape
    out: list[list[float | None]] = []
    for r in range(rows):
        row: list[float | None] = []
        for c in range(cols):
            v = values[r, c]
            row.append(None if not np.isfinite(v) else float(v))
        out.append(row)
    return out


def _sample_cog_to_mesh(
    cog_url: str,
    *,
    bounds: list[float],
    cols: int,
    rows: int,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Sample a COG onto the DEM mesh grid (EPSG:4326, same size/bounds)."""
    from rio_tiler.io import Reader

    west, south, east, north = bounds
    with Reader(cog_url) as src:
        img = src.part(
            [west, south, east, north],
            indexes=[1],
            height=rows,
            width=cols,
            dst_crs="EPSG:4326",
            bounds_crs="EPSG:4326",
        )
    arr = img.array[0].astype(np.float64)
    alpha = img.alpha_mask if img.alpha_mask is not None else None
    return arr, alpha


def render_drape_grid(
    *,
    watershed_geom: dict,
    layer_cfg: LayerConfig,
    cols: int,
    rows: int,
    bounds: list[float],
    cog_url: str | None = None,
    elev_grid: np.ndarray | None = None,
) -> dict[str, Any]:
    """Clinton-style Plotly surfacecolor grid aligned 1:1 with the DEM mesh.

    Returns north-up grids (same row order as ``build_dem_mesh`` elevations).
    The client applies ``flipud`` for Plotly, matching clinton_code.
    """
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, cols, rows)
    ws_mask = geometry_mask(
        [watershed_geom],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
        all_touched=True,
    )

    # DEM is the base surface — no overlay drape values needed.
    if layer_cfg.id == "dem" or layer_cfg.analysis_type == "dem":
        if elev_grid is None:
            raise ValueError("elev_grid required for DEM")
        values = np.where(ws_mask & np.isfinite(elev_grid), elev_grid.astype(np.float64), np.nan)
        valid = values[np.isfinite(values)]
        cmin = float(np.nanmin(valid)) if valid.size else 0.0
        cmax = float(np.nanmax(valid)) if valid.size else 1.0
        if cmax <= cmin:
            cmax = cmin + 1.0
        return {
            "values": _grid_to_json(values),
            "colorscale": "Earth",
            "cmin": cmin,
            "cmax": cmax,
            "title": "Elevation (m)",
            "value_type": "dem",
            "category_labels": [],
        }

    if layer_cfg.source == "cog" and cog_url:
        arr, alpha = _sample_cog_to_mesh(cog_url, bounds=bounds, cols=cols, rows=rows)
        nodata = layer_cfg.nodata
        valid = ws_mask.copy()
        if nodata is not None:
            valid &= arr != float(nodata)
        if alpha is not None:
            valid &= alpha > 0
        # Drop absurd fill / empty
        valid &= np.isfinite(arr)

        if layer_cfg.render_type == "categorical" and layer_cfg.classes:
            # Clinton: only classes present in the watershed; skip Background/No Data
            class_by_val: dict[int, tuple[str, str]] = {}
            for e in layer_cfg.classes:
                if e.value is None:
                    continue
                if layer_cfg.nodata is not None and e.value == layer_cfg.nodata:
                    continue
                if _is_skip_class_label(e.label):
                    continue
                try:
                    class_by_val[int(e.value)] = (e.label, _hex_color(e.color))
                except (TypeError, ValueError):
                    continue

            mapped = np.full((rows, cols), np.nan, dtype=np.float64)
            colors: list[str] = []
            labels: list[str] = []

            if layer_cfg.analysis_type == "jrc_occurrence":
                # Class values are lower bounds of percentage ranges
                breaks = sorted(class_by_val.keys())
                for i, b in enumerate(breaks):
                    hi = breaks[i + 1] if i + 1 < len(breaks) else None
                    pix = valid & (arr >= b)
                    if hi is not None:
                        pix &= arr < hi
                    if not pix.any():
                        continue
                    mapped[pix] = float(len(colors))
                    lbl, hex_c = class_by_val[b]
                    colors.append(hex_c)
                    labels.append(lbl)
            else:
                # Exact class IDs (LULC, JRC transitions, etc.)
                grouped: dict[tuple[str, str], np.ndarray] = {}
                sample = arr[valid]
                if sample.size:
                    for raw_f in np.unique(sample):
                        if not np.isfinite(raw_f):
                            continue
                        raw = int(raw_f)
                        if raw not in class_by_val:
                            continue
                        key = class_by_val[raw]
                        if key not in grouped:
                            grouped[key] = np.zeros((rows, cols), dtype=bool)
                        grouped[key] |= valid & (arr == raw)
                for (lbl, hex_c), mask in grouped.items():
                    mapped[mask] = float(len(colors))
                    colors.append(hex_c)
                    labels.append(lbl)

            n = len(colors)
            return {
                "values": _grid_to_json(mapped),
                "colorscale": _stepped_colorscale(colors),
                "cmin": -0.5 if n else 0.0,
                "cmax": float(n - 0.5) if n else 1.0,
                "title": layer_cfg.name,
                "value_type": "categorical",
                "category_labels": labels,
            }

        # Continuous COG
        masked = np.where(valid, arr, np.nan)
        if not np.isfinite(masked).any():
            return {
                "values": _grid_to_json(masked),
                "colorscale": "Viridis",
                "cmin": 0.0,
                "cmax": 1.0,
                "title": layer_cfg.name,
                "value_type": "continuous",
                "category_labels": [],
            }
        lo = float(np.nanpercentile(masked, 2))
        hi = float(np.nanpercentile(masked, 98))
        if hi <= lo:
            hi = lo + 1.0
        return {
            "values": _grid_to_json(masked),
            "colorscale": "Viridis",
            "cmin": lo,
            "cmax": hi,
            "title": layer_cfg.name,
            "value_type": "continuous",
            "category_labels": [],
        }

    # Vector: rasterize style values onto the DEM mesh grid
    if layer_cfg.source == "vector_fgb":
        bbox = _watershed_bbox(watershed_geom)
        gdf = _read_vector_gdf_bbox(layer_cfg.s3_key, bbox)
        clipped = _clip_to_watershed(gdf, watershed_geom)
        empty = {
            "values": [[None] * cols for _ in range(rows)],
            "colorscale": [[0.0, "#cccccc"], [1.0, "#cccccc"]],
            "cmin": 0.0,
            "cmax": 1.0,
            "title": layer_cfg.name,
            "value_type": "categorical",
            "category_labels": [],
        }
        if clipped.empty:
            return empty

        clipped, column = _prepare_style_column(clipped, layer_cfg)

        if layer_cfg.render_type == "choropleth" and layer_cfg.choropleth_stops and column:
            stops = layer_cfg.choropleth_stops
            # Rasterize continuous values, then bin to stop indices (Clinton discrete look)
            shapes = []
            for _, row in clipped.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                try:
                    val = float(row[column])
                except (TypeError, ValueError):
                    continue
                if not np.isfinite(val):
                    continue
                shapes.append((geom, val))
            values = np.full((rows, cols), np.nan, dtype=np.float64)
            if shapes:
                band = rasterize(
                    shapes,
                    out_shape=(rows, cols),
                    transform=transform,
                    fill=_SENTINEL,
                    dtype=np.float64,
                    all_touched=True,
                )
                values = np.where(ws_mask & (band != _SENTINEL), band, np.nan)

            mapped = np.full((rows, cols), np.nan, dtype=np.float64)
            colors: list[str] = []
            labels: list[str] = []
            for i, stop in enumerate(stops):
                pix = np.isfinite(values) & (values >= float(stop.min))
                if i < len(stops) - 1:
                    pix &= values < float(stop.max)
                if not pix.any():
                    continue
                mapped[pix] = float(len(colors))
                colors.append(_hex_color(stop.color))
                labels.append(stop.label)
            n = len(colors)
            return {
                "values": _grid_to_json(mapped),
                "colorscale": _stepped_colorscale(colors),
                "cmin": -0.5 if n else 0.0,
                "cmax": float(n - 0.5) if n else 1.0,
                "title": layer_cfg.name,
                "value_type": "categorical",
                "category_labels": labels,
            }

        if layer_cfg.render_type == "categorical" and column:
            entries = [
                e
                for e in layer_cfg.classes
                if e.value is not None and not _is_skip_class_label(e.label)
            ]
            # Only classes present in the watershed (Clinton)
            present: dict[str, tuple[str, str]] = {}
            for _, row in clipped.iterrows():
                key = str(row[column]) if row[column] is not None else ""
                if not key:
                    continue
                match = next((e for e in entries if str(e.value) == key), None)
                if match is None:
                    # try case-insensitive
                    match = next(
                        (e for e in entries if str(e.value).lower() == key.lower()),
                        None,
                    )
                if match is None:
                    continue
                present[str(match.value)] = (match.label, _hex_color(match.color))

            label_to_idx = {k: i for i, k in enumerate(present.keys())}
            shapes = []
            for _, row in clipped.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                key = str(row[column]) if row[column] is not None else ""
                if key not in label_to_idx:
                    # case-insensitive fallback
                    hit = next((k for k in label_to_idx if k.lower() == key.lower()), None)
                    if hit is None:
                        continue
                    key = hit
                shapes.append((geom, float(label_to_idx[key])))
            values = np.full((rows, cols), np.nan, dtype=np.float64)
            if shapes:
                band = rasterize(
                    shapes,
                    out_shape=(rows, cols),
                    transform=transform,
                    fill=_SENTINEL,
                    dtype=np.float64,
                    all_touched=True,
                )
                values = np.where(ws_mask & (band != _SENTINEL), band, np.nan)
            colors = [c for (_, c) in present.values()]
            labels = [lbl for (lbl, _) in present.values()]
            n = len(colors)
            return {
                "values": _grid_to_json(values),
                "colorscale": _stepped_colorscale(colors),
                "cmin": -0.5 if n else 0.0,
                "cmax": float(n - 0.5) if n else 1.0,
                "title": layer_cfg.name,
                "value_type": "categorical",
                "category_labels": labels,
            }

        return empty

    return {
        "values": [[None] * cols for _ in range(rows)],
        "colorscale": [[0.0, "#cccccc"], [1.0, "#cccccc"]],
        "cmin": 0.0,
        "cmax": 1.0,
        "title": layer_cfg.name,
        "value_type": "categorical",
        "category_labels": [],
    }


def get_cached_drape_grid(
    cache_key: tuple[str, str],
    builder,
) -> dict[str, Any]:
    cached = _DRAPE_GRID_CACHE.get(cache_key)
    if cached is not None:
        return cached
    grid = builder()
    if len(_DRAPE_GRID_CACHE) >= _DRAPE_GRID_CACHE_MAX:
        _DRAPE_GRID_CACHE.clear()
    _DRAPE_GRID_CACHE[cache_key] = grid
    return grid


def clear_terrain_caches() -> None:
    _MESH_CACHE.clear()
    _DRAPE_CACHE.clear()
    _DRAPE_GRID_CACHE.clear()


def encode_terrarium(elev: np.ndarray) -> np.ndarray:
    """Encode elevation metres to Terrarium RGB (MapLibre ``encoding: 'terrarium'``)."""
    h = elev.astype(np.float64) + 32768.0
    h = np.clip(h, 0.0, 65535.999)
    r = np.floor(h / 256.0)
    g = np.floor(np.mod(h, 256.0))
    b = np.floor((h - np.floor(h)) * 256.0)
    return np.dstack([r, g, b]).astype(np.uint8)


def render_terrarium_tile(
    cog_url: str,
    z: int,
    x: int,
    y: int,
    *,
    nodata: float | int | None = -9999,
    tilesize: int = 256,
) -> bytes:
    """DEM tile as Terrarium RGB PNG for MapLibre raster-dem terrain."""
    from rio_tiler.io import Reader
    from PIL import Image

    with Reader(cog_url) as src:
        img = src.tile(x, y, z, tilesize=tilesize, indexes=[1])

    arr = img.array[0].astype(np.float32)
    valid = np.ones(arr.shape, dtype=bool)
    if nodata is not None:
        valid &= arr != float(nodata)
    valid &= arr > -500  # allow slight negatives; drop absurd nodata
    if img.alpha_mask is not None:
        valid &= img.alpha_mask > 0

    # Invalid → 0 m so MapLibre gets a defined elevation (flat).
    elev = np.where(valid, arr, 0.0)
    rgb = encode_terrarium(elev)
    buf = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
