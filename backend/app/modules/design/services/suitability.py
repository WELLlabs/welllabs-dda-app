"""Site-suitability engine for Design solutions.

For one AOI, inputs are read once onto a shared WGS84 grid and every solution
in the catalog is scored from those arrays:

* **slope** (degrees) — local path or GDAL path (``settings.design_slope_path``)
* **LULC 250k** class codes — S3 COG (``settings.design_lulc_s3_key``),
  resampled nearest-neighbour onto the slope grid
* **drainage lines** with Strahler ``ORDER`` — indexed FlatGeobuf
  (``settings.design_drainage_path``), read by AOI bbox

Area solutions (Areal/Point without a stream rule) → pixels inside the AOI
that satisfy slope ∧ LULC, vectorized to polygons.

Line solutions (Instream, any stream-order rule, or no GIS criteria at all) →
drainage reaches inside the AOI whose order is in range and whose sampled
slope/LULC pass, returned as lines.

Ranking score = % of AOI area (area solutions) or % of AOI stream length
(line solutions). Results are memoised per AOI.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import mapping, shape

from app.modules.design.services.solutions_catalog import (
    HARD_EXCLUDE_LULC,
    LULC_CLASS_LABELS,
    Solution,
    load_solutions,
)
from app.shared.config import settings

log = logging.getLogger(__name__)

# Native slope resolution (1 arc-second SRTM ≈ 30 m). The grid is capped so a
# very large AOI is read from an overview rather than at full resolution.
SLOPE_RES_DEG = 0.000269494585236
MAX_GRID_PX = 2048
# Display only: drop isolated suitable patches smaller than this many pixels.
MIN_PATCH_PX = 3
LULC_NODATA = 0
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LNG_EQ = 111_320.0
_CACHE_SIZE = 6


class SuitabilityInputError(RuntimeError):
    """A required input dataset is not configured or could not be read."""


# --------------------------------------------------------------------------- grid


@dataclass
class Grid:
    bounds: tuple[float, float, float, float]
    width: int
    height: int

    @property
    def dx(self) -> float:
        return (self.bounds[2] - self.bounds[0]) / self.width

    @property
    def dy(self) -> float:
        return (self.bounds[3] - self.bounds[1]) / self.height

    @property
    def transform(self):
        from rasterio.transform import from_bounds

        return from_bounds(*self.bounds, self.width, self.height)

    def pixel_area_m2(self) -> np.ndarray:
        """Per-row pixel area (m²), shape (height, 1)."""
        rows = np.arange(self.height)
        lat = self.bounds[3] - (rows + 0.5) * self.dy
        w = self.dx * _M_PER_DEG_LNG_EQ * np.cos(np.radians(lat))
        h = self.dy * _M_PER_DEG_LAT
        return (w * h)[:, None]

    def rowcol(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        col = np.floor((x - self.bounds[0]) / self.dx).astype(np.int64)
        row = np.floor((self.bounds[3] - y) / self.dy).astype(np.int64)
        inside = (col >= 0) & (col < self.width) & (row >= 0) & (row < self.height)
        return np.clip(row, 0, self.height - 1), np.clip(col, 0, self.width - 1), inside


def grid_for_aoi(aoi) -> Grid:
    minx, miny, maxx, maxy = aoi.bounds
    pad = SLOPE_RES_DEG
    bounds = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    w = max(1, math.ceil((bounds[2] - bounds[0]) / SLOPE_RES_DEG))
    h = max(1, math.ceil((bounds[3] - bounds[1]) / SLOPE_RES_DEG))
    scale = max(w, h) / MAX_GRID_PX
    if scale > 1:
        w = max(1, int(round(w / scale)))
        h = max(1, int(round(h / scale)))
    return Grid(bounds=bounds, width=w, height=h)


# --------------------------------------------------------------------------- inputs


def _lulc_path() -> str:
    if not settings.aws_s3_bucket:
        raise SuitabilityInputError("AWS_S3_BUCKET is not set — LULC cannot be read from the bucket")
    return f"s3://{settings.aws_s3_bucket}/{settings.design_lulc_s3_key.lstrip('/')}"


def _require_path(value: str, label: str, env: str) -> str:
    if not value:
        raise SuitabilityInputError(f"{label} is not configured (set {env})")
    if not value.startswith("/vsi") and "://" not in value and not Path(value).exists():
        raise SuitabilityInputError(f"{label} not found at {value} ({env})")
    return value


def _read_band(path: str, grid: Grid, *, label: str) -> np.ma.MaskedArray:
    from rasterio.crs import CRS
    from rio_tiler.io import Reader

    wgs84 = CRS.from_epsg(4326)
    try:
        with Reader(path) as src:
            img = src.part(
                grid.bounds,
                dst_crs=wgs84,
                bounds_crs=wgs84,
                indexes=1,
                width=grid.width,
                height=grid.height,
                max_size=None,
                resampling_method="nearest",
                reproject_method="nearest",
            )
    except Exception as exc:  # noqa: BLE001 — surface a readable cause to the client
        raise SuitabilityInputError(f"Could not read {label}: {exc}") from exc
    return img.array[0]


def read_slope(grid: Grid) -> np.ma.MaskedArray:
    path = _require_path(settings.design_slope_path, "Slope raster", "DESIGN_SLOPE_PATH")
    return _read_band(path, grid, label="slope raster")


def read_lulc(grid: Grid) -> np.ma.MaskedArray:
    return _read_band(_lulc_path(), grid, label="LULC raster")


def read_streams(aoi):
    """Drainage lines intersecting the AOI, clipped and exploded to LineStrings."""
    import geopandas as gpd

    path = _require_path(settings.design_drainage_path, "Drainage lines", "DESIGN_DRAINAGE_PATH")
    try:
        gdf = gpd.read_file(path, bbox=aoi.bounds, columns=["ORDER"])
    except Exception as exc:  # noqa: BLE001
        raise SuitabilityInputError(f"Could not read drainage lines: {exc}") from exc
    if gdf.empty:
        return np.empty(0, dtype=object), np.empty(0, dtype=np.int16)
    geoms = gdf.geometry.values.to_numpy() if hasattr(gdf.geometry.values, "to_numpy") else np.asarray(gdf.geometry)
    orders = gdf["ORDER"].fillna(0).astype(np.int16).to_numpy()
    shapely.prepare(aoi)
    hit = shapely.intersects(aoi, geoms)
    clipped = shapely.intersection(geoms[hit], aoi)
    orders = orders[hit]
    parts, idx = shapely.get_parts(clipped, return_index=True)
    is_line = shapely.get_type_id(parts) == 1  # LineString
    parts, idx = parts[is_line], idx[is_line]
    keep = shapely.length(parts) > 0
    return parts[keep], orders[idx[keep]]


# --------------------------------------------------------------------------- streams


@dataclass
class StreamSamples:
    """Drainage lines sampled at ~pixel spacing.

    Point arrays are concatenated across lines; ``seg_*`` arrays describe the
    segment from point i to i+1 within the same line.
    """

    x: np.ndarray
    y: np.ndarray
    slope: np.ndarray  # degrees, NaN outside data
    lulc: np.ndarray  # class code, 0 outside data
    line_id: np.ndarray
    order: np.ndarray  # per point (copied from its line)
    seg_start: np.ndarray  # index of the segment's first point
    seg_len_m: np.ndarray
    total_m: float

    @classmethod
    def empty(cls) -> "StreamSamples":
        z = np.empty(0)
        zi = np.empty(0, dtype=np.int64)
        return cls(z, z, z, zi, zi, zi, zi, z, 0.0)


def sample_streams(lines: np.ndarray, orders: np.ndarray, grid: Grid, slope, lulc) -> StreamSamples:
    if len(lines) == 0:
        return StreamSamples.empty()
    step = min(grid.dx, grid.dy)
    lengths = shapely.length(lines)
    counts = np.maximum(2, np.ceil(lengths / step).astype(np.int64) + 1)
    line_id = np.repeat(np.arange(len(lines)), counts)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    frac = (np.arange(len(line_id)) - starts[line_id]) / (counts[line_id] - 1)
    pts = shapely.line_interpolate_point(lines[line_id], frac, normalized=True)
    x, y = shapely.get_x(pts), shapely.get_y(pts)

    row, col, inside = grid.rowcol(x, y)
    s = np.where(np.ma.getmaskarray(slope)[row, col], np.nan, np.ma.getdata(slope)[row, col].astype(float))
    s[~inside] = np.nan
    if lulc is not None:
        lc = np.where(np.ma.getmaskarray(lulc)[row, col], LULC_NODATA, np.ma.getdata(lulc)[row, col]).astype(np.int64)
        lc[~inside] = LULC_NODATA
    else:
        lc = np.zeros(len(x), dtype=np.int64)

    same_line = line_id[1:] == line_id[:-1]
    seg_start = np.nonzero(same_line)[0]
    mid_lat = (y[seg_start] + y[seg_start + 1]) / 2
    dxm = (x[seg_start + 1] - x[seg_start]) * _M_PER_DEG_LNG_EQ * np.cos(np.radians(mid_lat))
    dym = (y[seg_start + 1] - y[seg_start]) * _M_PER_DEG_LAT
    seg_len = np.hypot(dxm, dym)
    return StreamSamples(
        x=x,
        y=y,
        slope=s,
        lulc=lc,
        line_id=line_id,
        order=orders[line_id].astype(np.int64),
        seg_start=seg_start,
        seg_len_m=seg_len,
        total_m=float(seg_len.sum()),
    )


def _point_pass(sol: Solution, st: StreamSamples) -> np.ndarray:
    ok = np.ones(len(st.x), dtype=bool)
    if sol.stream_order is not None:
        lo, hi = sol.stream_order
        ok &= (st.order >= lo) & (st.order <= hi)
    if sol.slope_deg is not None:
        lo, hi = sol.slope_deg
        with np.errstate(invalid="ignore"):
            ok &= (st.slope >= lo) & (st.slope <= hi)
    if sol.lulc_classes is not None:
        ok &= np.isin(st.lulc, list(sol.lulc_classes))
    return ok


def _segment_pass(sol: Solution, st: StreamSamples) -> np.ndarray:
    ok = _point_pass(sol, st)
    return ok[st.seg_start] & ok[st.seg_start + 1]


def _segment_aptness(sol: Solution, st: StreamSamples) -> np.ndarray:
    """Per-segment aptness in [0, 1]: the weaker of its two endpoints' slope margins."""
    m = slope_margin(sol, st.slope)
    return np.minimum(m[st.seg_start], m[st.seg_start + 1])


