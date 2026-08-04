"""Package project and upload to QField Cloud."""

import json
import logging
import math
import shutil
import sqlite3
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from qfieldcloud_sdk import sdk

from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage
from app.modules.diagnose.services.layer_catalog import (
    get_catalog,
    get_layer_for_key,
    display_name_for_key,
)
from app.modules.diagnose.services.package_progress import PackageProgress
from app.modules.diagnose.services.qgis_package import build_qfield_project_with_qgis
from app.modules.diagnose.services.s3_cleanup import cleanup_project_s3

logger = logging.getLogger(__name__)

MIN_RASTER_BYTES = 10_000


def _project_bounds(project_id: str) -> tuple[dict, list[float] | None]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, watershed_name,
                   ST_AsGeoJSON(watershed_geom)::json AS watershed_geojson,
                   ST_XMin(watershed_geom) AS xmin,
                   ST_YMin(watershed_geom) AS ymin,
                   ST_XMax(watershed_geom) AS xmax,
                   ST_YMax(watershed_geom) AS ymax
            FROM diagnosis WHERE id = %(id)s
            """,
            {"id": project_id},
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Project not found")
    extent = None
    if row["xmin"] is not None:
        extent = [row["xmin"], row["ymin"], row["xmax"], row["ymax"]]
    return row, extent


def _write_cutline(package_dir: Path, watershed_geojson: dict) -> Path:
    cutline = package_dir / "watershed.geojson"
    cutline.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                "features": [{"type": "Feature", "geometry": watershed_geojson}],
            }
        )
    )
    return cutline


def _target_dimensions(extent: list[float] | None, max_pixels: int) -> tuple[int, int]:
    """Size the clipped raster so the longest watershed side uses max_pixels."""
    if not extent or len(extent) != 4:
        return max_pixels, max_pixels

    width = max(abs(extent[2] - extent[0]), 1e-9)
    height = max(abs(extent[3] - extent[1]), 1e-9)
    if width >= height:
        ts_x = max_pixels
        ts_y = max(int(round(max_pixels * height / width)), 256)
    else:
        ts_y = max_pixels
        ts_x = max(int(round(max_pixels * width / height)), 256)
    return ts_x, ts_y


def _layer_name_from_key(key: str) -> str:
    basename = key.rsplit("/", 1)[-1]
    for ext in (".cog.tif", ".tif", ".tiff"):
        if basename.lower().endswith(ext):
            return basename[: -len(ext)]
    return basename.rsplit(".", 1)[0]


def _ogr_pg_dsn() -> str:
    parsed = urlparse(settings.database_url)
    return (
        f"PG:dbname={parsed.path.lstrip('/')} "
        f"host={parsed.hostname} port={parsed.port or 5432} "
        f"user={parsed.username} password={parsed.password}"
    )


def _fetch_zone_colors(project_id: str) -> list[str]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT color
            FROM observation_zones
            WHERE project_id = %(id)s AND color IS NOT NULL
            """,
            {"id": project_id},
        )
        return [row["color"] for row in cur.fetchall() if row["color"]]


def _export_vectors_gpkg(
    package_dir: Path, project_id: str, progress: PackageProgress | None = None
) -> tuple[Path, Path, Path]:
    """Export project vectors to separate GeoPackages (avoids fid/fid1 append artifacts)."""
    uuid.UUID(project_id)
    zones_gpkg = package_dir / "observation_zones.gpkg"
    notes_gpkg = package_dir / "field_notes.gpkg"
    hypotheses_gpkg = package_dir / "hypotheses.gpkg"
    legacy_gpkg = package_dir / "vectors.gpkg"
    for path in (zones_gpkg, notes_gpkg, hypotheses_gpkg, legacy_gpkg):
        if path.exists():
            path.unlink()

    dsn = _ogr_pg_dsn()
    _run_gdal(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            str(zones_gpkg),
            dsn,
            "-sql",
            (
                "SELECT id AS zone_id, project_id, text, observations, questions, color, geom "
                f"FROM observation_zones WHERE project_id = '{project_id}'"
            ),
            "-nln",
            "observation_zones",
            "-nlt",
            "MULTIPOLYGON",
            "-a_srs",
            "EPSG:4326",
        ],
        progress,
    )
    _run_gdal(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            str(notes_gpkg),
            dsn,
            "-sql",
            (
                "SELECT id AS note_id, project_id, title, text, photo_path, audio_path, "
                "hypothesis_id::text AS hypothesis_id, geom "
                f"FROM field_notes WHERE project_id = '{project_id}'"
            ),
            "-nln",
            "field_notes",
            "-nlt",
            "POINT",
            "-a_srs",
            "EPSG:4326",
        ],
        progress,
    )
    _run_gdal(
        [
            "ogr2ogr",
            "-f",
            "GPKG",
            str(hypotheses_gpkg),
            dsn,
            "-sql",
            (
                "SELECT id::text AS hypothesis_id, project_id, hypothesis, status "
                f"FROM hypotheses WHERE project_id = '{project_id}'"
            ),
            "-nln",
            "hypotheses",
            "-nlt",
            "NONE",
        ],
        progress,
    )
    if not zones_gpkg.is_file() or not notes_gpkg.is_file() or not hypotheses_gpkg.is_file():
        raise RuntimeError("GeoPackage export failed")

    _apply_gpkg_insert_defaults(zones_gpkg, "observation_zones", project_id)
    _apply_gpkg_insert_defaults(notes_gpkg, "field_notes", project_id)
    return zones_gpkg, notes_gpkg, hypotheses_gpkg


