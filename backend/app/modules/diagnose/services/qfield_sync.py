"""Package project and upload to QField Cloud."""

import json
import logging
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
from app.modules.diagnose.services.lulc_colormap import write_gdaldem_color_file
from app.modules.diagnose.services.package_progress import PackageProgress
from app.modules.diagnose.services.qgis_package import build_qfield_project_with_qgis

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


def _clip_to_geotiff(
    src_vsis3: str,
    dest: Path,
    cutline: Path,
    colormap_file: Path,
    extent: list[float] | None,
    progress: PackageProgress | None = None,
) -> None:
    """Clip remote COG, apply LULC palette, and write a tiled RGBA GeoTIFF."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    work_dir = dest.parent / "_raster_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    gray_tif = work_dir / "clip_gray.tif"
    rgb_tif = work_dir / "clip_rgba.tif"
    ts_x, ts_y = _target_dimensions(extent, settings.qfield_raster_max_pixels)

    _run_gdal(
        [
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
            "near",
            "-of",
            "GTiff",
            src_vsis3,
            str(gray_tif),
        ],
        progress,
    )
    _run_gdal(
        ["gdaldem", "color-relief", str(gray_tif), str(colormap_file), str(rgb_tif), "-alpha"],
        progress,
    )
    _run_gdal(
        [
            "gdal_translate",
            "-of",
            "GTiff",
            "-co",
            "COMPRESS=DEFLATE",
            "-co",
            "TILED=YES",
            "-co",
            "PHOTOMETRIC=RGB",
            str(rgb_tif),
            str(dest),
        ],
        progress,
    )
    _validate_geotiff(dest)
    _run_gdal(["gdaladdo", "-r", "average", str(dest), "2", "4", "8"], progress)
    shutil.rmtree(work_dir, ignore_errors=True)


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
    for path in package_dir.glob("lulc_colors.txt"):
        path.unlink()
    raster_dir = package_dir / "rasters"
    if raster_dir.exists():
        shutil.rmtree(raster_dir)


def _build_watershed_rasters(
    package_dir: Path,
    cutline: Path,
    extent: list[float] | None,
    progress: PackageProgress | None = None,
) -> list[str]:
    if not s3_storage.is_s3_enabled():
        return []

    colormap_file = package_dir / "lulc_colors.txt"
    write_gdaldem_color_file(colormap_file)

    raster_filenames: list[str] = []
    for key in settings.cog_layers.split(","):
        key = key.strip()
        if not key:
            continue
        name = _layer_name_from_key(key)
        tif_name = f"{name}.tif"
        dest = package_dir / tif_name
        src = f"/vsis3/{settings.aws_s3_bucket}/{key}"
        logger.info("Clipping s3://%s/%s to watershed GeoTIFF", settings.aws_s3_bucket, key)
        if progress:
            progress.log(f"Clipping {name} to watershed GeoTIFF")
        _clip_to_geotiff(src, dest, cutline, colormap_file, extent, progress)
        raster_filenames.append(tif_name)

    # Remove any old .tif/.tif.aux.xml files that are no longer part of COG_LAYERS.
    # This prevents stale rasters from being uploaded to QField Cloud.
    current_tifs = set(raster_filenames)
    for orphan in package_dir.glob("*.tif"):
        if orphan.name not in current_tifs:
            logger.info("Removing orphaned raster: %s", orphan.name)
            orphan.unlink(missing_ok=True)
    for orphan in package_dir.glob("*.tif.aux.xml"):
        stem = orphan.name.replace(".tif.aux.xml", ".tif")
        if stem not in current_tifs:
            orphan.unlink(missing_ok=True)

    return raster_filenames


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
            FROM users
            WHERE id = %(uid)s AND qfield_token IS NOT NULL AND qfield_token <> ''
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
            SELECT DISTINCT u.qfield_username
            FROM (
                SELECT user_id FROM diagnosis_users WHERE diagnosis_id = %(pid)s
                UNION
                SELECT om.user_id FROM diagnosis_orgs do
                    JOIN org_members om ON om.org_id = do.org_id
                WHERE do.diagnosis_id = %(pid)s
            ) shared
            JOIN users u ON u.id = shared.user_id
            WHERE u.qfield_username IS NOT NULL
              AND u.qfield_username <> ''
              AND u.qfield_token IS NOT NULL
              AND u.qfield_token <> ''
              AND u.qfield_username != %(owner)s
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

    step(40, "Building watershed GeoTIFF from COG…")
    raster_filenames = _build_watershed_rasters(package_dir, cutline, extent, progress)
    if raster_filenames:
        step(60, f"GeoTIFF ready ({len(raster_filenames)} layer(s))")
    else:
        step(60, "No COG layers configured — skipping raster")

    zone_colors = _fetch_zone_colors(project_id)
    step(65, "Generating QGIS project with PyQGIS…")
    raster_filename = raster_filenames[0] if raster_filenames else None

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
        raster_filename=raster_filename,
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
        step(98, f"S3 backup: {len(s3_keys)} file(s)")

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