def _segments_to_lines(st: StreamSamples, seg_ok: np.ndarray, seg_cls: np.ndarray | None = None) -> dict[int, list]:
    """Merge consecutive passing segments of the same line (and aptness class) into runs.

    Returns {apt_class: [coords, ...]}; class 0 when no classes are given.
    """
    idx = st.seg_start[seg_ok]
    if idx.size == 0:
        return {}
    cls = seg_cls[seg_ok] if seg_cls is not None else np.zeros(idx.size, dtype=np.int64)
    # A run breaks when the next passing segment doesn't continue this one, or changes class.
    breaks = np.nonzero((np.diff(idx) != 1) | (np.diff(cls) != 0))[0] + 1
    out: dict[int, list] = {}
    for run, run_cls in zip(np.split(idx, breaks), np.split(cls, breaks)):
        pts = np.append(run, run[-1] + 1)
        out.setdefault(int(run_cls[0]), []).append(np.column_stack([st.x[pts], st.y[pts]]).round(6).tolist())
    return out


# --------------------------------------------------------------------------- aptness

APT_LABELS = {1: "Marginal", 2: "Fair", 3: "Good", 4: "Best"}


def slope_margin(sol: Solution, slope_deg: np.ndarray) -> np.ndarray:
    """How comfortably each slope value sits inside the solution's range, in [0, 1].

    1 = as far from the binding threshold(s) as the range allows; 0 = on the edge.
    A lower bound of 0 % is not a real threshold (slope can't go below it), so for
    '0–10 %' the flattest ground scores highest; for '5–15 %' the middle (10 %) does.
    No slope rule → 1 everywhere.
    """
    v = np.asarray(slope_deg, dtype=float)
    if sol.slope_deg is None:
        return np.ones_like(v)
    lo, hi = sol.slope_deg
    width = hi - lo
    if width <= 0:
        return np.ones_like(v)
    with np.errstate(invalid="ignore"):
        if lo <= 0:
            m = (hi - v) / width
        else:
            m = np.minimum(v - lo, hi - v) / (width / 2)
    return np.nan_to_num(np.clip(m, 0.0, 1.0), nan=0.0)