def _apply_gpkg_insert_defaults(gpkg_path: Path, table: str, project_id: str) -> None:
    """Ensure QField inserts always get project_id (Qgs defaults alone are unreliable on mobile)."""
    uuid.UUID(project_id)
    conn = sqlite3.connect(gpkg_path)
    try:
        conn.execute(f"DROP TRIGGER IF EXISTS {table}_set_project_id")
        conn.execute(
            f"""
            CREATE TRIGGER {table}_set_project_id
            AFTER INSERT ON {table}
            FOR EACH ROW
            WHEN NEW.project_id IS NULL OR trim(NEW.project_id) = ''
            BEGIN
                UPDATE {table}
                SET project_id = '{project_id}'
                WHERE fid = NEW.fid;
            END
            """
        )
        if table == "field_notes":
            conn.execute("DROP TRIGGER IF EXISTS field_notes_set_note_id")
            conn.execute(
                """
                CREATE TRIGGER field_notes_set_note_id
                AFTER INSERT ON field_notes
                FOR EACH ROW
                WHEN NEW.note_id IS NULL OR trim(NEW.note_id) = ''
                BEGIN
                    UPDATE field_notes
                    SET note_id = lower(hex(randomblob(16)))
                    WHERE fid = NEW.fid;
                END
                """
            )
        conn.commit()
    finally:
        conn.close()