def aptness_class(score: np.ndarray) -> np.ndarray:
    """[0, 1] → 1..4 (Marginal, Fair, Good, Best) in equal quarters."""
    return np.clip(np.floor(np.asarray(score) * 4).astype(np.int64) + 1, 1, 4)


# --------------------------------------------------------------------------- areas


def _area_mask(sol: Solution, slope, lulc, aoi_mask: np.ndarray) -> np.ndarray:
    mask = aoi_mask.copy()
    if sol.slope_deg is not None:
        lo, hi = sol.slope_deg
        s = np.ma.getdata(slope)
        with np.errstate(invalid="ignore"):
            mask &= ~np.ma.getmaskarray(slope) & (s >= lo) & (s <= hi)
    if sol.lulc_classes is not None:
        if lulc is None:
            return np.zeros_like(mask)
        mask &= ~np.ma.getmaskarray(lulc) & np.isin(np.ma.getdata(lulc), list(sol.lulc_classes))
    elif lulc is not None:
        mask &= ~np.isin(np.ma.getdata(lulc), list(HARD_EXCLUDE_LULC))
    return mask


def _smooth3(a: np.ndarray) -> np.ndarray:
    """3×3 mean (edge-padded). SRTM slope is noisy on flat ground; grading on the
    smoothed surface gives coherent zones instead of pixel speckle. The pass/fail
    mask still uses the raw values."""
    p = np.pad(a, 1, mode="edge")
    h, w = a.shape
    return sum(p[i : i + h, j : j + w] for i in range(3) for j in range(3)) / 9.0


def _area_classes(sol: Solution, mask: np.ndarray, slope) -> np.ndarray:
    """uint8 raster: 0 outside the suitable mask, else aptness class 1..4."""
    s = np.ma.getdata(slope).astype(float)
    cls = aptness_class(slope_margin(sol, _smooth3(s)))
    return np.where(mask, cls, 0).astype(np.uint8)


def _mask_to_features(mask: np.ndarray, grid: Grid, sol_id: str) -> list[dict]:
    """The suitable mask as a single MultiPolygon feature (the map shows suitable / not suitable only).

    Vectorizing the binary mask rather than per-aptness-class patches gives far fewer
    polygon boundaries — faster to build and a much smaller payload.
    """
    from rasterio import features

    if not mask.any():
        return []
    on = mask.astype(np.uint8)
    # Drop isolated suitable specks (display only; metrics use the full mask).
    if MIN_PATCH_PX > 1:
        on = features.sieve(on, size=MIN_PATCH_PX, connectivity=8)
    polys = [shape(geom) for geom, _ in features.shapes(on, mask=on > 0, transform=grid.transform)]
    if not polys:
        return []
    tol = min(grid.dx, grid.dy) * 0.5
    # Simplify each polygon (vectorized) rather than one big MultiPolygon: the patches
    # from features.shapes never overlap, and this is ~7x faster on fragmented masks.
    arr = shapely.set_precision(shapely.simplify(np.array(polys, dtype=object), tol, preserve_topology=True), 1e-6)
    parts = [p for p in shapely.get_parts(arr) if p.geom_type == "Polygon" and not p.is_empty]
    if not parts:
        return []
    return [
        {
            "type": "Feature",
            "geometry": mapping(shapely.multipolygons(parts)),
            "properties": {"solution_id": sol_id, "kind": "area"},
        }
    ]


# --------------------------------------------------------------------------- context


@dataclass
class AoiContext:
    aoi: Any
    grid: Grid
    slope: np.ma.MaskedArray
    lulc: np.ma.MaskedArray | None
    lulc_error: str | None
    aoi_mask: np.ndarray
    pixel_area: np.ndarray
    aoi_area_m2: float
    streams: StreamSamples
    streams_error: str | None
    ranking: list[dict] | None = None
    stats: dict | None = None
    geojson: dict[str, dict] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _build_context(aoi) -> AoiContext:
    from rasterio import features

    grid = grid_for_aoi(aoi)
    slope = read_slope(grid)
    lulc_error = None
    try:
        lulc = read_lulc(grid)
    except SuitabilityInputError as exc:
        log.warning("Design suitability: %s", exc)
        lulc, lulc_error = None, str(exc)

    aoi_mask = features.geometry_mask([mapping(aoi)], (grid.height, grid.width), grid.transform, invert=True, all_touched=False)
    pixel_area = grid.pixel_area_m2()
    aoi_area = float((aoi_mask * pixel_area).sum())

    streams_error = None
    try:
        lines, orders = read_streams(aoi)
        streams = sample_streams(lines, orders, grid, slope, lulc)
    except SuitabilityInputError as exc:
        log.warning("Design suitability: %s", exc)
        streams, streams_error = StreamSamples.empty(), str(exc)

    return AoiContext(
        aoi=aoi,
        grid=grid,
        slope=slope,
        lulc=lulc,
        lulc_error=lulc_error,
        aoi_mask=aoi_mask,
        pixel_area=pixel_area,
        aoi_area_m2=aoi_area,
        streams=streams,
        streams_error=streams_error,
    )