def _run_gdal(cmd: list[str], progress: PackageProgress | None = None) -> None:
    label = Path(cmd[-1]).name if cmd else "gdal"
    logger.info("GDAL: %s", " ".join(cmd))
    if progress:
        progress.log(f"GDAL: {cmd[0]} → {label}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr or result.stdout
        if progress and detail:
            for line in detail.strip().splitlines()[-5:]:
                progress.log(line)
        raise RuntimeError(
            f"GDAL failed ({result.returncode}): {detail}"
        )
    if progress and result.stderr:
        for line in result.stderr.strip().splitlines():
            stripped = line.strip()
            if stripped and (
                stripped.endswith("%")
                or "done" in stripped.lower()
                or "error" in stripped.lower()
            ):
                progress.log(stripped)


def _validate_geotiff(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"GeoTIFF not created: {path}")
    size = path.stat().st_size
    logger.info("GeoTIFF %s: %d bytes", path.name, size)
    if size < MIN_RASTER_BYTES:
        raise RuntimeError(
            f"GeoTIFF for {path.name} looks empty ({size} bytes). "
            "Check COG_LAYERS, watershed geometry, and AWS read access."
        )


def _rio_colormap_palette(
    colormap_name: str = "gist_earth",
    *,
    steps: int = 32,
) -> list[tuple[float, int, int, int, int]]:
    """Sample rio-tiler colormap (same as Diagnose web tiles) into gdaldem stops."""
    try:
        from rio_tiler.colormap import cmap as rio_cmaps

        table = rio_cmaps.get(colormap_name)
    except Exception:
        try:
            from rio_tiler.colormap import cmap as rio_cmaps

            table = rio_cmaps.get("gist_earth")
        except Exception:
            # Offline fallback approximating gist_earth (blue → green → yellow → white)
            return [
                (0.00, 0, 0, 0, 255),
                (0.12, 21, 56, 120, 255),
                (0.25, 42, 115, 126, 255),
                (0.37, 59, 141, 98, 255),
                (0.50, 93, 160, 75, 255),
                (0.62, 153, 174, 88, 255),
                (0.75, 188, 170, 98, 255),
                (0.87, 218, 182, 159, 255),
                (1.00, 253, 250, 250, 255),
            ]

    palette: list[tuple[float, int, int, int, int]] = []
    last = max(steps - 1, 1)
    for i in range(steps):
        frac = i / last
        idx = int(round(frac * 255))
        rgba = table[idx]
        r, g, b = int(rgba[0]), int(rgba[1]), int(rgba[2])
        a = int(rgba[3]) if len(rgba) > 3 else 255
        palette.append((frac, r, g, b, a))
    return palette


def _write_continuous_color_file(
    path: Path,
    nodata: float | int | None = -9999,
    *,
    vmin: float | None = None,
    vmax: float | None = None,
    colormap_name: str = "gist_earth",
) -> None:
    """Write a DEM color ramp matching Diagnose web tiles (rio-tiler colormap).

    Stops are stretched across the watershed clip min/max so local relief uses the
    full ramp (same approach as tile rescale in layers.py).
    """
    palette = _rio_colormap_palette(colormap_name)
    lines: list[str] = []
    if nodata is not None:
        lines.append(f"{nodata} 0 0 0 0")

    if vmin is not None and vmax is not None and math.isfinite(vmin) and math.isfinite(vmax):
        lo, hi = float(vmin), float(vmax)
        if hi <= lo:
            hi = lo + 1.0
        span = hi - lo
        for frac, r, g, b, a in palette:
            elev = lo + frac * span
            lines.append(f"{elev:.6f} {r} {g} {b} {a}")
    else:
        for frac, r, g, b, a in palette:
            lines.append(f"{int(round(frac * 100))}% {r} {g} {b} {a}")

    lines.append("nv 0 0 0 0")
    path.write_text("\n".join(lines) + "\n")


def _dem_valid_mask(arr, nodata: float | int | None):
    """Mask valid elevation pixels — drop nodata and common cutline fill (0)."""
    import numpy as np

    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != float(nodata)
    # gdalwarp often leaves 0 outside the cutline even with -dstnodata; those zeros
    # previously pulled the color stretch to 0→max so real elevations looked beige.
    if nodata is not None and float(nodata) != 0.0 and arr.size:
        zero_frac = float((arr == 0).mean())
        if zero_frac > 0.01:
            valid &= arr != 0.0
    return valid


def _dem_minmax(path: Path, nodata: float | int | None) -> tuple[float, float] | None:
    """Return robust (p2, p98) elevation range for a DEM clip."""
    try:
        import numpy as np
        import rasterio
    except ImportError:
        return None
    with rasterio.open(path) as ds:
        arr = ds.read(1, masked=False).astype("float64")
    valid = _dem_valid_mask(arr, nodata)
    if not valid.any():
        return None
    vals = arr[valid]
    lo = float(np.percentile(vals, 2))
    hi = float(np.percentile(vals, 98))
    if not math.isfinite(lo) or not math.isfinite(hi):
        return None
    if hi <= lo:
        lo = float(vals.min())
        hi = float(vals.max())
        if hi <= lo:
            hi = lo + 1.0
    return lo, hi


def _colorize_continuous_geotiff(
    gray_tif: Path,
    rgba_tif: Path,
    *,
    nodata: float | int | None,
    colormap_name: str = "gist_earth",
) -> tuple[float, float]:
    """Colorize a single-band DEM clip like Diagnose web tiles (rio-tiler LUT + p2–p98)."""
    import numpy as np
    import rasterio
    from rasterio.enums import ColorInterp
    from rio_tiler.colormap import cmap as rio_cmaps

    with rasterio.open(gray_tif) as ds:
        arr = ds.read(1).astype(np.float32)
        profile = ds.profile.copy()

    valid = _dem_valid_mask(arr, nodata)
    if not valid.any():
        raise RuntimeError(f"DEM clip has no valid pixels: {gray_tif}")

    vals = arr[valid]
    lo = float(np.percentile(vals, 2))
    hi = float(np.percentile(vals, 98))
    if hi <= lo:
        lo = float(vals.min())
        hi = float(vals.max())
        if hi <= lo:
            hi = lo + 1.0

    scaled = np.zeros(arr.shape, dtype=np.uint8)
    scaled[valid] = np.clip((vals - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)

    try:
        table = rio_cmaps.get(colormap_name)
    except Exception:
        table = rio_cmaps.get("gist_earth")
    lut = np.zeros((256, 4), dtype=np.uint8)
    for i in range(256):
        rgba = table.get(i, (0, 0, 0, 255))
        lut[i, 0] = int(rgba[0])
        lut[i, 1] = int(rgba[1])
        lut[i, 2] = int(rgba[2])
        lut[i, 3] = int(rgba[3]) if len(rgba) > 3 else 255

    out = lut[scaled]
    out[~valid, 3] = 0

    profile.update(
        driver="GTiff",
        count=4,
        dtype="uint8",
        nodata=None,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        photometric="RGB",
    )
    for key in ("nbits", "pixeltype"):
        profile.pop(key, None)

    with rasterio.open(rgba_tif, "w", **profile) as dst:
        dst.write(out[:, :, 0], 1)
        dst.write(out[:, :, 1], 2)
        dst.write(out[:, :, 2], 3)
        dst.write(out[:, :, 3], 4)
        dst.colorinterp = (
            ColorInterp.red,
            ColorInterp.green,
            ColorInterp.blue,
            ColorInterp.alpha,
        )
    return lo, hi


def _clip_to_geotiff(
    src_vsis3: str,
    dest: Path,
    cutline: Path,
    colormap_file: Path | None,
    extent: list[float] | None,
    progress: PackageProgress | None = None,
    *,
    continuous: bool = False,
    nodata: float | int | None = None,
    colormap_name: str = "gist_earth",
) -> None:
    """Clip remote COG to watershed GeoTIFF (palette for categorical, ramp for continuous)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    work_dir = dest.parent / "_raster_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    gray_tif = work_dir / "clip_gray.tif"
    rgb_tif = work_dir / "clip_rgba.tif"
    ts_x, ts_y = _target_dimensions(extent, settings.qfield_raster_max_pixels)
    resample = "bilinear" if continuous else "near"

    warp_cmd = [
        "gdalwarp",
        "-cutline",
        str(cutline),
        "-cutline_srs",
        "EPSG:4326",
        "-crop_to_cutline",
        "-ts",
        str(ts_x),
        str(ts_y),
        "-r",
        resample,
        "-of",
        "GTiff",
    ]
    # Preserve nodata so DEM color stretch uses real elevations only
    if continuous and nodata is not None:
        warp_cmd.extend(["-dstnodata", str(nodata)])
    warp_cmd.extend([src_vsis3, str(gray_tif)])
    _run_gdal(warp_cmd, progress)

    # Continuous DEM: colorize like Diagnose web tiles (rio LUT + p2–p98).
    # Avoid gdaldem here — fill zeros were stretching the ramp so blues/greens vanished.
    if continuous:
        lo, hi = _colorize_continuous_geotiff(
            gray_tif,
            rgb_tif,
            nodata=nodata,
            colormap_name=colormap_name,
        )
        logger.info("DEM colorized with %s over %.1f–%.1f m", colormap_name, lo, hi)
        if progress:
            progress.log(f"DEM colored ({colormap_name}) for {lo:.0f}–{hi:.0f} m")
        if colormap_file is not None:
            _write_continuous_color_file(
                colormap_file,
                nodata=nodata,
                vmin=lo,
                vmax=hi,
                colormap_name=colormap_name,
            )
        translate_src = rgb_tif
        photometric = ["-co", "PHOTOMETRIC=RGB"]
    elif colormap_file is not None and colormap_file.is_file():
        _run_gdal(
            [
                "gdaldem",
                "color-relief",
                str(gray_tif),
                str(colormap_file),
                str(rgb_tif),
                "-alpha",
            ],
            progress,
        )
        translate_src = rgb_tif
        photometric = ["-co", "PHOTOMETRIC=RGB"]
    else:
        translate_src = gray_tif
        photometric = []

    _run_gdal(
        [
            "gdal_translate",
            "-of",
            "GTiff",
            "-co",
            "COMPRESS=DEFLATE",
            "-co",
            "TILED=YES",
            *photometric,
            str(translate_src),
            str(dest),
        ],
        progress,
    )
    _validate_geotiff(dest)
    _run_gdal(["gdaladdo", "-r", "average", str(dest), "2", "4", "8"], progress)
    shutil.rmtree(work_dir, ignore_errors=True)


def _prune_package_dir(package_dir: Path, project_name: str) -> None:
    """Keep only files that belong in the current QField / S3 package."""
    keep_names = {
        f"{project_name}.qgs",
        "observation_zones.gpkg",
        "field_notes.gpkg",
        "hypotheses.gpkg",
    }
    for path in package_dir.glob("*.tif"):
        keep_names.add(path.name)
    for path in package_dir.glob("*.tif.aux.xml"):
        keep_names.add(path.name)
    # Secondary / reference vectors clipped for the watershed
    for path in package_dir.glob("secondary_*.gpkg"):
        keep_names.add(path.name)

    for path in list(package_dir.iterdir()):
        if path.is_dir():
            logger.info("Pruning stale package directory: %s", path.name)
            shutil.rmtree(path, ignore_errors=True)
            continue
        if path.is_file() and path.name not in keep_names:
            logger.info("Pruning stale package file: %s", path.name)
            path.unlink(missing_ok=True)


def _cleanup_stale_rasters(package_dir: Path) -> None:
    """Remove leftovers from older packaging (full COGs in rasters_tmp, etc.)."""
    stale_tmp = package_dir / "rasters_tmp"
    if stale_tmp.exists():
        shutil.rmtree(stale_tmp)
    work_dir = package_dir / "_raster_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    legacy_gpkg = package_dir / "vectors.gpkg"
    if legacy_gpkg.exists():
        legacy_gpkg.unlink()
    for path in package_dir.glob("*.mbtiles"):
        path.unlink()
    for path in package_dir.glob("IndiaSat_*.gpkg"):
        path.unlink()
    for path in package_dir.glob("IndiaSat_*.tif"):
        path.unlink()
    for path in package_dir.glob("*_colors.txt"):
        path.unlink()
    for path in package_dir.glob("secondary_*.gpkg"):
        path.unlink(missing_ok=True)
    raster_dir = package_dir / "rasters"
    if raster_dir.exists():
        shutil.rmtree(raster_dir)


def _build_watershed_rasters(
    package_dir: Path,
    cutline: Path,
    extent: list[float] | None,
    progress: PackageProgress | None = None,
) -> list[dict]:
    """Clip all enabled COG layers. Returns [{filename, name}, ...]."""
    if not s3_storage.is_s3_enabled():
        return []

    raster_layers: list[dict] = []
    for key in settings.cog_layers.split(","):
        key = key.strip()
        if not key:
            continue
        stem = _layer_name_from_key(key)
        tif_name = f"{stem}.tif"
        dest = package_dir / tif_name
        src = f"/vsis3/{settings.aws_s3_bucket}/{key}"
        layer_cfg = get_layer_for_key(key)
        display = (layer_cfg.name if layer_cfg else None) or display_name_for_key(key)

        try:
            if layer_cfg and layer_cfg.render_type == "categorical":
                colormap_file = package_dir / f"{stem}_colors.txt"
                layer_cfg.write_gdaldem_color_file(colormap_file)
                continuous = False
            elif layer_cfg and layer_cfg.render_type == "continuous":
                colormap_file = package_dir / f"{stem}_colors.txt"
                continuous = True
            else:
                logger.warning("Skipping COG '%s' — no layers.yaml render config", key)
                if progress:
                    progress.log(f"Skipping {display}: no render config")
                continue

            logger.info("Clipping s3://%s/%s to watershed GeoTIFF", settings.aws_s3_bucket, key)
            if progress:
                progress.log(f"Clipping {display} to watershed GeoTIFF")
            cmap_name = "gist_earth"
            if layer_cfg and layer_cfg.render_type == "continuous":
                cmap_name = str(layer_cfg.continuous.get("colormap") or "gist_earth")
            _clip_to_geotiff(
                src,
                dest,
                cutline,
                colormap_file,
                extent,
                progress,
                continuous=continuous,
                nodata=layer_cfg.nodata if layer_cfg else None,
                colormap_name=cmap_name,
            )
            raster_layers.append({"filename": tif_name, "name": display})
        except Exception as exc:
            logger.exception("Failed to package raster %s: %s", key, exc)
            if progress:
                progress.log(f"Skipped {display}: {exc}")

    current_tifs = {item["filename"] for item in raster_layers}
    for orphan in package_dir.glob("*.tif"):
        if orphan.name not in current_tifs:
            logger.info("Removing orphaned raster: %s", orphan.name)
            orphan.unlink(missing_ok=True)
    for orphan in package_dir.glob("*.tif.aux.xml"):
        stem_tif = orphan.name.replace(".tif.aux.xml", ".tif")
        if stem_tif not in current_tifs:
            orphan.unlink(missing_ok=True)

    return raster_layers


def _enabled_vector_keys() -> set[str]:
    return {k.strip() for k in (settings.vector_layers or "").split(",") if k.strip()}


def _vector_style_payload(cfg) -> dict:
    """JSON-serializable style for the QGIS builder (colors + legend labels)."""
    return {
        "render_type": cfg.render_type,
        "style_column": cfg.style_column,
        "label_column": cfg.label_column,
        "classes": [
            {"value": entry.value, "label": entry.label, "color": entry.color}
            for entry in cfg.legend_entries()
        ],
        "choropleth_stops": [
            {
                "min": stop.min,
                "max": stop.max,
                "label": stop.label,
                "color": stop.color,
            }
            for stop in cfg.choropleth_stops
        ],
    }


def _export_secondary_vectors(
    package_dir: Path,
    watershed_geom: dict,
    progress: PackageProgress | None = None,
) -> list[dict]:
    """Clip enabled VECTOR_LAYERS to the watershed and write one GPKG per catalog layer.

    Shared s3_keys (villages / resilience) are clipped once, then exported once per
    thematic catalog entry so each keeps its own colors and legend in QField.
    Returns [{filename, name, layername, render_type, ...}, ...].
    """
    from app.modules.diagnose.services.layer_analysis import clip_vector_geojson
    from app.modules.diagnose.services.terrain_drape import _prepare_style_column

    enabled = _enabled_vector_keys()
    if not enabled or not s3_storage.is_s3_enabled():
        return []

    # Clip each unique s3_key once
    clipped_by_key: dict[str, dict] = {}
    exports: list[dict] = []
    for cfg in get_catalog().vector_layers():
        if cfg.s3_key not in enabled:
            continue
        if not cfg.map_render:
            continue

        display = cfg.name
        gpkg_name = f"secondary_{cfg.id}.gpkg"
        layername = cfg.id
        dest = package_dir / gpkg_name
        if progress:
            progress.log(f"Clipping {display} to watershed GeoPackage")
        try:
            if cfg.s3_key not in clipped_by_key:
                clipped_by_key[cfg.s3_key] = clip_vector_geojson(
                    cfg.s3_key, "", watershed_geom
                )
            geojson = clipped_by_key[cfg.s3_key]
            features = geojson.get("features") or []
            if not features:
                logger.info("No features in watershed for %s — writing empty GPKG", cfg.id)

            import geopandas as gpd
            from shapely.geometry import shape

            rows = []
            for feat in features:
                props = dict(feat.get("properties") or {})
                geom = feat.get("geometry")
                if not geom:
                    continue
                props["geometry"] = shape(geom)
                rows.append(props)
            if rows:
                gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
            else:
                gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

            # Materialize style_column (WISER ranks, pct_scst, aquifer labels, …)
            gdf, _ = _prepare_style_column(gdf, cfg)

            if dest.exists():
                dest.unlink()
            gdf.to_file(dest, layer=layername, driver="GPKG")
            payload = {
                "filename": gpkg_name,
                "name": display,
                "layername": layername,
                **_vector_style_payload(cfg),
            }
            exports.append(payload)
            logger.info(
                "Secondary vector %s (%s) → %s (%d features, style=%s)",
                cfg.id,
                cfg.s3_key,
                gpkg_name,
                len(features),
                cfg.render_type,
            )
        except Exception as exc:
            logger.exception("Failed to package vector %s: %s", cfg.id, exc)
            if progress:
                progress.log(f"Skipped {display}: {exc}")

    return exports


def _get_or_create_project(client: sdk.Client, name: str) -> dict:
    for project in client.list_projects():
        if project["name"] == name:
            return project
    return client.create_project(name)


def _extract_layer_ids(qgs_path: Path) -> dict[str, str]:
    """Return {layer_name: layer_id} from an existing .qgs file."""
    ids: dict[str, str] = {}
    try:
        tree = ET.parse(qgs_path)
        for maplayer in tree.getroot().findall(".//maplayer"):
            id_elem = maplayer.find("id")
            name_elem = maplayer.find("layername")
            if id_elem is not None and name_elem is not None and id_elem.text and name_elem.text:
                ids[name_elem.text] = id_elem.text
    except Exception as exc:
        logger.warning("Could not read layer IDs from %s: %s", qgs_path, exc)
    return ids


def _patch_layer_ids(qgs_path: Path, preserved: dict[str, str]) -> None:
    """Rewrite the .qgs replacing newly generated layer IDs with preserved ones.

    PyQGIS assigns a fresh UUID-based ID every run. QField Cloud uses these IDs
    to reconcile layers between packaging runs. Keeping them stable across
    re-packages prevents layers breaking on devices that already have the project.
    """
    if not preserved:
        return
    try:
        content = qgs_path.read_text(encoding="utf-8")
        # Parse the new .qgs to find which new IDs map to which layer names
        root = ET.fromstring(content)
        replacements: dict[str, str] = {}
        for maplayer in root.findall(".//maplayer"):
            id_elem = maplayer.find("id")
            name_elem = maplayer.find("layername")
            if (
                id_elem is not None
                and name_elem is not None
                and id_elem.text
                and name_elem.text
                and name_elem.text in preserved
            ):
                new_id = id_elem.text
                old_id = preserved[name_elem.text]
                if new_id != old_id:
                    replacements[new_id] = old_id
        # String-replace every occurrence (IDs appear in <id>, <layer-tree-layer>, <legendlayer>, etc.)
        for new_id, old_id in replacements.items():
            content = content.replace(new_id, old_id)
        qgs_path.write_text(content, encoding="utf-8")
        logger.info(
            "Preserved layer IDs for %d layer(s): %s",
            len(replacements),
            list(replacements.values()),
        )
    except Exception as exc:
        logger.warning("Could not patch layer IDs in %s: %s", qgs_path, exc)


def _get_user_qfield_token(user_id: str) -> tuple[str, str]:
    """Return (qfield_username, token) for the given user, or raise ValueError."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT qfield_username, qfield_token AS token
            FROM user_qfield_credentials
            WHERE user_id = %(uid)s AND qfield_token IS NOT NULL AND qfield_token <> ''
            """,
            {"uid": user_id},
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(
            "Connect your QField Cloud account in Profile settings first."
        )
    return row["qfield_username"], row["token"]


def _sync_qfield_collaborators(
    client: sdk.Client, qfc_project_id: str, project_id: str, owner_username: str
) -> int:
    """Add diagnosis collaborators as QField Cloud project editors. Returns count added."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT qc.qfield_username
            FROM (
                SELECT user_id FROM diagnosis_users WHERE diagnosis_id = %(pid)s
                UNION
                SELECT om.user_id FROM diagnosis_orgs do
                    JOIN org_members om ON om.org_id = do.org_id
                WHERE do.diagnosis_id = %(pid)s
            ) shared
            JOIN user_qfield_credentials qc ON qc.user_id = shared.user_id
            WHERE qc.qfield_username IS NOT NULL
              AND qc.qfield_username <> ''
              AND qc.qfield_token IS NOT NULL
              AND qc.qfield_token <> ''
              AND qc.qfield_username != %(owner)s
            """,
            {"pid": project_id, "owner": owner_username},
        )
        usernames = [r["qfield_username"] for r in cur.fetchall()]

    added = 0
    for username in usernames:
        try:
            client.add_project_collaborator(
                qfc_project_id, username, sdk.ProjectCollaboratorRole.EDITOR
            )
            added += 1
        except Exception as exc:
            logger.warning(
                "Could not add QField collaborator %s to project %s: %s",
                username, qfc_project_id, exc,
            )
    return added


def package_and_upload(
    project_id: str,
    user_id: str,
    progress: PackageProgress | None = None,
) -> dict:
    """
    1. Load project watershed from PostGIS
    2. Export vectors to GeoPackage and clip COGs to watershed GeoPackage rasters
    3. Generate QGIS project with offline layers (no live PostGIS on device)
    4. Upload to QField Cloud and trigger packaging
    """
    qfield_username, qfield_token = _get_user_qfield_token(user_id)

    def step(percent: int, message: str) -> None:
        if progress:
            progress.emit(percent, message)

    step(5, "Loading project from database…")
    row, extent = _project_bounds(project_id)
    project_name = f"{settings.qfield_project_name}-{row['name']}".replace(" ", "-")[:80]
    package_dir = Path(settings.packages_dir) / project_id
    package_dir.mkdir(parents=True, exist_ok=True)

    step(10, "Preparing package directory…")
    _cleanup_stale_rasters(package_dir)

    step(15, "Writing watershed cutline…")
    cutline = _write_cutline(package_dir, row["watershed_geojson"])

    step(20, "Exporting vectors to GeoPackage…")
    zones_gpkg, notes_gpkg, hypotheses_gpkg = _export_vectors_gpkg(package_dir, project_id, progress)
    step(
        35,
        f"GeoPackages ready ({zones_gpkg.stat().st_size // 1024} KB + "
        f"{notes_gpkg.stat().st_size // 1024} KB + "
        f"{hypotheses_gpkg.stat().st_size // 1024} KB)",
    )

    step(40, "Building watershed GeoTIFFs from COGs…")
    raster_layers = _build_watershed_rasters(package_dir, cutline, extent, progress)
    if raster_layers:
        step(55, f"GeoTIFF ready ({len(raster_layers)} layer(s))")
    else:
        step(55, "No COG layers configured — skipping rasters")

    step(56, "Clipping secondary vector layers…")
    watershed_geom = row["watershed_geojson"]
    if isinstance(watershed_geom, str):
        watershed_geom = json.loads(watershed_geom)
    secondary_vectors = _export_secondary_vectors(package_dir, watershed_geom, progress)
    if secondary_vectors:
        step(62, f"Secondary vectors ready ({len(secondary_vectors)} layer(s))")
    else:
        step(62, "No secondary vectors configured — skipping")

    zone_colors = _fetch_zone_colors(project_id)
    step(65, "Generating QGIS project with PyQGIS…")

    # Read layer IDs from any existing .qgs before deleting it, so we can
    # restore them after the rebuild and keep QField Cloud layer references stable.
    preserved_layer_ids: dict[str, str] = {}
    existing_qgs = package_dir / f"{project_name}.qgs"
    if existing_qgs.is_file():
        preserved_layer_ids = _extract_layer_ids(existing_qgs)
        if preserved_layer_ids and progress:
            progress.log(
                f"Existing package found — preserving layer IDs for "
                f"{len(preserved_layer_ids)} layer(s) to avoid breaking QField sync"
            )
        logger.info(
            "Preserving %d layer IDs from previous package: %s",
            len(preserved_layer_ids),
            list(preserved_layer_ids.keys()),
        )

    for stray_qgs in package_dir.glob("*.qgs"):
        stray_qgs.unlink()
    for stray_bak in package_dir.glob("*.qgs~"):
        stray_bak.unlink()

    build_qfield_project_with_qgis(
        package_dir,
        project_name,
        project_id,
        rasters=raster_layers,
        secondary_vectors=secondary_vectors,
        zone_colors=zone_colors,
        extent=extent,
    )
    qgs_path = package_dir / f"{project_name}.qgs"

    # Patch the newly generated layer IDs back to the preserved ones so that
    # QField Cloud (and any devices already holding the project) can reconcile
    # layers without treating this as a breaking schema change.
    if preserved_layer_ids:
        _patch_layer_ids(qgs_path, preserved_layer_ids)
        if progress:
            progress.log(
                f"Layer IDs preserved for {len(preserved_layer_ids)} layer(s) "
                f"({', '.join(preserved_layer_ids)})"
            )

    # Remove the QGIS backup file that PyQGIS may have created — we don't want
    # it uploaded to QField Cloud.
    for stray_bak in package_dir.glob("*.qgs~"):
        stray_bak.unlink(missing_ok=True)

    step(68, "Pruning stale package files…")
    _prune_package_dir(package_dir, project_name)

    step(70, "Connecting to QField Cloud…")
    client = sdk.Client(url=settings.qfield_cloud_url, token=qfield_token)
    qfc_project = _get_or_create_project(client, project_name)
    qfc_project_id = qfc_project["id"]
    step(75, f"QField project: {project_name}")

    step(78, "Uploading package files to QField Cloud…")
    client.upload_files(
        project_id=qfc_project_id,
        upload_type=sdk.FileTransferType.PROJECT,
        project_path=str(package_dir),
        filter_glob="*",
        throw_on_error=True,
        show_progress=False,
        force=True,
    )
    step(88, "Upload complete")

    package_state = "uploaded"
    try:
        step(90, "Triggering QField Cloud package job…")
        job = client.job_trigger(qfc_project_id, sdk.JobTypes.PACKAGE, force=True)
        job_id = job["id"]

        for attempt in range(60):
            status = client.job_status(job_id)
            state = status.get("status", "unknown")
            step(90 + min(attempt, 8), f"QField packaging job: {state}")
            if state in ("completed", "success", "finished"):
                package_state = "packaged"
                break
            if state in ("failed", "error"):
                raise RuntimeError(f"QField packaging failed: {status}")
            time.sleep(2)
    except Exception as exc:
        logger.warning("QField package job status unavailable (%s); files were uploaded.", exc)
        if progress:
            progress.log(f"Package job status unavailable: {exc}")
        package_state = "uploaded"

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE diagnosis
               SET qfield_project_id = %(qfid)s,
                   qfield_project_owner = %(uid)s
             WHERE id = %(pid)s
            """,
            {"qfid": qfc_project_id, "uid": user_id, "pid": project_id},
        )

    try:
        collab_count = _sync_qfield_collaborators(
            client, qfc_project_id, project_id, qfield_username
        )
        if collab_count and progress:
            progress.log(f"Added {collab_count} collaborator(s) to QField Cloud project")
    except Exception as exc:
        logger.warning("Collaborator sync failed (non-fatal): %s", exc)

    s3_keys: list[str] = []
    if s3_storage.is_s3_enabled():
        step(96, "Backing up package to S3…")
        s3_keys = s3_storage.sync_directory_to_s3(
            package_dir, s3_storage.packages_prefix(project_id)
        )
        step(97, f"S3 backup: {len(s3_keys)} file(s)")
        cleanup_stats = cleanup_project_s3(project_id)
        if cleanup_stats.get("deleted") and progress:
            progress.log(
                f"S3 cleanup: removed {cleanup_stats['deleted']} orphaned media file(s)"
            )

    step(100, "Packaging complete")

    return {
        "project_id": qfc_project_id,
        "project_name": project_name,
        "local_project_id": project_id,
        "package_dir": str(package_dir),
        "s3_package_keys": s3_keys,
        "status": package_state,
        "message": (
            f"Project “{row['name']}” ({row['watershed_name']}) uploaded to QField Cloud. "
            "Vectors are packaged as offline GeoPackage (no live database connection on the phone). "
            "Open QField, download the project, and add field notes with photo/audio attachments. "
            "After pushing from the field, use Sync from QField in the web app to move media to S3."
        ),
    }