_cache: "OrderedDict[str, AoiContext]" = OrderedDict()
_cache_guard = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}


def _aoi_key(aoi_geojson: dict) -> str:
    h = hashlib.sha1()
    h.update(shapely.to_wkb(shape(aoi_geojson), output_dimension=2))
    for part in (settings.design_slope_path, settings.design_drainage_path, settings.design_lulc_s3_key):
        h.update(part.encode())
    return h.hexdigest()


def get_context(aoi_geojson: dict) -> AoiContext:
    key = _aoi_key(aoi_geojson)
    with _cache_guard:
        ctx = _cache.get(key)
        if ctx is not None:
            _cache.move_to_end(key)
            return ctx
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:  # one build per AOI even under concurrent requests
        with _cache_guard:
            ctx = _cache.get(key)
        if ctx is None:
            aoi = shapely.make_valid(shape(aoi_geojson))
            aoi = shapely.force_2d(aoi)
            ctx = _build_context(aoi)
            if ctx.lulc_error or ctx.streams_error:
                # Don't pin a degraded result — retry the inputs on the next request
                # (e.g. drainage FGB still being built, or a transient S3 error).
                return ctx
            with _cache_guard:
                _cache[key] = ctx
                while len(_cache) > _CACHE_SIZE:
                    old, _ = _cache.popitem(last=False)
                    _key_locks.pop(old, None)
        return ctx


# --------------------------------------------------------------------------- public


def _evaluate(sol: Solution, ctx: AoiContext) -> dict:
    needs_lulc = sol.lulc_classes is not None
    if needs_lulc and ctx.lulc is None:
        return {"status": "unavailable", "message": ctx.lulc_error or "LULC unavailable", "score": 0.0}
    if sol.uses_streams:
        if ctx.streams_error:
            return {"status": "unavailable", "message": ctx.streams_error, "score": 0.0}
        st = ctx.streams
        seg_ok = _segment_pass(sol, st)
        seg_cls = aptness_class(_segment_aptness(sol, st))
        suitable_m = float(st.seg_len_m[seg_ok].sum())
        pct = 100.0 * suitable_m / st.total_m if st.total_m else 0.0
        classes = [
            {"apt": c, "label": APT_LABELS[c], "km": round(float(st.seg_len_m[seg_ok & (seg_cls == c)].sum()) / 1000, 2)}
            for c in APT_LABELS
        ]
        return {
            "status": "ok",
            "kind": "line",
            "suitable_km": round(suitable_m / 1000, 2),
            "total_km": round(st.total_m / 1000, 2),
            "pct": round(pct, 1),
            "score": pct,
            "classes": classes,
        }
    mask = _area_mask(sol, ctx.slope, ctx.lulc, ctx.aoi_mask)
    cls = _area_classes(sol, mask, ctx.slope)
    suitable_m2 = float((mask * ctx.pixel_area).sum())
    pct = 100.0 * suitable_m2 / ctx.aoi_area_m2 if ctx.aoi_area_m2 else 0.0
    classes = [
        {"apt": c, "label": APT_LABELS[c], "ha": round(float(((cls == c) * ctx.pixel_area).sum()) / 10_000, 1)}
        for c in APT_LABELS
    ]
    return {
        "status": "ok",
        "kind": "area",
        "suitable_ha": round(suitable_m2 / 10_000, 1),
        "total_ha": round(ctx.aoi_area_m2 / 10_000, 1),
        "pct": round(pct, 1),
        "score": pct,
        "classes": classes,
    }


def rank_solutions(aoi_geojson: dict) -> dict:
    """All catalog solutions with suitability metrics, most feasible first."""
    ctx = get_context(aoi_geojson)
    with ctx.lock:
        if ctx.ranking is None:
            rows = []
            for order, sol in enumerate(load_solutions()):
                metrics = _evaluate(sol, ctx)
                rows.append({**sol.to_dict(), "metrics": metrics, "_order": order})
            # Solutions with no GIS criteria always score 100 % — they say nothing about
            # feasibility, so they sit after every scored solution.
            rows.sort(
                key=lambda r: (
                    r["metrics"]["status"] != "ok",
                    not r["has_gis_criteria"],
                    -r["metrics"]["score"],
                    r["_order"],
                )
            )
            for r in rows:
                r.pop("_order")
            ctx.ranking = rows
    warnings = [w for w in (ctx.lulc_error, ctx.streams_error) if w]
    return {
        "solutions": ctx.ranking,
        "aoi_area_ha": round(ctx.aoi_area_m2 / 10_000, 1),
        "stream_km": round(ctx.streams.total_m / 1000, 2),
        "grid": {"width": ctx.grid.width, "height": ctx.grid.height, "res_m": round(ctx.grid.dy * _M_PER_DEG_LAT, 1)},
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- watershed stats

# Slope classes (percent rise) for the AOI summary — the catalog's rules are in %.
SLOPE_CLASSES_PCT: tuple[tuple[float, float, str], ...] = (
    (0, 3, "Flat"),
    (3, 8, "Gentle"),
    (8, 15, "Moderate"),
    (15, 30, "Steep"),
    (30, math.inf, "Very steep"),
)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, q * cum[-1])])


def _geodesic_shape(aoi) -> tuple[float, float]:
    """(area_m2, perimeter_m) on the WGS84 ellipsoid."""
    from pyproj import Geod

    area, perim = Geod(ellps="WGS84").geometry_area_perimeter(aoi)
    return abs(float(area)), float(perim)


def _slope_stats(ctx: AoiContext) -> dict:
    inside = ctx.aoi_mask & ~np.ma.getmaskarray(ctx.slope)
    deg = np.ma.getdata(ctx.slope)[inside].astype(float)
    weights = np.broadcast_to(ctx.pixel_area, ctx.aoi_mask.shape)[inside]
    finite = np.isfinite(deg)
    deg, weights = deg[finite], weights[finite]
    if deg.size == 0 or weights.sum() <= 0:
        return {"status": "unavailable", "message": "No slope data inside the AOI"}
    pct = np.tan(np.radians(deg)) * 100.0
    total = float(weights.sum())
    classes = []
    for lo, hi, label in SLOPE_CLASSES_PCT:
        sel = (pct >= lo) & (pct < hi)
        area = float(weights[sel].sum())
        classes.append(
            {
                "label": label,
                "range": f"{lo:g}–{hi:g} %" if math.isfinite(hi) else f"> {lo:g} %",
                "ha": round(area / 10_000, 1),
                "pct": round(100.0 * area / total, 1),
            }
        )
    return {
        "status": "ok",
        "mean_pct": round(float((pct * weights).sum() / total), 1),
        "median_pct": round(_weighted_quantile(pct, weights, 0.5), 1),
        "p90_pct": round(_weighted_quantile(pct, weights, 0.9), 1),
        "max_pct": round(float(pct.max()), 1),
        "classes": classes,
    }


def _lulc_stats(ctx: AoiContext) -> dict:
    if ctx.lulc is None:
        return {"status": "unavailable", "message": ctx.lulc_error or "LULC unavailable"}
    codes = np.ma.getdata(ctx.lulc).astype(np.int64)
    valid = ctx.aoi_mask & ~np.ma.getmaskarray(ctx.lulc) & (codes != LULC_NODATA)
    weights = np.broadcast_to(ctx.pixel_area, ctx.aoi_mask.shape)
    total = float(weights[valid].sum())
    if total <= 0:
        return {"status": "unavailable", "message": "No land-use data inside the AOI"}
    area_by_code = np.bincount(codes[valid], weights=weights[valid])
    classes = [
        {
            "code": int(code),
            "label": LULC_CLASS_LABELS.get(int(code), f"Class {code}"),
            "ha": round(float(area) / 10_000, 1),
            "pct": round(100.0 * float(area) / total, 1),
        }
        for code, area in enumerate(area_by_code)
        if area > 0
    ]
    classes.sort(key=lambda c: -c["ha"])
    return {"status": "ok", "classes": classes, "mapped_ha": round(total / 10_000, 1)}


def _drainage_stats(ctx: AoiContext, area_km2: float) -> dict:
    if ctx.streams_error:
        return {"status": "unavailable", "message": ctx.streams_error}
    st = ctx.streams
    total_km = st.total_m / 1000
    seg_order = st.order[st.seg_start] if st.seg_start.size else np.empty(0, dtype=np.int64)
    by_order = []
    for order in sorted({int(o) for o in seg_order}):
        km = float(st.seg_len_m[seg_order == order].sum()) / 1000
        by_order.append({"order": order, "km": round(km, 2), "pct": round(100.0 * km / total_km, 1) if total_km else 0.0})
    return {
        "status": "ok",
        "total_km": round(total_km, 2),
        "reaches": int(np.unique(st.line_id).size) if st.line_id.size else 0,
        "max_order": max((o["order"] for o in by_order), default=None),
        "density_km_per_km2": round(total_km / area_km2, 2) if area_km2 else None,
        "by_order": by_order,
    }


def aoi_stats(aoi_geojson: dict) -> dict:
    """Watershed-level summary of the three design inputs (slope, LULC, drainage) plus AOI shape."""
    ctx = get_context(aoi_geojson)
    with ctx.lock:
        if ctx.stats is None:
            area_m2, perim_m = _geodesic_shape(ctx.aoi)
            c = ctx.aoi.centroid
            minx, miny, maxx, maxy = ctx.aoi.bounds
            ctx.stats = {
                "watershed": {
                    "area_ha": round(area_m2 / 10_000, 1),
                    "perimeter_km": round(perim_m / 1000, 2),
                    "centroid": {"lng": round(float(c.x), 6), "lat": round(float(c.y), 6)},
                    "bounds": [round(v, 6) for v in (minx, miny, maxx, maxy)],
                    "parts": len(shapely.get_parts(ctx.aoi)),
                    "grid_res_m": round(ctx.grid.dy * _M_PER_DEG_LAT, 1),
                },
                "slope": _slope_stats(ctx),
                "lulc": _lulc_stats(ctx),
                "drainage": _drainage_stats(ctx, area_m2 / 1_000_000),
                "warnings": [w for w in (ctx.lulc_error, ctx.streams_error) if w],
            }
        return ctx.stats


def solution_geojson(aoi_geojson: dict, sol: Solution) -> dict:
    """FeatureCollection of the areas/reaches where ``sol`` is suitable inside the AOI."""
    ctx = get_context(aoi_geojson)
    with ctx.lock:
        cached = ctx.geojson.get(sol.id)
    if cached is not None:
        return cached

    metrics = _evaluate(sol, ctx)
    features_out: list[dict] = []
    if metrics["status"] == "ok":
        if sol.uses_streams:
            st = ctx.streams
            for coords in _segments_to_lines(st, _segment_pass(sol, st)).values():
                features_out.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "MultiLineString", "coordinates": coords},
                        "properties": {"solution_id": sol.id, "kind": "line"},
                    }
                )
        else:
            mask = _area_mask(sol, ctx.slope, ctx.lulc, ctx.aoi_mask)
            features_out.extend(_mask_to_features(mask, ctx.grid, sol.id))
    fc = {
        "type": "FeatureCollection",
        "features": features_out,
        "properties": {"solution_id": sol.id, "metrics": metrics},
    }
    with ctx.lock:
        ctx.geojson[sol.id] = fc
    return fc


# --------------------------------------------------------------------------- inspect

# A clicked point "is on" a stream if a sampled drainage point lies within this distance.
NEAR_STREAM_M = 60.0


def _pct(deg: float) -> float:
    return math.tan(math.radians(deg)) * 100.0


def _fmt_range(lo: float, hi: float, unit: str = "") -> str:
    return f"{lo:g}–{hi:g}{unit}" if lo != hi else f"{lo:g}{unit}"


def inspect_point(aoi_geojson: dict, sol: Solution, lng: float, lat: float) -> dict:
    """Explain how one location measures against ``sol``'s criteria."""
    from shapely.geometry import Point

    ctx = get_context(aoi_geojson)
    inside = bool(ctx.aoi.covers(Point(lng, lat)))
    row, col, in_grid = ctx.grid.rowcol(np.array([lng]), np.array([lat]))
    r, c, in_grid = int(row[0]), int(col[0]), bool(in_grid[0])

    slope_deg = None
    if in_grid and not np.ma.getmaskarray(ctx.slope)[r, c]:
        slope_deg = float(np.ma.getdata(ctx.slope)[r, c])
    lulc_code = None
    if in_grid and ctx.lulc is not None and not np.ma.getmaskarray(ctx.lulc)[r, c]:
        lulc_code = int(np.ma.getdata(ctx.lulc)[r, c])

    stream = None
    st = ctx.streams
    if len(st.x):
        dxm = (st.x - lng) * _M_PER_DEG_LNG_EQ * math.cos(math.radians(lat))
        dym = (st.y - lat) * _M_PER_DEG_LAT
        d = np.hypot(dxm, dym)
        i = int(np.argmin(d))
        if d[i] <= NEAR_STREAM_M:
            stream = {
                "order": int(st.order[i]),
                "distance_m": round(float(d[i])),
                "slope_deg": None if np.isnan(st.slope[i]) else float(st.slope[i]),
                "index": i,
            }

    # Line solutions are judged where the structure sits: on the nearest stream.
    on_stream = sol.uses_streams
    judged_slope = (stream or {}).get("slope_deg") if on_stream else slope_deg
    judged_lulc = int(st.lulc[stream["index"]]) if (on_stream and stream) else lulc_code

    checks: list[dict] = []
    if on_stream:
        checks.append(
            {
                "criterion": "On a drainage line",
                "rule": f"within {NEAR_STREAM_M:g} m",
                "value": f"{stream['distance_m']} m away" if stream else f"none within {NEAR_STREAM_M:g} m",
                "pass": stream is not None,
            }
        )
    if sol.stream_order is not None:
        lo, hi = sol.stream_order
        checks.append(
            {
                "criterion": "Stream order",
                "rule": _fmt_range(lo, hi),
                "value": str(stream["order"]) if stream else "—",
                "pass": bool(stream and lo <= stream["order"] <= hi),
            }
        )
    if sol.slope_pct is not None:
        lo, hi = sol.slope_pct
        ok = judged_slope is not None and sol.slope_deg[0] <= judged_slope <= sol.slope_deg[1]
        checks.append(
            {
                "criterion": "Slope" + (" (along stream)" if on_stream else ""),
                "rule": _fmt_range(lo, hi, " %"),
                "value": "no data" if judged_slope is None else f"{_pct(judged_slope):.1f} % ({judged_slope:.1f}°)",
                "pass": bool(ok),
            }
        )
    label = LULC_CLASS_LABELS.get(judged_lulc, "No data") if judged_lulc is not None else "No data"
    if sol.lulc_classes is not None:
        checks.append(
            {
                "criterion": "Land use",
                "rule": ", ".join(sol.lulc_terms),
                "value": label,
                "pass": judged_lulc in sol.lulc_classes if judged_lulc is not None else False,
            }
        )
    elif not on_stream and ctx.lulc is not None:
        checks.append(
            {
                "criterion": "Land use",
                "rule": "not built-up, water, rann or snow",
                "value": label,
                "pass": judged_lulc not in HARD_EXCLUDE_LULC,
            }
        )

    suitable = inside and all(ch["pass"] for ch in checks)
    aptness = None
    if suitable:
        score = float(slope_margin(sol, np.array([judged_slope if judged_slope is not None else np.nan]))[0])
        if sol.slope_deg is None:
            score = 1.0
        cls = int(aptness_class(np.array([score]))[0])
        aptness = {"score": round(score, 2), "apt": cls, "label": APT_LABELS[cls]}

    return {
        "lng": lng,
        "lat": lat,
        "inside_aoi": inside,
        "solution_id": sol.id,
        "solution_name": sol.name,
        "suitable": suitable,
        "aptness": aptness,
        "checks": checks,
        "context": {
            "slope_pct": None if slope_deg is None else round(_pct(slope_deg), 1),
            "lulc": LULC_CLASS_LABELS.get(lulc_code, "No data") if lulc_code is not None else None,
            "stream_order": stream["order"] if stream else None,
        },
    }
